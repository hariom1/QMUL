import asyncio
import logging
from typing import TYPE_CHECKING

from nebula.addons.functions import print_msg_box
from nebula.core.situationalawareness.candidateselection.candidateselector import factory_CandidateSelector
from nebula.core.situationalawareness.modelhandlers.modelhandler import factory_ModelHandler
from nebula.core.situationalawareness.momentum import Momentum
from nebula.core.situationalawareness.awareness.samodule import SAModule
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
        engine: "Engine",
    ):
        self._aditional_participant = aditional_participant
        self.topology = topology
        print_msg_box(
            msg=f"Starting NodeManager module...", indent=2, title="NodeManager module"
        )
        logging.info("🌐  Initializing Node Manager")
        self._engine = engine
        self.config = engine.get_config()
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
        self.discarded_offers_addr_lock = Locker(name="discarded_offers_addr_lock")
        self.discarded_offers_addr = []

        self._desc_done = False #TODO remove
        
        self._situational_awareness_module = SAModule(self, self.engine.addr, topology)

    @property
    def engine(self):
        return self._engine

    @property
    def candidate_selector(self):
        return self._candidate_selector

    @property
    def model_handler(self):
        return self._model_handler

    @property
    def sam(self):
        return self._situational_awareness_module

    def is_additional_participant(self):
        return self._aditional_participant

    async def set_configs(self):
        """
        model_handler config:
            - self total rounds
            - self current round
            - self epochs

        candidate_selector config:
            - self model loss
            - self weight distance
            - self weight hetereogeneity
        """
        await self.sam.init()
        logging.info("Building candidate selector configuration..")
        self.candidate_selector.set_config([0, 0.5, 0.5])
        # self.engine.trainer.get_loss(), self.config.participant["molibity_args"]["weight_distance"], self.config.participant["molibity_args"]["weight_het"]
        
    async def get_geoloc(self):
        return await self.sam.get_geoloc()
        
    async def experiment_finish(self):
        await self.sam.experiment_finish()        

    """
                ##############################
                #      WEIGHT STRATEGIES     #
                ##############################
    """

    async def register_late_neighbor(self, addr, joinning_federation=False):
        logging.info(f"Registering | late neighbor: {addr}, joining: {joinning_federation}")
        self.sam.meet_node(addr)
        await self.update_neighbors(addr)
        if joinning_federation:
            pass

    """
                ##############################
                #        CONNECTIONS         #
                ##############################
    """

    def get_restructure_process_lock(self):
        return self.sam.get_restructure_process_lock()

    def accept_connection(self, source, joining=False):
        return self.sam.accept_connection(source, joining)
    
    def still_waiting_for_candidates(self):
        return not self.accept_candidates_lock.locked()

    async def add_pending_connection_confirmation(self, addr):
        await self._update_neighbors_lock.acquire_async()
        await self.pending_confirmation_from_nodes_lock.acquire_async()
        if addr not in self.sam.get_nodes_known(neighbors_only=True):
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
        return self.sam.need_more_neighbors()

    def get_actions(self):
        return self.sam.get_actions()

    async def update_neighbors(self, node, remove=False):
        await self._update_neighbors_lock.acquire_async()
        self.sam.update_neighbors(node, remove)
        if remove:
            pass
        else:
            self.sam.meet_node(node)
            self._remove_pending_confirmation_from(node)
        await self._update_neighbors_lock.release_async()

    def meet_node(self, node):
        self.sam.meet_node(node)

    def get_nodes_known(self, neighbors_too=False):
        return self.sam.get_nodes_known(neighbors_too)

    def accept_model_offer(self, source, decoded_model, rounds, round, epochs, n_neighbors, loss):
        if not self.accept_candidates_lock.locked():
            logging.info(f"🔄 Processing offer from {source}...")
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
        connections_stablished = await self.engine.cm.stablish_connection_to_federation(msg_type, addrs_known)

        # wait offer
        #TODO actualizar con la informacion de latencias
        logging.info(f"Connections stablish after finding federation: {connections_stablished}")
        if connections_stablished:
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
            #TODO candidates not choosen --> disconnect
            try:
                for addr, _, _ in best_candidates:
                    await self.add_pending_connection_confirmation(addr)
                    await self.engine.cm.send_message(addr, msg)
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                await self.update_neighbors(addr, remove=True)
                logging.info("Error during stablishment")
            self.accept_candidates_lock.release()
            self.late_connection_process_lock.release()
            self.candidate_selector.remove_candidates()
            if not self._desc_done: #TODO remove
                self._desc_done = True
                asyncio.create_task(self.sam.san.stop_connections_with_federation())
        # if no candidates, repeat process
        else:
            logging.info("❗️  No Candidates found...")
            self.accept_candidates_lock.release()
            self.late_connection_process_lock.release()
            if not connected:
                logging.info("❗️  repeating process...")
                await self.start_late_connection_process(connected, msg_type, addrs_known)
                


