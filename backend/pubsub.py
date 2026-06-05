import asyncio
import json
import logging

log = logging.getLogger("pubsub")

class AsyncPubSubBroker:
    """
    Scalable asyncio Pub/Sub Message Broker.
    Replaces the naive websocket set with individual asyncio queues.
    """
    def __init__(self):
        self.subscribers = set()
        self.loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def subscribe(self) -> asyncio.Queue:
        """Create a new queue for a subscriber and register it."""
        queue = asyncio.Queue()
        self.subscribers.add(queue)
        log.debug(f"New subscriber added. Total subscribers: {len(self.subscribers)}")
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        """Remove a subscriber queue."""
        self.subscribers.discard(queue)
        log.debug(f"Subscriber removed. Total subscribers: {len(self.subscribers)}")

    async def _publish_async(self, message: str):
        """Internal coroutine to dispatch the message to all queues."""
        dead_queues = set()
        for queue in list(self.subscribers):
            try:
                # Use put_nowait to ensure non-blocking scalable dispatch
                queue.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("Subscriber queue full, dropping message")
            except Exception as e:
                log.error(f"Failed to push message to queue: {e}")
                dead_queues.add(queue)

        # Cleanup any dead queues
        for q in dead_queues:
            self.subscribers.discard(q)

    def publish_sync(self, event_type: str, data: dict):
        """
        Thread-safe broadcast method.
        Can be called from synchronous background threads.
        """
        if not self.loop:
            return

        log.debug(f"Publishing event: {event_type}")
        try:
            message = json.dumps({"type": event_type, "data": data})
            asyncio.run_coroutine_threadsafe(self._publish_async(message), self.loop)
        except Exception as e:
            log.error(f"Broadcast serialization/publish error: {e}")

# Global broker instance
broker = AsyncPubSubBroker()

def broadcast(event_type: str, data: dict):
    """
    Exposed broadcast function to be used by the rest of the application.
    """
    broker.publish_sync(event_type, data)
