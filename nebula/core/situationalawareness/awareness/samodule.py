import asyncio
import logging
from nebula.addons.functions import print_msg_box
from nebula.core.situationalawareness.awareness.sanetwork.sanetwork import SANetwork
from nebula.core.situationalawareness.awareness.satraining.satraining import SATraining
from nebula.core.utils.locker import Locker
from nebula.core.nebulaevents import RoundEndEvent
from nebula.core.eventmanager import EventManager

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.situationalawareness.nodemanager import NodeManager
    from nebula.core.network.communications import CommunicationsManager

RESTRUCTURE_COOLDOWN = 5


class SAModule:
    def __init__(
        self,
        nodemanager,
        addr,
        topology,
    ):
        print_msg_box(
            msg=f"Starting Situational Awareness module...",
            indent=2,
            title="Situational Awareness module",
        )
        logging.info("🌐  Initializing SAModule")
        self._addr = addr
        self._topology = topology
        self._node_manager: NodeManager = nodemanager
        self._situational_awareness_network = SANetwork(self, self._addr, self._topology)
        self._situational_awareness_training = SATraining(self, self._addr, "qds", "fastreboot", verbose=True)
        self._restructure_process_lock = Locker(name="restructure_process_lock")
        self._restructure_cooldown = 0

    @property
    def nm(self):
        return self._node_manager

    @property
    def san(self):
        return self._situational_awareness_network
    
    @property
    def sat(self):
        return self._situational_awareness_training

    @property
    def cm(self):
        return CommunicationsManager.get_instance()
    

    async def init(self):
        await EventManager.get_instance().subscribe_node_event(RoundEndEvent, self._mobility_actions)
        await self.san.init()
        await self.sat.init()

          
    def is_additional_participant(self):
        return self.nm.is_additional_participant()

    async def experiment_finish(self):
        await self.san.experiment_finish()
        
    async def get_geoloc(self):
        latitude = self.nm.config.participant["mobility_args"]["latitude"]
        longitude = self.nm.config.participant["mobility_args"]["longitude"]
        return (latitude, longitude)    
    
    async def _mobility_actions(self, ree : RoundEndEvent):
        logging.info("🔄 Starting additional mobility actions...")
        await self.san.module_actions()
        await self.sat.module_actions()    


    """                                                     ###############################
                                                            #    REESTRUCTURE TOPOLOGY    #
                                                            ###############################
    """

    def get_restructure_process_lock(self):
        return self.san.get_restructure_process_lock()

    """                                                     ###############################
                                                            #          SA NETWORK         #
                                                            ###############################
    """

    async def register_node(self, node, neighbor=False, remove=False):
        await self.san.register_node(self, node, neighbor, remove)

    def meet_node(self, node):
        self.san.meet_node(node)

    def update_neighbors(self, node, remove=False):
        self.san.update_neighbors(node, remove)
        if not remove:
            self.san.meet_node(node)

    def get_nodes_known(self, neighbors_too=False, neighbors_only=False):
        return self.san.get_nodes_known(neighbors_too, neighbors_only)

    async def neighbors_left(self):
        return await self.san.neighbors_left()

    def accept_connection(self, source, joining=False):
        return self.san.accept_connection(source, joining)

    def need_more_neighbors(self):
        return self.san.need_more_neighbors()

    def get_actions(self):
        return self.san.get_actions()

    
