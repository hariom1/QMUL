import asyncio
from abc import ABC, abstractmethod

class GPSModule(ABC):

    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass
    
    @abstractmethod
    async def is_running(self):
        pass

class GPSModuleException(Exception):
    pass

def factory_gpsmodule(gps_module, sam, addr) -> GPSModule:
    from nebula.core.situationalawareness.awareness.GPS.nebulagps import NebulaGPS
    
    GPS_SERVICES = {
        "nebula": NebulaGPS,
    }
    
    gps_module = GPS_SERVICES.get(gps_module, NebulaGPS)
    
    if gps_module:
        return gps_module(sam, addr)
    else:
         raise GPSModuleException(f"GPS Module {gps_module} not found")