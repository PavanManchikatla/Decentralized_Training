import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from db.migrate import apply_migrations
from db.orm import JobRecord, NodeRecord, ResultRecord, TaskRecord
from models import (
    Job,
    JobStatus,
    Node,
    NodeCapabilities,
    NodeIdentity,
    NodeMetrics,
    NodePolicy,
    NodeStatus,
    Task,
    TaskResult,
    TaskStatus,
    TaskType,
)
from scheduler import evaluate_node_eligibility, score_node


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _encode_json(value: dict[str, object] | None) -> str:
    return json.dumps(value or {}, separators=(",", ":"), default=str)


def _decode_json(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    decoded = json.loads(value)
    if isinstance(decoded, dict):
        return decoded
    return {"value": decoded}


_ALLOWED_JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING},
    JobStatus.RUNNING: {JobStatus.COMPLETED, JobStatus.FAILED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
}


class CoordinatorRepository:
    def __init__(self, db_url: str) -> None:
        apply_migrations(db_url)
        self._engine = create_engine(
            db_url,
            future=True,
            connect_args={"check_same_thread": False},
        )
        self._session_factory = sessionmaker(
            bind=self._engine, autoflush=False, expire_on_commit=False
        )

    def _default_capabilities(self) -> NodeCapabilities:
        return NodeCapabilities()

    def _default_metrics(self) -> NodeMetrics:
        return NodeMetrics()

    def _default_policy(self) -> NodePolicy:
        return NodePolicy()

    def _ensure_node(self, session: Session, node_id: str) -> NodeRecord:
        node = session.get(NodeRecord, node_id)
        if node is not None:
            return node

        now = _utc_now()
        node = NodeRecord(
            node_id=node_id,
            display_name=node_id,
            ip="0.0.0.0",
            port=0,
            status=NodeStatus.UNKNOWN.value,
            capabilities_json=_encode_json(
                self._default_capabilities().model_dump(mode="json")
            ),
            metrics_json=_encode_json(self._default_metrics().model_dump(mode="json")),
            policy_json=_encode_json(self._default_policy().model_dump(mode="json")),
            last_seen=now,
            created_at=now,
            updated_at=now,
        )
        session.add(node)
        session.flush()
        return node

    def _to_node(self, row: NodeRecord) -> Node:
        identity = NodeIdentity(
            node_id=row.node_id,
            display_name=row.display_name,
            ip=row.ip,
            port=row.port,
        )
        capabilities = NodeCapabilities.model_validate(
            _decode_json(row.capabilities_json)
        )
        metrics = NodeMetrics.model_validate(_decode_json(row.metrics_json))
        policy = NodePolicy.model_validate(_decode_json(row.policy_json))

        return Node(
            identity=identity,
            capabilities=capabilities,
            metrics=metrics,
            policy=policy,
            status=NodeStatus(row.status),
            last_seen=_as_utc(row.last_seen) or _utc_now(),
            created_at=_as_utc(row.created_at) or _utc_now(),
            updated_at=_as_utc(row.updated_at) or _utc_now(),
        )

    def _task_rows_for_job(self, session: Session, job_id: str) -> list[TaskRecord]:
        return session.scalars(
            select(TaskRecord)
            .where(TaskRecord.job_id == job_id)
            .order_by(TaskRecord.created_at.asc())
        ).all()

    def _task_result_rows_for_job(
        self, session: Session, job_id: str
    ) -> list[ResultRecord]:
        stmt = (
            select(ResultRecord)
            .join(TaskRecord, TaskRecord.id == ResultRecord.task_id)
            .where(TaskRecord.job_id == job_id)
        )
        return session.scalars(stmt).all()

    def _job_stats(self, session: Session, job_id: str) -> dict[str, object]:
        task_rows = self._task_rows_for_job(session, job_id)
        result_rows = self._task_result_rows_for_job(session, job_id)

        total_tasks = len(task_rows)
        queued_tasks = sum(
            1 for row in task_rows if row.status == TaskStatus.QUEUED.value
        )
        running_tasks = sum(
            1 for row in task_rows if row.status == TaskStatus.RUNNING.value
        )
        completed_tasks = sum(
            1 for row in task_rows if row.status == TaskStatus.COMPLETED.value
        )
        failed_tasks = sum(
            1 for row in task_rows if row.status == TaskStatus.FAILED.value
        )
        total_retries = sum(row.retries for row in task_rows)

        assigned_nodes = sorted(
            {
                row.assigned_node_id
                for row in task_rows
                if row.assigned_node_id is not None and row.assigned_node_id != ""
            }
        )

        avg_task_duration_ms: float | None = None
        if result_rows:
            avg_task_duration_ms = round(
                sum(row.duration_ms for row in result_rows) / len(result_rows), 3
            )

        throughput_tasks_per_minute: float | None = None
        started_candidates = [
            _as_utc(row.started_at)
            for row in task_rows
            if _as_utc(row.started_at) is not None
        ]
        if completed_tasks > 0 and started_candidates:
            earliest_started = min(started_candidates)
            now = _utc_now()
            elapsed_minutes = max((now - earliest_started).total_seconds() / 60.0, 1e-6)
            throughput_tasks_per_minute = round(completed_tasks / elapsed_minutes, 3)

        return {
            "total_tasks": total_tasks,
            "queued_tasks": queued_tasks,
            "running_tasks": running_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "total_retries": total_retries,
            "assigned_nodes": assigned_nodes,
            "avg_task_duration_ms": avg_task_duration_ms,
            "throughput_tasks_per_minute": throughput_tasks_per_minute,
        }

    def _refresh_job_state_locked(
        self, session: Session, job_id: str
    ) -> JobRecord | None:
        row = session.get(JobRecord, job_id)
        if row is None:
            return None

        stats = self._job_stats(session, job_id)
        total_tasks = int(stats["total_tasks"])
        queued_tasks = int(stats["queued_tasks"])
        running_tasks = int(stats["running_tasks"])
        completed_tasks = int(stats["completed_tasks"])
        failed_tasks = int(stats["failed_tasks"])

        now = _utc_now()
        status = JobStatus(row.status)
        if total_tasks > 0:
            if completed_tasks == total_tasks:
                status = JobStatus.COMPLETED
            elif failed_tasks > 0 and queued_tasks == 0 and running_tasks == 0:
                status = JobStatus.FAILED
            elif running_tasks > 0 or completed_tasks > 0 or failed_tasks > 0:
                status = JobStatus.RUNNING
            else:
                status = JobStatus.QUEUED

        row.status = status.value
        row.updated_at = now
        row.attempts = int(stats["total_retries"])

        assigned_nodes = list(stats["assigned_nodes"])
        row.assigned_node_id = assigned_nodes[0] if assigned_nodes else None

        task_rows = self._task_rows_for_job(session, job_id)
        started_values = [
            _as_utc(item.started_at)
            for item in task_rows
            if _as_utc(item.started_at) is not None
        ]
        completed_values = [
            _as_utc(item.completed_at)
            for item in task_rows
            if _as_utc(item.completed_at) is not None
        ]

        if started_values and row.started_at is None:
            row.started_at = min(started_values)

        if status in {JobStatus.COMPLETED, JobStatus.FAILED} and completed_values:
            row.completed_at = max(completed_values)
        elif status not in {JobStatus.COMPLETED, JobStatus.FAILED}:
            row.completed_at = None

        if status == JobStatus.FAILED and failed_tasks > 0:
            row.error = f"{failed_tasks} tasks failed"
        elif status == JobStatus.COMPLETED:
            row.error = None

        session.flush()
        return row

    def _to_job(self, session: Session, row: JobRecord) -> Job:
        stats = self._job_stats(session, row.id)

        return Job(
            id=row.id,
            type=TaskType(row.type),
            status=JobStatus(row.status),
            payload_ref=row.payload_ref,
            assigned_node_id=row.assigned_node_id,
            attempts=row.attempts,
            created_at=_as_utc(row.created_at) or _utc_now(),
            updated_at=_as_utc(row.updated_at) or _utc_now(),
            started_at=_as_utc(row.started_at),
            completed_at=_as_utc(row.completed_at),
            error=row.error,
            total_tasks=int(stats["total_tasks"]),
            queued_tasks=int(stats["queued_tasks"]),
            running_tasks=int(stats["running_tasks"]),
            completed_tasks=int(stats["completed_tasks"]),
            failed_tasks=int(stats["failed_tasks"]),
            total_retries=int(stats["total_retries"]),
            assigned_nodes=list(stats["assigned_nodes"]),
            avg_task_duration_ms=(
                float(stats["avg_task_duration_ms"])
                if stats["avg_task_duration_ms"] is not None
                else None
            ),
            throughput_tasks_per_minute=(
                float(stats["throughput_tasks_per_minute"])
                if stats["throughput_tasks_per_minute"] is not None
                else None
            ),
        )

    def _to_task(self, row: TaskRecord) -> Task:
        return Task(
            id=row.id,
            job_id=row.job_id,
            type=TaskType(row.type),
            payload=_decode_json(row.payload_json),
            status=TaskStatus(row.status),
            assigned_node_id=row.assigned_node_id,
            retries=row.retries,
            max_retries=row.max_retries,
            lease_expires_at=_as_utc(row.lease_expires_at),
            created_at=_as_utc(row.created_at) or _utc_now(),
            updated_at=_as_utc(row.updated_at) or _utc_now(),
            started_at=_as_utc(row.started_at),
            completed_at=_as_utc(row.completed_at),
            error=row.error,
        )

    def upsert_node_identity(
        self, node_id: str, display_name: str, ip: str, port: int
    ) -> Node:
        now = _utc_now()
        with self._session_factory.begin() as session:
            node = self._ensure_node(session, node_id)
            node.display_name = display_name
            node.ip = ip
            node.port = port
            node.updated_at = now
            session.flush()
            return self._to_node(node)

    def upsert_node_capabilities(
        self, node_id: str, capabilities: NodeCapabilities | dict[str, object]
    ) -> Node:
        now = _utc_now()
        payload = NodeCapabilities.model_validate(capabilities)

        with self._session_factory.begin() as session:
            node = self._ensure_node(session, node_id)
            node.capabilities_json = _encode_json(payload.model_dump(mode="json"))
            node.updated_at = now
            session.flush()
            return self._to_node(node)

    def update_node_metrics(
        self, node_id: str, metrics: NodeMetrics | dict[str, object]
    ) -> Node:
        now = _utc_now()
        payload = NodeMetrics.model_validate(metrics)

        with self._session_factory.begin() as session:
            node = self._ensure_node(session, node_id)
            node.metrics_json = _encode_json(payload.model_dump(mode="json"))
            node.status = NodeStatus.ONLINE.value
            node.last_seen = payload.heartbeat_ts
            node.updated_at = now
            session.flush()
            return self._to_node(node)

    def get_nodes(self) -> list[Node]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(NodeRecord).order_by(NodeRecord.node_id.asc())
            ).all()
            return [self._to_node(row) for row in rows]

    def get_node(self, node_id: str) -> Node | None:
        with self._session_factory() as session:
            row = session.get(NodeRecord, node_id)
            if row is None:
                return None
            return self._to_node(row)

    def update_node_policy(
        self, node_id: str, policy: NodePolicy | dict[str, object]
    ) -> Node:
        now = _utc_now()
        payload = NodePolicy.model_validate(policy)

        with self._session_factory.begin() as session:
            node = self._ensure_node(session, node_id)
            node.policy_json = _encode_json(payload.model_dump(mode="json"))
            node.updated_at = now
            session.flush()
            return self._to_node(node)

    def mark_offline_if_stale_nodes(self, stale_seconds: int) -> list[Node]:
        now = _utc_now()
        cutoff = now - timedelta(seconds=stale_seconds)
        updated_nodes: list[Node] = []

        with self._session_factory.begin() as session:
            rows = session.scalars(select(NodeRecord)).all()
            for node in rows:
                if (
                    _as_utc(node.last_seen) or now
                ) < cutoff and node.status != NodeStatus.OFFLINE.value:
                    node.status = NodeStatus.OFFLINE.value
                    node.updated_at = now
                    session.flush()
                    updated_nodes.append(self._to_node(node))

        return updated_nodes

    def mark_offline_if_stale(self, stale_seconds: int) -> int:
        return len(self.mark_offline_if_stale_nodes(stale_seconds=stale_seconds))

    def create_job(self, job: Job | dict[str, object]) -> Job:
        payload = Job.model_validate(job)
        with self._session_factory.begin() as session:
            row = JobRecord(
                id=payload.id,
                type=payload.type.value,
                status=payload.status.value,
                payload_ref=payload.payload_ref,
                assigned_node_id=payload.assigned_node_id,
                attempts=payload.attempts,
                created_at=payload.created_at,
                updated_at=payload.updated_at,
                started_at=payload.started_at,
                completed_at=payload.completed_at,
                error=payload.error,
            )
            session.add(row)
            session.flush()
            return self._to_job(session, row)

    def list_jobs(
        self,
        status: JobStatus | None = None,
        task_type: TaskType | None = None,
        node_id: str | None = None,
    ) -> list[Job]:
        stmt = select(JobRecord)
        if status is not None:
            stmt = stmt.where(JobRecord.status == status.value)
        if task_type is not None:
            stmt = stmt.where(JobRecord.type == task_type.value)
        if node_id is not None:
            task_subquery = select(TaskRecord.job_id).where(
                TaskRecord.assigned_node_id == node_id
            )
            stmt = stmt.where(
                or_(
                    JobRecord.assigned_node_id == node_id,
                    JobRecord.id.in_(task_subquery),
                )
            )
        stmt = stmt.order_by(JobRecord.created_at.desc(), JobRecord.id.asc())

        with self._session_factory() as session:
            rows = session.scalars(stmt).all()
            return [self._to_job(session, row) for row in rows]

    def get_job(self, job_id: str) -> Job | None:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                return None
            return self._to_job(session, row)

    def assign_job(self, job_id: str, node_id: str | None) -> Job:
        now = _utc_now()
        with self._session_factory.begin() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise KeyError(job_id)
            row.assigned_node_id = node_id
            row.updated_at = now
            session.flush()
            return self._to_job(session, row)

    def transition_job_status(
        self, job_id: str, new_status: JobStatus, error: str | None = None
    ) -> Job:
        now = _utc_now()

        with self._session_factory.begin() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise KeyError(job_id)

            current_status = JobStatus(row.status)
            if current_status == new_status:
                if error is not None:
                    row.error = error
                    row.updated_at = now
                    session.flush()
                return self._to_job(session, row)

            if new_status not in _ALLOWED_JOB_TRANSITIONS[current_status]:
                raise ValueError(
                    f"Invalid transition from {current_status.value} to {new_status.value}"
                )

            row.status = new_status.value
            row.updated_at = now

            if new_status == JobStatus.RUNNING:
                row.started_at = row.started_at or now
                row.attempts = (row.attempts or 0) + 1
                row.error = None
            elif new_status == JobStatus.COMPLETED:
                row.completed_at = now
                row.error = None
            elif new_status == JobStatus.FAILED:
                row.completed_at = now
                row.error = error or row.error or "Job failed"

            session.flush()
            return self._to_job(session, row)

    def create_tasks(
        self,
        job_id: str,
        task_type: TaskType,
        payloads: list[dict[str, object]],
        max_retries: int = 2,
    ) -> list[Task]:
        now = _utc_now()
        with self._session_factory.begin() as session:
            job = session.get(JobRecord, job_id)
            if job is None:
                raise KeyError(job_id)

            created: list[Task] = []
            for payload in payloads:
                row = TaskRecord(
                    id=f"task-{uuid.uuid4().hex[:12]}",
                    job_id=job_id,
                    type=task_type.value,
                    payload_json=_encode_json(payload),
                    status=TaskStatus.QUEUED.value,
                    assigned_node_id=None,
                    retries=0,
                    max_retries=max_retries,
                    lease_expires_at=None,
                    created_at=now,
                    updated_at=now,
                    started_at=None,
                    completed_at=None,
                    error=None,
                )
                session.add(row)
                session.flush()
                created.append(self._to_task(row))

            self._refresh_job_state_locked(session, job_id)
            return created

    def list_tasks(
        self,
        job_id: str | None = None,
        status: TaskStatus | None = None,
        node_id: str | None = None,
    ) -> list[Task]:
        stmt = select(TaskRecord)
        if job_id is not None:
            stmt = stmt.where(TaskRecord.job_id == job_id)
        if status is not None:
            stmt = stmt.where(TaskRecord.status == status.value)
        if node_id is not None:
            stmt = stmt.where(TaskRecord.assigned_node_id == node_id)
        stmt = stmt.order_by(TaskRecord.created_at.asc())

        with self._session_factory() as session:
            rows = session.scalars(stmt).all()
            return [self._to_task(row) for row in rows]

    def get_task(self, task_id: str) -> Task | None:
        with self._session_factory() as session:
            row = session.get(TaskRecord, task_id)
            if row is None:
                return None
            return self._to_task(row)

    def pull_task_for_node(self, node_id: str, lease_seconds: int) -> Task | None:
        now = _utc_now()
        lease_expires_at = now + timedelta(seconds=lease_seconds)

        with self._session_factory.begin() as session:
            self._recover_stale_tasks_locked(session, now)

            node_row = session.get(NodeRecord, node_id)
            if node_row is None:
                return None
            node = self._to_node(node_row)

            queued_rows = session.scalars(
                select(TaskRecord)
                .where(TaskRecord.status == TaskStatus.QUEUED.value)
                .order_by(TaskRecord.created_at.asc())
            ).all()

            selected_row: TaskRecord | None = None
            selected_score: float | None = None

            for row in queued_rows:
                task_type = TaskType(row.type)
                eligible, _ = evaluate_node_eligibility(node, task_type)
                if not eligible:
                    continue

                score = score_node(node, task_type)
                age_bonus = max(
                    (now - (_as_utc(row.created_at) or now)).total_seconds() / 30.0, 0.0
                )
                weighted_score = score + age_bonus

                if (
                    selected_row is None
                    or selected_score is None
                    or weighted_score > selected_score
                ):
                    selected_row = row
                    selected_score = weighted_score

            if selected_row is None:
                return None

            selected_row.status = TaskStatus.RUNNING.value
            selected_row.assigned_node_id = node_id
            selected_row.lease_expires_at = lease_expires_at
            selected_row.started_at = selected_row.started_at or now
            selected_row.updated_at = now

            job_row = session.get(JobRecord, selected_row.job_id)
            if job_row is not None:
                job_row.status = JobStatus.RUNNING.value
                job_row.assigned_node_id = node_id
                job_row.started_at = job_row.started_at or now
                job_row.updated_at = now

            session.flush()
            self._refresh_job_state_locked(session, selected_row.job_id)
            return self._to_task(selected_row)

    def _recover_stale_tasks_locked(
        self, session: Session, now: datetime
    ) -> list[TaskRecord]:
        stale_rows = session.scalars(
            select(TaskRecord).where(
                TaskRecord.status == TaskStatus.RUNNING.value,
                TaskRecord.lease_expires_at.is_not(None),
                TaskRecord.lease_expires_at < now,
            )
        ).all()

        touched_jobs: set[str] = set()
        for row in stale_rows:
            row.retries += 1
            row.lease_expires_at = None
            row.updated_at = now
            row.error = "Task lease expired"

            if row.retries > row.max_retries:
                row.status = TaskStatus.FAILED.value
                row.completed_at = now
            else:
                row.status = TaskStatus.QUEUED.value
                row.assigned_node_id = None

            touched_jobs.add(row.job_id)

        for job_id in touched_jobs:
            self._refresh_job_state_locked(session, job_id)

        session.flush()
        return stale_rows

    def recover_stale_tasks(self) -> list[Task]:
        now = _utc_now()
        with self._session_factory.begin() as session:
            rows = self._recover_stale_tasks_locked(session, now)
            return [self._to_task(row) for row in rows]

    def submit_task_result(self, result: TaskResult) -> tuple[Task, Job]:
        payload = TaskResult.model_validate(result)
        now = _utc_now()

        with self._session_factory.begin() as session:
            row = session.get(TaskRecord, payload.task_id)
            if row is None:
                raise KeyError(payload.task_id)

            if (
                row.assigned_node_id is not None
                and row.assigned_node_id != payload.node_id
            ):
                raise ValueError(
                    f"Task '{payload.task_id}' assigned to {row.assigned_node_id}, not {payload.node_id}"
                )

            if row.status not in {TaskStatus.RUNNING.value, TaskStatus.QUEUED.value}:
                raise ValueError(
                    f"Task '{payload.task_id}' is not executable in status {row.status}"
                )

            result_row = ResultRecord(
                task_id=payload.task_id,
                node_id=payload.node_id,
                success=1 if payload.success else 0,
                output_json=_encode_json(payload.output),
                duration_ms=payload.duration_ms,
                created_at=now,
            )
            session.add(result_row)

            row.lease_expires_at = None
            row.updated_at = now

            if payload.success:
                row.status = TaskStatus.COMPLETED.value
                row.completed_at = now
                row.error = None
            else:
                row.retries += 1
                if row.retries > row.max_retries:
                    row.status = TaskStatus.FAILED.value
                    row.completed_at = now
                    row.error = "Task failed after max retries"
                else:
                    row.status = TaskStatus.QUEUED.value
                    row.assigned_node_id = None
                    row.error = "Task execution failed; requeued"

            session.flush()
            refreshed_job = self._refresh_job_state_locked(session, row.job_id)
            if refreshed_job is None:
                raise KeyError(row.job_id)

            return (self._to_task(row), self._to_job(session, refreshed_job))

    def get_execution_metrics(self) -> dict[str, object]:
        now = _utc_now()
        five_minutes_ago = now - timedelta(minutes=5)

        with self._session_factory() as session:
            total_results = session.scalar(select(func.count(ResultRecord.id))) or 0
            success_results = (
                session.scalar(
                    select(func.count(ResultRecord.id)).where(ResultRecord.success == 1)
                )
                or 0
            )
            failed_results = int(total_results) - int(success_results)

            avg_duration_ms = session.scalar(select(func.avg(ResultRecord.duration_ms)))
            recent_completed = (
                session.scalar(
                    select(func.count(ResultRecord.id)).where(
                        ResultRecord.created_at >= five_minutes_ago
                    )
                )
                or 0
            )
            throughput_per_minute = round(float(recent_completed) / 5.0, 3)

            node_rows = session.execute(
                select(
                    ResultRecord.node_id,
                    func.count(ResultRecord.id).label("total"),
                    func.sum(ResultRecord.success).label("success"),
                ).group_by(ResultRecord.node_id)
            ).all()

            node_reliability: dict[str, float] = {}
            for node_id, total, success in node_rows:
                total_count = int(total or 0)
                success_count = int(success or 0)
                if total_count <= 0:
                    continue
                node_reliability[str(node_id)] = round(success_count / total_count, 3)

            return {
                "total_results": int(total_results),
                "success_results": int(success_results),
                "failed_results": int(failed_results),
                "avg_duration_ms": (
                    round(float(avg_duration_ms), 3)
                    if avg_duration_ms is not None
                    else None
                ),
                "throughput_tasks_per_minute": throughput_per_minute,
                "node_reliability": node_reliability,
            }

    def close(self) -> None:
        self._engine.dispose()


