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

    def __new__(cls, verbose):
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

    def __init__(self, verbose):
        """Initializes the suggestion buffer with thread-safe synchronization."""
        self._verbose = verbose
        self._buffer : dict[NodeEvent, list[SACommand]] = defaultdict(list)            # {event: [suggestion]}
        self._suggestion_buffer_lock = Locker("suggestion_buffer_lock", async_lock=True)
        self._expected_agents = defaultdict(set)    # {event: {agents}}
        self._expected_agents_lock = Locker("expected_agents_lock", async_lock=True)
        self._event_notifications : dict[SAModuleAgent, asyncio.Event] = {}              

    async def register_event_agents(self, event_type, agent: SAModuleAgent):
        """Registers expected agents for a given event."""
        async with self._expected_agents_lock:
            self._expected_agents[event_type].add(agent)
            if event_type not in self._event_notifications:
                self._event_notifications[agent] = asyncio.Event()

    async def register_suggestion(self, event_type, agent: SAModuleAgent, suggestion: SACommand):
        """Registers a suggestion from an agent for a specific event."""
        async with self._suggestion_buffer_lock:
            self._buffer[event_type].append((agent, suggestion))

    async def notify_all_suggestions_done_for_agent(self, saa : SAModuleAgent):
        async with self._expected_agents_lock:
            try:
                self._event_notifications[saa].set()
            except:
                if self._verbose: logging.error(f"SAModuleAgent: {saa} not found on notifications awaited")
            
    async def get_suggestions(self, event_type):
        """Retrieves all suggestions registered for a given event."""
        async with self._suggestion_buffer_lock:
            return self._buffer.get(event_type, [])

    async def clear_suggestions(self, event_type):
        """Clears all suggestions stored for a given event."""
        async with self._lock:
            if event_type in self._buffer:
                del self._buffer[event_type]
                del self._expected_agents[event_type]
    
    async def clear_sa_agent(self, saa : SAModuleAgent):
        async with self._expected_agents_lock:
            pass
