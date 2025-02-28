from abc import ABC, abstractmethod
import asyncio

class AddonEvent(ABC):
    @abstractmethod
    async def get_event_data(self):
        pass
    
class NodeEvent(ABC):
    @abstractmethod
    async def get_event_data(self):
        pass
    
    @abstractmethod
    async def is_concurrent(self):
        pass

class MessageEvent:
    def __init__(self, message_type, source, message):
        self.source = source
        self.message_type = message_type
        self.message = message

class AggregationEvent(NodeEvent):
    def __init__(self, updates : dict, expected_nodes : set, missing_nodes : set):
        self._updates = updates
        self._expected_nodes = expected_nodes
        self._missing_nodes = missing_nodes
        
    def __str__(self):
        return "Aggregation Ready"
        
    async def get_event_data(self) -> tuple[dict, set, set]:
        return (self._updates, self._expected_nodes, self._missing_nodes)
    
    async def is_concurrent(self) -> bool:
        return False 
    
class GPSEvent(AddonEvent):
    def __init__(self, distances : dict):
        self.distances = distances
    
    def __str__(self):
        return "GPSEvent"    
        
    async def get_event_data(self) -> dict:
        return self.distances.copy()