_default_repository: CoordinatorRepository | None = None


def init_repository(db_url: str) -> CoordinatorRepository:
    global _default_repository
    _default_repository = CoordinatorRepository(db_url=db_url)
    return _default_repository


def get_repository() -> CoordinatorRepository:
    if _default_repository is None:
        raise RuntimeError("Repository is not initialized")
    return _default_repository


def upsert_node_identity(node_id: str, display_name: str, ip: str, port: int) -> Node:
    return get_repository().upsert_node_identity(node_id, display_name, ip, port)


def upsert_node_capabilities(
    node_id: str, capabilities: NodeCapabilities | dict[str, object]
) -> Node:
    return get_repository().upsert_node_capabilities(node_id, capabilities)


def update_node_metrics(node_id: str, metrics: NodeMetrics | dict[str, object]) -> Node:
    return get_repository().update_node_metrics(node_id, metrics)


def get_nodes() -> list[Node]:
    return get_repository().get_nodes()


def get_node(node_id: str) -> Node | None:
    return get_repository().get_node(node_id)


def update_node_policy(node_id: str, policy: NodePolicy | dict[str, object]) -> Node:
    return get_repository().update_node_policy(node_id, policy)


def mark_offline_if_stale(stale_seconds: int) -> int:
    return get_repository().mark_offline_if_stale(stale_seconds)


