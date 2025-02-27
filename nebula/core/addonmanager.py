import logging
import asyncio
from nebula.addons.functions import print_msg_box
from nebula.addons.mobility import Mobility
from nebula.addons.networksimulation.networksimulator import factory_network_simulator
from nebula.addons.GPS.gpsmodule import factory_gpsmodule
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.engine import Engine

class AddondManager():
    def __init__(self, engine : "Engine", config):
        self._engine = engine
        self._config = config
        self._addons = []
        
    async def deploy_additional_services(self):
        print_msg_box(msg="Deploying Additional Services\n(='.'=)", indent=2, title="Addons Manager")
        if self._config.participant["mobility_args"]["mobility"]:
            mobility = Mobility(self._config, self._engine.cm, self._engine.event_manager)
            self._addons.append(mobility)
            if self._config.participant["network_args"]["simulation"]:
                refresh_conditions_interval = 5
                network_simulation = factory_network_simulator("nebula", self._engine.event_manager, self._engine.cm, refresh_conditions_interval, "eth0", verbose=False)
                self._addons.append(network_simulation) 
            update_interval = 5
            gps = factory_gpsmodule("nebula", self._config, self._engine.event_manager, self._engine.addr, update_interval, verbose=False)
            self._addons.append(gps)
            
        for add in self._addons:
            await add.start()
                
                