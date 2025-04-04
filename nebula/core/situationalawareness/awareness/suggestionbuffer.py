from nebula.core.utils.locker import Locker
from nebula.utils import logging
import asyncio
from nebula.core.situationalawareness.awareness.samoduleagent import SAModuleAgent
from nebula.core.situationalawareness.awareness.sacommand import SACommand
from nebula.core.nebulaevents import NodeEvent, RoundEndEvent, AggregationEvent
from collections import defaultdict

class SuggestionBuffer():
    _instance = None
    _lock = Locker("initialize_sb_lock", async_lock=False)

    def __new__(cls, arbitrator_notification, verbose):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls):
        """Obtain SuggestionBuffer instance"""
        if cls._instance is None:
            raise ValueError("SuggestionBuffer has not been initialized yet.")
        return cls._instance

    def __init__(self, arbitrator_notification : asyncio.Event, verbose):
        """Initializes the suggestion buffer with thread-safe synchronization."""
        self._arbitrator_notification = arbitrator_notification
        self._arbitrator_notification_lock = Locker("arbitrator_notification_lock", async_lock=True)
        self._verbose = verbose
        self._buffer : dict[NodeEvent, list[SACommand]] = defaultdict(list)             # {event: [suggestion]}
        self._suggestion_buffer_lock = Locker("suggestion_buffer_lock", async_lock=True)
        self._expected_agents = defaultdict(set)                                        # {event: {agents}}
        self._expected_agents_lock = Locker("expected_agents_lock", async_lock=True)
        self._event_notifications : dict[SAModuleAgent, asyncio.Event] = {}
        self._event_waited = None
                      
    async def register_event_agents(self, event_type, agent: SAModuleAgent):
        """Registers expected agents for a given event."""
        async with self._expected_agents_lock:
            if self._verbose: logging.info(f"Registering SA Agent: {agent.get_agent()} for event: {event_type}")
            self._expected_agents[event_type].add(agent)
            if event_type not in self._event_notifications:
                self._event_notifications[agent] = asyncio.Event()

    async def register_suggestion(self, event_type, agent: SAModuleAgent, suggestion: SACommand):
        """Registers a suggestion from an agent for a specific event."""
        async with self._suggestion_buffer_lock:
            if self._verbose: logging.info(f"Registering Suggestion from SA Agent: {agent.get_agent()} for event: {event_type}")
            self._buffer[event_type].append((agent, suggestion))

    async def set_event_waited(self, event_type):
        """Registers event to be waited"""
        if not self._event_waited:
            if self._verbose: logging.info(f"Set notification when all suggestiones are being received for event: {event_type}")
            self._event_waited = event_type

    #TODO maybe should define dict using events as keys to collect notifications for agents per events
    async def notify_all_suggestions_done_for_agent(self, saa : SAModuleAgent, event_type):
        """SA Agent notification that has registered all the suggestions for event_type"""
        async with self._expected_agents_lock:
            try:
                self._event_notifications[saa].set()
                if self._verbose: logging.info(f"SA Agent: {saa.get_agent()} notifies all suggestions registered for event: {event_type}")
                await self._notify_arbitrator(event_type)
            except:
                if self._verbose: logging.error(f"SAModuleAgent: {saa.get_agent()} not found on notifications awaited")

    async def _notify_arbitrator(self, event_type):
        """Checking if is should notify arbitrator that all suggestions for event_type have been received"""
        if event_type != self._event_waited:
            return
        
        async with self._arbitrator_notification_lock:
            async with self._expected_agents_lock:
                expected_agents = self._expected_agents.get(event_type, [])  # Get the expected agents for this event type
                # Check if all expected agents have sent their notifications
                all_received = all(self._event_notifications[agent].is_set() for agent in expected_agents if agent in self._event_notifications)
                if all_received:
                    self._arbitrator_notification.set()
                    self._event_waited = None
                    await self._reset_notifications_for_agents(expected_agents)                

    async def _reset_notifications_for_agents(self, agents):
        """Reset notifications for SA Agents"""
        for agent in agents:
            self._event_notifications[agent].clear()

    async def get_suggestions(self, event_type):
        """Retrieves all suggestions registered for a given event."""
        async with self._suggestion_buffer_lock:
            async with  self._expected_agents_lock:
                if self._verbose: logging.info(f"Retrieving all sugestions for event: {event_type}")
                return self._buffer.get(event_type, [])

    async def clear_suggestions(self, event_type):
        """Clears all suggestions stored for a given event."""
        async with self._lock:
            if event_type in self._buffer:
                del self._buffer[event_type]
                del self._expected_agents[event_type]
    