def mark_offline_if_stale_nodes(stale_seconds: int) -> list[Node]:
    return get_repository().mark_offline_if_stale_nodes(stale_seconds)


def create_job(job: Job | dict[str, object]) -> Job:
    return get_repository().create_job(job)


def list_jobs(
    status: JobStatus | None = None,
    task_type: TaskType | None = None,
    node_id: str | None = None,
) -> list[Job]:
    return get_repository().list_jobs(
        status=status, task_type=task_type, node_id=node_id
    )


def get_job(job_id: str) -> Job | None:
    return get_repository().get_job(job_id)


def assign_job(job_id: str, node_id: str | None) -> Job:
    return get_repository().assign_job(job_id=job_id, node_id=node_id)


def transition_job_status(
    job_id: str, new_status: JobStatus, error: str | None = None
) -> Job:
    return get_repository().transition_job_status(
        job_id=job_id, new_status=new_status, error=error
    )


def create_tasks(
    job_id: str,
    task_type: TaskType,
    payloads: list[dict[str, object]],
    max_retries: int = 2,
) -> list[Task]:
    return get_repository().create_tasks(
        job_id=job_id, task_type=task_type, payloads=payloads, max_retries=max_retries
    )


def list_tasks(
    job_id: str | None = None,
    status: TaskStatus | None = None,
    node_id: str | None = None,
) -> list[Task]:
    return get_repository().list_tasks(job_id=job_id, status=status, node_id=node_id)


def get_task(task_id: str) -> Task | None:
    return get_repository().get_task(task_id)


def pull_task_for_node(node_id: str, lease_seconds: int) -> Task | None:
    return get_repository().pull_task_for_node(
        node_id=node_id, lease_seconds=lease_seconds
    )


def recover_stale_tasks() -> list[Task]:
    return get_repository().recover_stale_tasks()


def submit_task_result(result: TaskResult) -> tuple[Task, Job]:
    return get_repository().submit_task_result(result)


def get_execution_metrics() -> dict[str, object]:
    return get_repository().get_execution_metrics()
