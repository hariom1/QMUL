from nebula.core.situationalawareness.awareness.satraining.trainingpolicy.trainingpolicy import TrainingPolicy
import asyncio
from nebula.core.utils.helper import cosine_metric
from nebula.core.utils.locker import Locker
from collections import deque
import logging
from nebula.core.eventmanager import EventManager
from nebula.core.nebulaevents import AggregationEvent
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.eventmanager import EventManager

# "Quality-Driven Selection"    (QDS)
class QDSTrainingPolicy(TrainingPolicy):
    MAX_HISTORIC_SIZE = 10
    SIMILARITY_THRESHOLD = 0.8

    def __init__(self, config : dict):
        self._addr = config["addr"]
        self._nodes : dict[str, deque] = {}
        self._nodes_lock = Locker(name="nodes_lock", async_lock=True)
        

    async def init(self, config):
        async with self._nodes_lock:
            nodes = config["nodes"]
            self._nodes : dict[str, deque] = {node_id: deque(maxlen=self.MAX_HISTORIC_SIZE) for node_id in nodes}
        await EventManager.get_instance().subscribe_node_event(AggregationEvent, self.process_aggregation_event)

    async def update_neighbors(self, node, remove=False):
        async with self._nodes_lock:
            if remove:
                self._nodes.pop(node, None)
            else:
                if not node in self._nodes:
                    self._nodes.update({node : deque(maxlen=self.MAX_HISTORIC_SIZE)})

    async def process_aggregation_event(self, agg_ev : AggregationEvent):
        logging.info("Processing aggregation event")
        (updates, expected_nodes, missing_nodes) = await agg_ev.get_event_data()
        self_updt = updates[self._addr]
        async with self._nodes_lock:
            for addr, updt in updates.items():
                if addr == self._addr: continue
                if not addr in self._nodes.keys(): continue
                (model,_) = updt
                (self_model, _) = self_updt 
                cos_sim = cosine_metric(self_model, model, similarity=True)
                self._nodes[addr].append(cos_sim)
    
    async def evaluate(self):
        async with self._nodes_lock:
            for node in self._nodes:
                if self._nodes[node]:
                    last_sim = self._nodes[node][-1]
                    if self._nodes[node][-1] < self.SIMILARITY_THRESHOLD:
                        logging.info(f"Node: {node} got a similarity value of: {last_sim} under threshold: {self.SIMILARITY_THRESHOLD}")