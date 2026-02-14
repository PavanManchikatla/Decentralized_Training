import asyncio
from collections import defaultdict, deque
from collections.abc import Iterable
from threading import Lock

from models import NodeMetrics, NodeUpdateEvent


class NodeEventBus:
    def __init__(self, queue_size: int = 256) -> None:
        self._queue_size = queue_size
        self._subscribers: set[asyncio.Queue[NodeUpdateEvent]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[NodeUpdateEvent]:
        queue: asyncio.Queue[NodeUpdateEvent] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[NodeUpdateEvent]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, event: NodeUpdateEvent) -> None:
        async with self._lock:
            subscribers: Iterable[asyncio.Queue[NodeUpdateEvent]] = tuple(self._subscribers)

        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)


class MetricsHistoryBuffer:
    def __init__(self, max_samples: int = 256) -> None:
        self._max_samples = max_samples
        self._samples: dict[str, deque[NodeMetrics]] = defaultdict(
            lambda: deque(maxlen=self._max_samples)
        )
        self._lock = Lock()

    def append(self, node_id: str, metrics: NodeMetrics) -> None:
        with self._lock:
            self._samples[node_id].append(metrics)

    def get(self, node_id: str, limit: int) -> list[NodeMetrics]:
        with self._lock:
            samples = self._samples.get(node_id)
            if not samples:
                return []
            items = list(samples)

        return items[-limit:]


node_event_bus = NodeEventBus()
metrics_history_buffer = MetricsHistoryBuffer()
