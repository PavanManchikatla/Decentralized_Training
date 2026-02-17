import asyncio
import logging

from api.state import node_event_bus
from db import mark_offline_if_stale_nodes, recover_stale_tasks
from models import NodeUpdateEvent

logger = logging.getLogger("coordinator")


async def stale_node_monitor(stale_seconds: int) -> None:
    while True:
        await asyncio.sleep(5)
        stale_nodes = mark_offline_if_stale_nodes(stale_seconds)
        for node in stale_nodes:
            event = NodeUpdateEvent(
                node_id=node.identity.node_id,
                status=node.status,
                metrics=node.metrics,
                updated_at=node.updated_at,
            )
            await node_event_bus.publish(event)
            logger.info(
                "node_marked_offline",
                extra={"node_id": node.identity.node_id, "status": node.status.value},
            )


async def stale_task_monitor(interval_seconds: int = 3) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        stale_tasks = recover_stale_tasks()
        if stale_tasks:
            logger.info(
                "stale_tasks_recovered",
                extra={
                    "count": len(stale_tasks),
                    "task_ids": [task.id for task in stale_tasks],
                },
            )
