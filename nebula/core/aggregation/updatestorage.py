import asyncio
import logging
from collections import deque
from typing import Dict, Tuple, Deque
from nebula.core.utils.locker import Locker
import time
from nebula.core.aggregation.aggregator import Aggregator 

class Update():
    def __init__(self, model, weight, source, round, time_received):
        self.model = model
        self.weight = weight
        self.source = source
        self.round = round
        self.time_received = time_received
        
    def __eq__(self, other):
        return self.round == other.round

MAX_UPDATE_BUFFER_SIZE = 1 # Modify to create an historic

class UpdateStorage():
    def __init__(
        self,
        aggregator: Aggregator,
        addr, 
        buffersize=MAX_UPDATE_BUFFER_SIZE
    ):
       self._addr = addr 
       self._aggregator = aggregator
       self._buffersize = buffersize 
       self._updates_storage: Dict[str, Tuple[Update, Deque[Update]]] = {}
       self._updates_storage_lock = Locker(name="updates_storage_lock", async_lock=True)
       self._sources_expected = set()
       self._sources_received = set()
       self._round_updates_lock = Locker(name="round_updates_lock", async_lock=True) # se coge cuando se empieza a comprobar si estan todas las updates
       self._update_federation_lock = Locker(name="update_federation_lock", async_lock=True)
       
    @property
    def us(self):
        return self._updates_storage
    
    @property
    def agg(self):
        return self._aggregator  
       
    async def round_expected_updates(self, federation_nodes: set):
        """
            Initializes the expected updates for the current round.

            This method updates the list of expected sources (`_sources_expected`) for the current training round 
            and ensures that their respective update storage is initialized if they were not previously registered.

            Args:
                federation_nodes (set): A set of node identifiers expected to provide updates in the current round.
        """
        await self._update_federation_lock.acquire_async()
        await self._updates_storage_lock.acquire_async()
        self._sources_expected = federation_nodes.copy()
        self._sources_received.clear()
        
        # Initialize new nodes
        for fn in federation_nodes:
            if fn not in self.us:
                self.us[fn] = (None, deque(maxlen=self._buffersize))
                
        # Clear removed nodes
        removed_nodes = [node for node in self._updates_storage.keys() if node not in federation_nodes]
        for rn in removed_nodes:
            del self._updates_storage[rn]
        
        await self._updates_storage_lock.release_async()
        await self._update_federation_lock.release_async()
        
        # Lock to check if all updates received
        if self._round_updates_lock.locked():
            self._round_updates_lock.release_async()
        
    async def storage_update(self, model, weight, source, round):
        """
            Stores an update in the update queue if it has not been previously received for the same source and round.

            This method ensures that only one update per source and round is stored, avoiding duplicates.
            If all expected updates for the current round have been received, it triggers the `all_updates_received()` method.

            Args:
                model: The model associated with the update.
                weight: The weight assigned to the update.
                source (str): The source identifier of the update.
                round (int): The training round in which the update was received.

            Logs:
                - Stores and logs the update if it's new for the round.
                - Logs a duplicate update if an identical one already exists.
                - Logs missing sources if not all expected updates have been received.
        """
        time_received = time.time()
        if source in self._sources_expected:
            updt = Update(model, weight, source, round, time_received)
            await self._updates_storage_lock.acquire_async()
            if updt in self.us[source][1]:
                logging.info(f"Discard | Alerady received update from source: {source} for round: {round}")
            else:    
                self.us[source][1].append(updt)
                self.us[source][0] = updt
                logging.info(f"Storage Update | source={source} | round={round} | weight={weight} | federation nodes: {self._sources_expected}")
                
                self._sources_received.add(source)
                updates_left = self._sources_expected.difference(self._sources_received)
                logging.info(f"Updates received ({self._sources_received}/{self._sources_expected}) | Missing nodes: {updates_left}")
                if self._round_updates_lock.locked() and not updates_left:
                    await self.all_updates_received()
            await self._updates_storage_lock.release_async()
        else:
            logging.info(f"source: {source} not in expected updates for this Round")
            
    async def get_round_updates(self):
        """
            Retrieves the latest updates received in the current round.

            This method collects updates from all received sources, prioritizing the most recent update
            stored in the queue. If an expected update is missing, it attempts to use the last received 
            update from that source instead.

            Returns:
                dict: A dictionary mapping each source to a tuple `(model, weight)`, containing 
                    the most recent update for that source.

            Logs:
                - Logs missing sources if expected updates have not been received.
                - Logs when a missing update is replaced by the last received update.
        """
        await self._updates_storage_lock.acquire_async()
        updates_missing = self._sources_expected.difference(self._sources_received)
        if updates_missing:
            logging.info(f"Missing updates from sources: {updates_missing}")
        updates = {}
        for sr in self._sources_received:
            source_historic = self.us[sr][1]
            last_updt_received = self.us[sr][0]
            updt: Update = None
            if source_historic:
                updt = source_historic[-1]
            elif last_updt_received:
                logging.info(f"Missing update source: {sr}, using last update received..")
                updt = last_updt_received
            updates[sr] = (updt.model, updt.weight)
        await self._updates_storage_lock.release_async()
        return updates
       
    async def notify_federation_update(self, source, remove=False):
        if not remove:
            if self._round_updates_lock.locked():
                logging.info(f"Source: {source} will be count next round")
            else:
                self._update_source(source, remove)
        # si se quita
        else:
            pass
        # comprobar si he recibido la updt
            # si no la he recibido se descarta de los esperados
            # si la he recibido
                # si antes de la agregacion de esta ronda la uso
    
    async def _clear_removed_sources(self):
        pass
            
    async def _update_source(self, source, remove=False):
        logging.info(f"🔄 Update | remove: {remove} | source: {source}")
        await self._updates_storage_lock.acquire_async()
        if remove:
            self._sources_expected.discard(source)
        else:
            self.us[source] = (None, deque(maxlen=self._buffersize))
            self._sources_expected.add(source)
        logging.info(f"federation nodes expected this round: {self._sources_expected}")
        await self._updates_storage_lock.release_async()
                  
    async def get_round_missing_nodes(self):
        await self._updates_storage_lock.acquire_async()
        updates_left = self._sources_expected.difference(self._sources_received)
        await self._updates_storage_lock.release_async()
        return updates_left
    
    async def notify_if_all_updates_received(self):
        await self._round_updates_lock.acquire_async()
    
    async def all_updates_received(self):
        updates_left = self._sources_expected.difference(self._sources_received)
        if len(updates_left) == 0:
            await self._round_updates_lock.release_async()
            await self.agg.notify_all_updates_received()
       