import asyncio
import inspect
import logging
from collections import defaultdict
from functools import wraps
from abc import ABC, abstractmethod
from nebula.core.network.messages import MessageEvent
from nebula.core.utils.locker import Locker

class AddonEvent(ABC):
    @abstractmethod
    async def get_event_data(self):
        pass

class EventManager:
    def __init__(self, verbose=False):
        self._subscribers: dict[tuple[str, str], list] = {}
        self._addons_events_subs : dict [AddonEvent, list] = {}
        self._addons_event_lock = Locker("addons_event_lock", async_lock=True)
        self._verbose = verbose

    def subscribe(self, event_type: tuple[str, str], callback: callable):
        """Register a callback for a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logging.info(f"EventManager | Subscribed callback for event: {event_type}")

    async def publish(self, message_event: MessageEvent):
        """Trigger all callbacks registered for a specific event type."""
        if self._verbose: logging.info(f"Publishing MessageEvent: {message_event.message_type}")
        event_type = message_event.message_type
        if event_type not in self._subscribers:
            logging.error(f"EventManager | No subscribers for event: {event_type}")
            return

        for callback in self._subscribers[event_type]:
            try:
                if asyncio.iscoroutinefunction(callback) or inspect.iscoroutine(callback):
                    await callback(message_event.source, message_event.message)
                else:
                    callback(message_event.source, message_event.message)
                if self._verbose: logging.info(f"EventManager | Triggering callback for event: {event_type}, from source: {message_event.source}")
            except Exception as e:
                logging.exception(f"EventManager | Error in callback for event {event_type}: {e}")
                 
    async def subscribe_addonevent(self, addonEventType: type[AddonEvent], callback: callable):
        """Register a callback for a specific type of AddonEvent."""
        async with self._addons_event_lock:
            if addonEventType not in self._addons_events_subs:
                self._addons_events_subs[addonEventType] = []
            self._addons_events_subs[addonEventType].append(callback)
        logging.info(f"EventManager | Subscribed callback for AddonEvent type: {addonEventType.__name__}")    
        
    async def publish_addonevent(self, addonevent: AddonEvent):
        """Trigger all callbacks registered for a specific type of AddonEvent."""
        if self._verbose: logging.info(f"Publishing AddonEvent: {addonevent}")
        async with self._addons_event_lock:
            event_type = type(addonevent)
            if event_type not in self._addons_events_subs:
                logging.error(f"EventManager | No subscribers for AddonEvent type: {event_type.__name__}")
                return

            for callback in self._addons_events_subs[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback) or inspect.iscoroutine(callback):
                        await callback(addonevent)
                    else:
                        callback(addonevent)
                    if self._verbose: logging.info(f"EventManager | Triggering callback for event type: {event_type.__name__}")
                except Exception as e:
                    logging.exception(f"EventManager | Error in callback for AddonEvent {event_type.__name__}: {e}")              

