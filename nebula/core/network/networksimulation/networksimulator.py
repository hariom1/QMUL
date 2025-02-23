import asyncio
from abc import ABC, abstractmethod

class NetworkSimulator(ABC):

    @abstractmethod 
    async def set_thresholds(self, threshold : dict):
        pass

    @abstractmethod 
    def set_network_conditions(self, dest_addr, distance):
        pass
    
    @abstractmethod 
    def clear_network_conditions(self):
        pass
    

class NetworkSimulatorException(Exception):
    pass 

def factory_connection_service(net_sim, cm, addr) -> NetworkSimulator:
    from nebula.core.network.networksimulation.nebulanetworksimulator import NebulaNS
    
    SIMULATION_SERVICES = {
        "nebula": NebulaNS,
    }
    
    con_serv = SIMULATION_SERVICES.get(net_sim, NebulaNS)
    
    if con_serv:
        return con_serv(cm, addr)
    else:
         raise NetworkSimulatorException(f"Network Simulator {net_sim} not found")