import asyncio
from abc import ABC, abstractmethod

class ExternalConnectionService(ABC):

    @abstractmethod 
    async def start(self):
        pass
    
    @abstractmethod 
    async def stop(self):
        pass
    
    @abstractmethod
    def is_running(self):
        pass
    
    @abstractmethod 
    async def find_federation(self):
        pass