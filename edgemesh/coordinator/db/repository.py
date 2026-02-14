import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from db.migrate import apply_migrations
from db.orm import JobRecord, NodeRecord
from models import (
    Job,
    JobStatus,
    Node,
    NodeCapabilities,
    NodeIdentity,
    NodeMetrics,
    NodePolicy,
    NodeStatus,
    TaskType,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _encode_json(value: dict[str, object]) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


class CoordinatorRepository:
    def __init__(self, db_url: str) -> None:
        apply_migrations(db_url)
        self._engine = create_engine(
            db_url,
            future=True,
            connect_args={"check_same_thread": False},
        )
        self._session_factory = sessionmaker(bind=self._engine, autoflush=False, expire_on_commit=False)

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
            capabilities_json=_encode_json(self._default_capabilities().model_dump(mode="json")),
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
        capabilities = NodeCapabilities.model_validate(json.loads(row.capabilities_json))
        metrics = NodeMetrics.model_validate(json.loads(row.metrics_json))
        policy = NodePolicy.model_validate(json.loads(row.policy_json))

        return Node(
            identity=identity,
            capabilities=capabilities,
            metrics=metrics,
            policy=policy,
            status=NodeStatus(row.status),
            last_seen=_as_utc(row.last_seen),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
        )

    def _to_job(self, row: JobRecord) -> Job:
        return Job(
            id=row.id,
            type=TaskType(row.type),
            status=JobStatus(row.status),
            assigned_node_id=row.assigned_node_id,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            error=row.error,
        )

    def upsert_node_identity(self, node_id: str, display_name: str, ip: str, port: int) -> Node:
        now = _utc_now()
        with self._session_factory.begin() as session:
            node = self._ensure_node(session, node_id)
            node.display_name = display_name
            node.ip = ip
            node.port = port
            node.updated_at = now
            session.flush()
            return self._to_node(node)

    def upsert_node_capabilities(self, node_id: str, capabilities: NodeCapabilities | dict[str, object]) -> Node:
        now = _utc_now()
        payload = NodeCapabilities.model_validate(capabilities)

        with self._session_factory.begin() as session:
            node = self._ensure_node(session, node_id)
            node.capabilities_json = _encode_json(payload.model_dump(mode="json"))
            node.updated_at = now
            session.flush()
            return self._to_node(node)

    def update_node_metrics(self, node_id: str, metrics: NodeMetrics | dict[str, object]) -> Node:
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
            rows = session.scalars(select(NodeRecord).order_by(NodeRecord.node_id.asc())).all()
            return [self._to_node(row) for row in rows]

    def get_node(self, node_id: str) -> Node | None:
        with self._session_factory() as session:
            row = session.get(NodeRecord, node_id)
            if row is None:
                return None
            return self._to_node(row)

    def update_node_policy(self, node_id: str, policy: NodePolicy | dict[str, object]) -> Node:
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
                if _as_utc(node.last_seen) < cutoff and node.status != NodeStatus.OFFLINE.value:
                    node.status = NodeStatus.OFFLINE.value
                    node.updated_at = now
                    session.flush()
                    updated_nodes.append(self._to_node(node))

        return updated_nodes

    def mark_offline_if_stale(self, stale_seconds: int) -> int:
        return len(self.mark_offline_if_stale_nodes(stale_seconds=stale_seconds))

    def create_job(self, job: Job) -> Job:
        payload = Job.model_validate(job)
        with self._session_factory.begin() as session:
            row = JobRecord(
                id=payload.id,
                type=payload.type.value,
                status=payload.status.value,
                assigned_node_id=payload.assigned_node_id,
                created_at=payload.created_at,
                updated_at=payload.updated_at,
                error=payload.error,
            )
            session.add(row)
            session.flush()
            return self._to_job(row)

    def get_job(self, job_id: str) -> Job | None:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                return None
            return self._to_job(row)

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


def upsert_node_capabilities(node_id: str, capabilities: NodeCapabilities | dict[str, object]) -> Node:
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
