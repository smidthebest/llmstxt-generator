import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Registry: job_id -> list of subscriber queues
_subscribers: dict[int, list[asyncio.Queue]] = {}


def subscribe(job_id: int) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _subscribers.setdefault(job_id, []).append(queue)
    return queue


def unsubscribe(job_id: int, queue: asyncio.Queue):
    if job_id in _subscribers:
        try:
            _subscribers[job_id].remove(queue)
        except ValueError:
            pass
        if not _subscribers[job_id]:
            del _subscribers[job_id]


def publish(job_id: int, event: dict[str, Any]):
    if job_id not in _subscribers:
        return
    for queue in _subscribers[job_id]:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
                queue.put_nowait(event)
            except asyncio.QueueEmpty:
                pass


def cleanup(job_id: int):
    if job_id in _subscribers:
        for queue in _subscribers[job_id]:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
