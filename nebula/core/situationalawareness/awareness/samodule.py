import asyncio
import logging
from typing import TYPE_CHECKING

from nebula.addons.functions import print_msg_box
from nebula.core.situationalawareness.awareness.sanetwork.sanetwork import SANetwork
from nebula.core.situationalawareness.awareness.satraining.satraining import SATraining
from nebula.core.situationalawareness.awareness.GPS.gpsmodule import factory_gpsmodule
from nebula.core.utils.locker import Locker

if TYPE_CHECKING:
    from nebula.core.situationalawareness.nodemanager import NodeManager

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
        self._situational_awareness_network = SANetwork(self, self.cm, self._addr, self._topology)
        self._situational_awareness_trainning = SATraining(self,"hybrid", "fastreboot")
        self._restructure_process_lock = Locker(name="restructure_process_lock")
        self._restructure_cooldown = 0
        self._gpsmodule = factory_gpsmodule("nebula", self, self._addr)

    @property
    def nm(self):
        return self._node_manager

    @property
    def san(self):
        return self._situational_awareness_network

    @property
    def cm(self):
        return self.nm.engine.cm
    
    @property
    def gps(self):
        return self._gpsmodule

    async def init(self):
        if not self.is_additional_participant():
            await self.gps.start()
        await self.san.init()
          
    def is_additional_participant(self):
        return self.nm.is_additional_participant()

    async def experiment_finish(self):
        await self.san.experiment_finish()
        
    async def get_geoloc(self):
        latitude = self.nm.config.participant["mobility_args"]["latitude"]
        longitude = self.nm.config.participant["mobility_args"]["longitude"]
        return (latitude, longitude)    
    
    async def mobility_actions(self):
        await self.verify_gps_service()
        await self.san.module_actions()    

    """                                                     ###############################
                                                            #         GPS SERVICE         #
                                                            ###############################
    """

    async def verify_gps_service(self):
        if not await self.gps.is_running():
            await self.gps.start()

    """                                                     ###############################
                                                            #    REESTRUCTURE TOPOLOGY    #
                                                            ###############################
    """

    # def _update_restructure_cooldown(self):
    #     if self._restructure_cooldown:
    #         self._restructure_cooldown = (self._restructure_cooldown + 1) % RESTRUCTURE_COOLDOWN

    # def _restructure_available(self):
    #     if self._restructure_cooldown:
    #         logging.info("Reestructure on cooldown")
    #     return self._restructure_cooldown == 0

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

    # """                                                     ###############################
    #                                                         #         ROBUSTNESS          #
    #                                                         ###############################
    # """

    # async def beacon_received(self, addr, geoloc):
    #     latitude, longitude = geoloc
    #     self.meet_node(addr)
    #     logging.info(f"Beacon received SAModule, source: {addr}, geolocalization: {latitude},{longitude}")

    # async def check_external_connection_service_status(self):
    #     if not await self.cm.is_external_connection_service_running():
    #         logging.info("🔄 External Service not running | Starting service...")
    #         await self.cm.init_external_connection_service()
    #         await self.cm.subscribe_beacon_listener(self.beacon_received)
    #         await self.cm.start_beacon()

    # async def analize_topology_robustness(self):
    #     logging.info("🔄 Analizing node network robustness...")
    #     if not self._restructure_process_lock.locked():
    #         if not await self.neighbors_left():
    #             logging.info("No Neighbors left | reconnecting with Federation")
    #             await self.reconnect_to_federation()
    #         elif self.np.need_more_neighbors() and self._restructure_available():
    #             logging.info("Insufficient Robustness | Upgrading robustness | Searching for more connections")
    #             self._update_restructure_cooldown()
    #             possible_neighbors = self.np.get_nodes_known(neighbors_too=False)
    #             possible_neighbors = await self.cm.apply_restrictions(possible_neighbors)
    #             if not possible_neighbors:
    #                 logging.info("All possible neighbors using nodes known are restricted...")
    #             else:
    #                 pass
    #                 # asyncio.create_task(self.upgrade_connection_robustness(possible_neighbors))
    #         else:
    #             logging.info("Sufficient Robustness | no actions required")
    #     else:
    #         logging.info("❗️ Reestructure/Reconnecting process already running...")

    # async def reconnect_to_federation(self):
    #     self._restructure_process_lock.acquire()
    #     await self.cm.clear_restrictions()
    #     await asyncio.sleep(120)
    #     # If we got some refs, try to reconnect to them
    #     if len(self.np.get_nodes_known()) > 0:
    #         logging.info("Reconnecting | Addrs availables")
    #         await self.nm.start_late_connection_process(
    #             connected=False, msg_type="discover_nodes", addrs_known=self.np.get_nodes_known()
    #         )
    #     else:
    #         logging.info("Reconnecting | NO Addrs availables")
    #         await self.nm.start_late_connection_process(connected=False, msg_type="discover_nodes")
    #     self._restructure_process_lock.release()

    # async def upgrade_connection_robustness(self, possible_neighbors):
    #     self._restructure_process_lock.acquire()
    #     # addrs_to_connect = self.neighbor_policy.get_nodes_known(neighbors_too=False)
    #     # If we got some refs, try to connect to them
    #     if len(possible_neighbors) > 0:
    #         logging.info(f"Reestructuring | Addrs availables | addr list: {possible_neighbors}")
    #         await self.nm.start_late_connection_process(
    #             connected=True, msg_type="discover_nodes", addrs_known=possible_neighbors
    #         )
    #     else:
    #         logging.info("Reestructuring | NO Addrs availables")
    #         await self.nm.start_late_connection_process(connected=True, msg_type="discover_nodes")
    #     self._restructure_process_lock.release()

    # async def stop_connections_with_federation(self):
    #     await asyncio.sleep(400)
    #     logging.info("### DISCONNECTING FROM FEDERATON ###")
    #     neighbors = self.np.get_nodes_known(neighbors_only=True)
    #     for n in neighbors:
    #         await self.cm.add_to_blacklist(n)
    #     for n in neighbors:
    #         await self.cm.disconnect(n, mutual_disconnection=False, forced=True)
