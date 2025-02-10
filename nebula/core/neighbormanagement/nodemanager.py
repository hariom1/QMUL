import asyncio
import logging
from typing import TYPE_CHECKING

from nebula.addons.functions import print_msg_box
from nebula.core.neighbormanagement.candidateselection.candidateselector import factory_CandidateSelector
from nebula.core.neighbormanagement.fastreboot import FastReboot
from nebula.core.neighbormanagement.modelhandlers.modelhandler import factory_ModelHandler
from nebula.core.neighbormanagement.momentum import Momentum
from nebula.core.neighbormanagement.neighborpolicies.neighborpolicy import factory_NeighborPolicy
from nebula.core.utils.locker import Locker

if TYPE_CHECKING:
    from nebula.core.engine import Engine

RESTRUCTURE_COOLDOWN = 5


class NodeManager:
    def __init__(
        self,
        aditional_participant,
        topology,
        model_handler,
        push_acceleration,
        engine: "Engine",
        fastreboot=False,
        momentum=False,
    ):
        self._aditional_participant = aditional_participant
        self.topology = "fully"  # topology
        print_msg_box(
            msg=f"Starting NodeManager module...\nTopology: {self.topology}", indent=2, title="NodeManager module"
        )
        logging.info("🌐  Initializing Node Manager")
        self._engine = engine
        self.config = engine.get_config()
        logging.info("Initializing Neighbor policy")
        self._neighbor_policy = factory_NeighborPolicy(self.topology)
        logging.info("Initializing Candidate Selector")
        self._candidate_selector = factory_CandidateSelector(self.topology)
        logging.info("Initializing Model Handler")
        self._model_handler = factory_ModelHandler(model_handler)
        self._update_neighbors_lock = Locker(name="_update_neighbors_lock", async_lock=True)
        self.late_connection_process_lock = Locker(name="late_connection_process_lock")
        self.pending_confirmation_from_nodes = set()
        self.pending_confirmation_from_nodes_lock = Locker(name="pending_confirmation_from_nodes_lock", async_lock=True)
        self.accept_candidates_lock = Locker(name="accept_candidates_lock")
        self.recieve_offer_timer = 5
        self._restructure_process_lock = Locker(name="restructure_process_lock")
        self.restructure = False
        self._restructure_cooldown = 0
        self.discarded_offers_addr_lock = Locker(name="discarded_offers_addr_lock")
        self.discarded_offers_addr = []
        self._push_acceleration = push_acceleration

        self.synchronizing_rounds = False

        self._fast_reboot_status = fastreboot
        self._momemtum_status = momentum

    @property
    def engine(self):
        return self._engine

    @property
    def neighbor_policy(self):
        return self._neighbor_policy

    @property
    def candidate_selector(self):
        return self._candidate_selector

    @property
    def model_handler(self):
        return self._model_handler

    @property
    def fr(self):
        return self._fastreboot

    @property
    def mom(self):
        return self._momemtum

    def fast_reboot_on(self):
        return self._fast_reboot_status

    def _update_restructure_cooldown(self):
        if self._restructure_cooldown:
            self._restructure_cooldown = (self._restructure_cooldown + 1) % RESTRUCTURE_COOLDOWN

    def _restructure_available(self):
        if self._restructure_cooldown:
            logging.info("Reestructure on cooldown")
        return self._restructure_cooldown == 0

    def get_push_acceleration(self):
        return self._push_acceleration

    def get_restructure_process_lock(self):
        return self._restructure_process_lock

    def set_synchronizing_rounds(self, status):
        self.synchronizing_rounds = status

    def get_syncrhonizing_rounds(self):
        return self.synchronizing_rounds

    async def set_rounds_pushed(self, rp):
        if self.fast_reboot_on():
            self.fr.set_rounds_pushed(rp)

    def still_waiting_for_candidates(self):
        return not self.accept_candidates_lock.locked()

    async def set_configs(self):
        """
        neighbor_policy config:
            - direct connections a.k.a neighbors
            - all nodes known
            - self addr

        model_handler config:
            - self total rounds
            - self current round
            - self epochs

        candidate_selector config:
            - self model loss
            - self weight distance
            - self weight hetereogeneity
        """
        logging.info("Building neighbor policy configuration..")
        self.neighbor_policy.set_config([
            await self.engine.cm.get_addrs_current_connections(only_direct=True, myself=False),
            await self.engine.cm.get_addrs_current_connections(only_direct=False, only_undirected=False, myself=False),
            self.engine.addr,
            self,
        ])
        logging.info("Building candidate selector configuration..")
        self.candidate_selector.set_config([0, 0.5, 0.5])
        # self.engine.trainer.get_loss(), self.config.participant["molibity_args"]["weight_distance"], self.config.participant["molibity_args"]["weight_het"]

        if self._fast_reboot_status:
            self._fastreboot = FastReboot(self)

        self._momemtum = None
        if self._momemtum_status and not self._aditional_participant:
            self._momemtum = Momentum(
                self, self.neighbor_policy.get_nodes_known(neighbors_only=True), dispersion_penalty=False
            )

    def late_config(self):
        if self._momemtum_status:
            self._momemtum = Momentum(
                self, self.neighbor_policy.get_nodes_known(neighbors_only=True), dispersion_penalty=False
            )

            ##############################
            #      WEIGHT STRATEGIES     #
            ##############################

    async def update_learning_rate(self, new_lr):
        await self.engine.update_model_learning_rate(new_lr)

    async def register_late_neighbor(self, addr, joinning_federation=False):
        logging.info(f"Registering | late neighbor: {addr}, joining: {joinning_federation}")
        self.meet_node(addr)
        await self.update_neighbors(addr)
        if self._momemtum_status:
            await self.mom.update_node(addr)
        if joinning_federation:
            if self.fast_reboot_on():
                await self.fr.add_fastReboot_addr(addr)

    async def apply_weight_strategy(self, updates: dict):
        if self.fast_reboot_on():
            await self.fr.apply_weight_strategy(updates)
        if self._momemtum:
            await self._momemtum.calculate_momentum_weights(updates)

            ##############################
            #        CONNECTIONS         #
            ##############################

    def accept_connection(self, source, joining=False):
        return self.neighbor_policy.accept_connection(source, joining)

    async def add_pending_connection_confirmation(self, addr):
        await self._update_neighbors_lock.acquire_async()
        await self.pending_confirmation_from_nodes_lock.acquire_async()
        if addr not in self.neighbor_policy.get_nodes_known(neighbors_only=True):
            logging.info(f" Addition | pending connection confirmation from: {addr}")
            self.pending_confirmation_from_nodes.add(addr)
        await self.pending_confirmation_from_nodes_lock.release_async()
        await self._update_neighbors_lock.release_async()

    async def _remove_pending_confirmation_from(self, addr):
        await self.pending_confirmation_from_nodes_lock.acquire_async()
        self.pending_confirmation_from_nodes.discard(addr)
        await self.pending_confirmation_from_nodes_lock.release_async()

    async def clear_pending_confirmations(self):
        await self.pending_confirmation_from_nodes_lock.acquire_async()
        self.pending_confirmation_from_nodes.clear()
        await self.pending_confirmation_from_nodes_lock.release_async()

    async def waiting_confirmation_from(self, addr):
        await self.pending_confirmation_from_nodes_lock.acquire_async()
        found = addr in self.pending_confirmation_from_nodes
        await self.pending_confirmation_from_nodes_lock.release_async()
        return found

    async def confirmation_received(self, addr, confirmation=False):
        logging.info(f" Update | connection confirmation received from: {addr} | confirmation: {confirmation}")
        if confirmation:
            await self.engine.cm.connect(addr, direct=True)
            await self.update_neighbors(addr)
        else:
            self._remove_pending_confirmation_from(addr)

    def add_to_discarded_offers(self, addr_discarded):
        self.discarded_offers_addr_lock.acquire()
        self.discarded_offers_addr.append(addr_discarded)
        self.discarded_offers_addr_lock.release()

    def need_more_neighbors(self):
        return self.neighbor_policy.need_more_neighbors()

    def get_actions(self):
        return self.neighbor_policy.get_actions()

    async def update_neighbors(self, node, remove=False):
        logging.info(f"Update neighbor | node addr: {node} | remove: {remove}")
        await self._update_neighbors_lock.acquire_async()
        self.neighbor_policy.update_neighbors(node, remove)
        # self.timer_generator.update_node(node, remove)
        if remove:
            if self._fast_reboot_status:
                self.fr.discard_fastreboot_for(node)
            if self._momemtum_status:
                await self.mom.update_node(node, remove=True)
        else:
            self.neighbor_policy.meet_node(node)
            if self._momemtum_status:
                await self.mom.update_node(node)
            self._remove_pending_confirmation_from(node)
        await self._update_neighbors_lock.release_async()

    async def neighbors_left(self):
        return len(await self.engine.cm.get_addrs_current_connections(only_direct=True, myself=False)) > 0

    def meet_node(self, node):
        if node != self.engine.addr:
            logging.info(f"Update nodes known | addr: {node}")
            self.neighbor_policy.meet_node(node)

    def get_nodes_known(self, neighbors_too=False):
        return self.neighbor_policy.get_nodes_known(neighbors_too)

    def accept_model_offer(self, source, decoded_model, rounds, round, epochs, n_neighbors, loss):
        if not self.accept_candidates_lock.locked():
            logging.info(f"🔄 Processing offer from {source}...")
            # model_accepted = True#self.model_handler.accept_model(decoded_model)
            # if source == "192.168.50.8:45007":
            model_accepted = self.model_handler.accept_model(decoded_model)
            self.model_handler.set_config(config=(rounds, round, epochs, self))
            if model_accepted:
                self.candidate_selector.add_candidate((source, n_neighbors, loss))
                return True
        else:
            return False

    async def get_trainning_info(self):
        return await self.model_handler.get_model(None)

    def add_candidate(self, source, n_neighbors, loss):
        if not self.accept_candidates_lock.locked():
            self.candidate_selector.add_candidate((source, n_neighbors, loss))

    async def currently_reestructuring(self):
        return self._restructure_process_lock.locked()

    async def stop_not_selected_connections(self):
        try:
            with self.discarded_offers_addr_lock:
                if len(self.discarded_offers_addr) > 0:
                    self.discarded_offers_addr = set(
                        self.discarded_offers_addr
                    ) - await self.engine.cm.get_addrs_current_connections(only_direct=True, myself=False)
                    logging.info(
                        f"Interrupting connections | discarded offers | nodes discarded: {self.discarded_offers_addr}"
                    )
                    for addr in self.discarded_offers_addr:
                        await self.engine.cm.disconnect(addr, mutual_disconnection=True)
                        await asyncio.sleep(1)
                    self.discarded_offers_addr = []
        except asyncio.CancelledError:
            pass

    async def check_external_connection_service_status(self):
        logging.info("🔄 Checking external connection service status...")
        n = await self.neighbors_left()
        ecs = await self.engine.cm.is_external_connection_service_running()
        ss = self.engine.get_sinchronized_status()
        action = None
        logging.info(f"Stats | neighbors: {n} | service running: {ecs} | synchronized status: {ss}")
        if not await self.neighbors_left() and await self.engine.cm.is_external_connection_service_running():
            logging.info("❗️  Isolated node | Shutdowning service required")
            action = lambda: self.engine.cm.stop_external_connection_service()
        elif (
            await self.neighbors_left()
            and not await self.engine.cm.is_external_connection_service_running()
            and self.engine.get_sinchronized_status()
        ):
            logging.info("🔄 NOT isolated node | Service not running | Starting service...")
            action = lambda: self.engine.cm.init_external_connection_service()
        return action

    async def start_late_connection_process(self, connected=False, msg_type="discover_join", addrs_known=None):
        """
        This function represents the process of discovering the federation and stablish the first
        connections with it. The first step is to send the DISCOVER_JOIN/NODES message to look for nodes,
        the ones that receive that message will send back a OFFER_MODEL/METRIC message. It contains info to do
        a selection process among candidates to later on connect to the best ones.
        The process will repeat until at least one candidate is found and the process will be locked
        to avoid concurrency.
        """
        logging.info("🌐  Initializing late connection process..")

        self.late_connection_process_lock.acquire()
        best_candidates = []
        self.candidate_selector.remove_candidates()
        await self.clear_pending_confirmations()

        # find federation and send discover
        await self.engine.cm.stablish_connection_to_federation(msg_type, addrs_known)

        # wait offer
        logging.info(f"Waiting: {self.recieve_offer_timer}s to receive offers from federation")
        await asyncio.sleep(self.recieve_offer_timer)

        # acquire lock to not accept late candidates
        self.accept_candidates_lock.acquire()

        if self.candidate_selector.any_candidate():
            logging.info("Candidates found to connect to...")
            # create message to send to candidates selected
            if not connected:
                msg = self.engine.cm.create_message("connection", "late_connect")
            else:
                msg = self.engine.cm.create_message("connection", "restructure")

            best_candidates = self.candidate_selector.select_candidates()
            logging.info(f"Candidates | {[addr for addr, _, _ in best_candidates]}")
            # candidates not choosen --> disconnect
            try:
                for addr, _, _ in best_candidates:
                    await self.add_pending_connection_confirmation(addr)
                    await self.engine.cm.send_message(addr, msg)
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                await self.update_neighbors(addr, remove=True)
                pass
            self.accept_candidates_lock.release()
            self.late_connection_process_lock.release()
            self.candidate_selector.remove_candidates()
            asyncio.create_task(self.stop_connections_with_federation())
        # if no candidates, repeat process
        else:
            logging.info("❗️  No Candidates found...")
            self.accept_candidates_lock.release()
            self.late_connection_process_lock.release()
            if not connected:
                logging.info("❗️  repeating process...")
                await self.start_late_connection_process(connected, msg_type, addrs_known)

                ##############################
                #         ROBUSTNESS         #
                ##############################

    async def check_robustness(self):
        logging.info("🔄 Analizing node network robustness...")
        logging.info(f"Synchronization status: {self.engine.get_sinchronized_status()} | got neighbors: {await self.neighbors_left()}")
        if not self._restructure_process_lock.locked():
            if not await self.neighbors_left():
                logging.info("No Neighbors left | reconnecting with Federation")
                #TODO comprobar q funcione correctamente
                self.engine.update_sinchronized_status(False)
                self.set_synchronizing_rounds(True)
                await asyncio.sleep(120)
                await self.reconnect_to_federation()
            elif (
                self.neighbor_policy.need_more_neighbors()
                and self.engine.get_sinchronized_status()
                and self._restructure_available()
            ):
                logging.info("Insufficient Robustness | Upgrading robustness | Searching for more connections")
                self._update_restructure_cooldown()
                possible_neighbors = self.neighbor_policy.get_nodes_known(neighbors_too=False)
                possible_neighbors = await self.engine.cm.apply_restrictions(possible_neighbors)
                if not possible_neighbors:
                    logging.info("All possible neighbors using nodes known are restricted...")                                
                    #asyncio.create_task(self.upgrade_connection_robustness(possible_neighbors)) 
            else:
                if not self.engine.get_sinchronized_status():
                    logging.info("Device not synchronized with federation")  
                else:
                    logging.info("Sufficient Robustness | no actions required")
        else:
            logging.info("❗️ Reestructure/Reconnecting process already running...")

    async def reconnect_to_federation(self):
        # If we got some refs, try to reconnect to them
        self._restructure_process_lock.acquire()
        await self.engine.cm.clear_restrictions()                   
        if len(self.neighbor_policy.get_nodes_known()) > 0:
            logging.info("Reconnecting | Addrs availables")
            await self.start_late_connection_process(connected=False, msg_type="discover_nodes", addrs_known=self.neighbor_policy.get_nodes_known())
        else:
            logging.info("Reconnecting | NO Addrs availables")
            await self.start_late_connection_process(connected=False, msg_type="discover_nodes")
        self._restructure_process_lock.release()

    async def upgrade_connection_robustness(self, possible_neighbors):
        self._restructure_process_lock.acquire()
        #addrs_to_connect = self.neighbor_policy.get_nodes_known(neighbors_too=False)
        # If we got some refs, try to connect to them
        if len(possible_neighbors) > 0:
            logging.info(f"Reestructuring | Addrs availables | addr list: {possible_neighbors}")
            await self.start_late_connection_process(connected=True, msg_type="discover_nodes", addrs_known=possible_neighbors)
        else:
            logging.info("Reestructuring | NO Addrs availables")
            await self.start_late_connection_process(connected=True, msg_type="discover_nodes")
        self._restructure_process_lock.release()
        
    async def stop_connections_with_federation(self):
        await asyncio.sleep(100)
        logging.info("### DISCONNECTING FROM FEDERATON ###")
        neighbors = self.neighbor_policy.get_nodes_known(neighbors_only=True)
        for n in neighbors: 
            await self.engine.cm.add_to_blacklist(n)
        for n in neighbors:
            await self.engine.cm.disconnect(n, mutual_disconnection=False, forced=True)
