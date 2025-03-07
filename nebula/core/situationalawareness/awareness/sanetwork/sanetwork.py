import asyncio
import logging
from nebula.core.utils.locker import Locker
from nebula.core.situationalawareness.awareness.sanetwork.neighborpolicies.neighborpolicy import factory_NeighborPolicy
from nebula.addons.functions import print_msg_box
from nebula.core.nebulaevents import BeaconRecievedEvent
from nebula.core.eventmanager import EventManager
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.network.communications import CommunicationsManager
    from nebula.core.situationalawareness.awareness.samodule import SAModule
    
RESTRUCTURE_COOLDOWN = 5    
    
class SANetwork():
    def __init__(
        self,
        sam: "SAModule",
        communication_manager: "CommunicationsManager",
        addr, 
        topology, 
        strict_topology=True
    ):
        print_msg_box(
            msg=f"Starting Network SA\nTopology: {topology}\nStrict: {strict_topology}",
            indent=2,
            title="Network SA module",
        )
        self._sam = sam
        self._cm = communication_manager
        self._addr = addr
        self._topology = topology
        self._strict_topology = strict_topology
        self._neighbor_policy = factory_NeighborPolicy(topology)
        self._restructure_process_lock = Locker(name="restructure_process_lock")
        self._restructure_cooldown = 0
        
    @property
    def sam(self):
        return self._sam    
        
    @property
    def cm(self):
        return self._cm    
        
    @property    
    def np(self):
        return self._neighbor_policy
    
    async def init(self):
        if not self.sam.is_additional_participant():
            logging.info("Deploying External Connection Service")
            await self.cm.start_external_connection_service()
            await EventManager.get_instance().subscribe_node_event(BeaconRecievedEvent, self.beacon_received)
            await self.cm.start_beacon()
        else:
            logging.info("Deploying External Connection Service | No running")
            await self.cm.start_external_connection_service(run_service=False)
        

        logging.info("Building neighbor policy configuration..")
        self.np.set_config([
            await self.cm.get_addrs_current_connections(only_direct=True, myself=False),
            await self.cm.get_addrs_current_connections(only_direct=False, only_undirected=False, myself=False),
            self._addr,
            self,
        ])
        
    async def module_actions(self):
        logging.info("SA Network evaluating current scenario")
        await self._check_external_connection_service_status()
        await self._analize_topology_robustness()    
        
     
    """                                                     ###############################
                                                            #       NEIGHBOR POLICY       #
                                                            ###############################
    """
    async def register_node(self, node, neighbor=False, remove=False):
        if not neighbor:
            self.meet_node(node)
        else:
            self.update_neighbors(node, remove)

    def meet_node(self, node):
        if node != self._addr:
            self.np.meet_node(node)

    def update_neighbors(self, node, remove=False):
        self.np.update_neighbors(node, remove)
        if not remove:
            self.np.meet_node(node)

    def get_nodes_known(self, neighbors_too=False, neighbors_only=False):
        return self.np.get_nodes_known(neighbors_too, neighbors_only)

    async def neighbors_left(self):
        return len(await self.cm.get_addrs_current_connections(only_direct=True, myself=False)) > 0

    def accept_connection(self, source, joining=False):
        return self.np.accept_connection(source, joining)

    def need_more_neighbors(self):
        return self.np.need_more_neighbors()

    def get_actions(self):
        return self.np.get_actions()
    
    """                                                     ###############################
                                                            # EXTERNAL CONNECTION SERVICE #
                                                            ###############################
    """
    
    async def _check_external_connection_service_status(self):
        if not await self.cm.is_external_connection_service_running():
            logging.info("🔄 External Service not running | Starting service...")
            await self.cm.init_external_connection_service()
            await EventManager.get_instance().subscribe_node_event(BeaconRecievedEvent, self.beacon_received)
            await self.cm.start_beacon()
    
    async def experiment_finish(self):
        await self.cm.stop_external_connection_service()
    
    async def beacon_received(self, beacon_recieved_event : BeaconRecievedEvent):
        addr, geoloc = await beacon_recieved_event.get_event_data()
        latitude, longitude = geoloc
        self.meet_node(addr)
        #logging.info(f"Beacon received SANetwork, source: {addr}, geolocalization: {latitude},{longitude}")        
        
    """                                                     ###############################
                                                            #    REESTRUCTURE TOPOLOGY    #
                                                            ###############################
    """

    def _update_restructure_cooldown(self):
        if self._restructure_cooldown:
            self._restructure_cooldown = (self._restructure_cooldown + 1) % RESTRUCTURE_COOLDOWN

    def _restructure_available(self):
        if self._restructure_cooldown:
            logging.info("Reestructure on cooldown")
        return self._restructure_cooldown == 0

    def get_restructure_process_lock(self):
        return self._restructure_process_lock    
    
    async def _analize_topology_robustness(self):
        logging.info("🔄 Analizing node network robustness...")
        if not self._restructure_process_lock.locked():
            if not await self.neighbors_left():
                logging.info("No Neighbors left | reconnecting with Federation")
                await self.reconnect_to_federation()
            elif self.np.need_more_neighbors() and self._restructure_available():
                logging.info("Insufficient Robustness | Upgrading robustness | Searching for more connections")
                self._update_restructure_cooldown()
                possible_neighbors = self.np.get_nodes_known(neighbors_too=False)
                possible_neighbors = await self.cm.apply_restrictions(possible_neighbors)
                if not possible_neighbors:
                    logging.info("All possible neighbors using nodes known are restricted...")
                else:
                    pass
                    # asyncio.create_task(self.upgrade_connection_robustness(possible_neighbors))
            else:
                logging.info("Sufficient Robustness | no actions required")
        else:
            logging.info("❗️ Reestructure/Reconnecting process already running...")

    async def reconnect_to_federation(self):
        self._restructure_process_lock.acquire()
        await self.cm.clear_restrictions()
        await asyncio.sleep(120)
        # If we got some refs, try to reconnect to them
        if len(self.np.get_nodes_known()) > 0:
            logging.info("Reconnecting | Addrs availables")
            await self.sam.nm.start_late_connection_process(
                connected=False, msg_type="discover_nodes", addrs_known=self.np.get_nodes_known()
            )
        else:
            logging.info("Reconnecting | NO Addrs availables")
            await self.sam.nm.start_late_connection_process(connected=False, msg_type="discover_nodes")
        self._restructure_process_lock.release()

    async def upgrade_connection_robustness(self, possible_neighbors):
        self._restructure_process_lock.acquire()
        # addrs_to_connect = self.neighbor_policy.get_nodes_known(neighbors_too=False)
        # If we got some refs, try to connect to them
        if len(possible_neighbors) > 0:
            logging.info(f"Reestructuring | Addrs availables | addr list: {possible_neighbors}")
            await self.sam.nm.start_late_connection_process(
                connected=True, msg_type="discover_nodes", addrs_known=possible_neighbors
            )
        else:
            logging.info("Reestructuring | NO Addrs availables")
            await self.sam.nm.start_late_connection_process(connected=True, msg_type="discover_nodes")
        self._restructure_process_lock.release()

    async def stop_connections_with_federation(self):
        await asyncio.sleep(200)
        logging.info("### DISCONNECTING FROM FEDERATON ###")
        neighbors = self.np.get_nodes_known(neighbors_only=True)
        for n in neighbors:
            await self.cm.add_to_blacklist(n)
        for n in neighbors:
            await self.cm.disconnect(n, mutual_disconnection=False, forced=True)    