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
       
    @property
    def us(self):
        return self._updates_storage
    
    @property
    def agg(self):
        return self._aggregator  
       
    async def round_expected_updates(self, federation_nodes: set):
        self._updates_storage_lock.acquire_async()
        self._sources_expected = federation_nodes
        self._sources_received.clear()
        for fn in federation_nodes:
            if fn not in self.us:
                self.us[fn] = (None, deque(maxlen=self._buffersize))
        self._updates_storage_lock.release_async()
        
    async def storage_update(self, model, weight, source, round):
        #TODO verificar duplicados
        time_received = time.time()
        if source in self._sources_expected:
            updt = Update(model, weight, source, round, time_received)
            self._updates_storage_lock.acquire_async()
            self.us[source][1].append(updt)
            self.us[source][0] = updt
            logging.info(f"Storage Update | source={source} | round={round} | weight={weight} | federation nodes: {self._sources_expected}")
            
            self._sources_received.add(source)
            updates_left = self._sources_expected.difference(self._sources_received)
            logging.info(f"Updates received ({self._sources_received}/{self._sources_expected}) | Missing nodes: {updates_left}")
            if not updates_left:
                await self.all_updates_received()
            self._updates_storage_lock.release_async()
        else:
            logging.info(f"source: {source} not in expected updates for this Round")
            
    async def update_source(self, source, remove=False):
        logging.info(f"🔄 Update | remove: {remove} | soure: {source}")
        self._updates_storage_lock.acquire_async()
        if remove:
            self._sources_expected.discard(source)
            del self.us[source]
        else:
            self.us[source] = (None, deque(maxlen=self._buffersize))
            self._sources_expected.add(source)
        self._updates_storage_lock.release_async()
        
    async def get_round_updates(self):
        self._updates_storage_lock.acquire_async()
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
        self._updates_storage_lock.release_async()
        return updates
                  
    async def get_round_missing_nodes(self):
        self._updates_storage_lock.acquire_async()
        updates_left = self._sources_expected.difference(self._sources_received)
        self._updates_storage_lock.release_async()
        return updates_left
    
    async def all_updates_received(self):
        logging.info("🔄 Notify | All updates received")
        self.agg.notify_all_updates_received()