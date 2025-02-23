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
    
    @abstractmethod 
    async def start_beacon(self):
        pass
    
    @abstractmethod 
    async def stop_beacon(self):
        pass
    
    @abstractmethod 
    async def modify_beacon_frequency(self, frequency):
        pass
    
    @abstractmethod
    async def subscribe_beacon_listener(self, listener):
        pass

class ExternalConnectionServiceException(Exception):
    pass 

def factory_connection_service(con_serv, cm, addr) -> ExternalConnectionService:
    from nebula.core.network.externalconnection.nebuladiscoveryservice import NebulaConnectionService
    
    CONNECTION_SERVICES = {
        "nebula": NebulaConnectionService,
    }
    
    con_serv = CONNECTION_SERVICES.get(con_serv, NebulaConnectionService)
    
    if con_serv:
        return con_serv(cm, addr)
    else:
         raise ExternalConnectionServiceException(f"Connection Service {con_serv} not found")