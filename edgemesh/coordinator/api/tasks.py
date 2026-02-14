import asyncio
import logging

from api.state import node_event_bus
from db import mark_offline_if_stale_nodes
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
