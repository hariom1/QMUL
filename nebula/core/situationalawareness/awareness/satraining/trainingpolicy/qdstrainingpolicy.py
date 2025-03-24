from nebula.core.situationalawareness.awareness.satraining.trainingpolicy.trainingpolicy import TrainingPolicy
import asyncio
from nebula.core.utils.helper import cosine_metric
from nebula.core.utils.locker import Locker
from collections import deque
import logging
from nebula.core.eventmanager import EventManager
from nebula.core.nebulaevents import AggregationEvent
import math

# "Quality-Driven Selection"    (QDS)
class QDSTrainingPolicy(TrainingPolicy):
    MAX_HISTORIC_SIZE = 10
    SIMILARITY_THRESHOLD = 0.8
    INACTIVE_THRESHOLD = 3
    GRACE_ROUNDS = 0
    CHECK_COOLDOWN = 50

    def __init__(self, config : dict):
        self._addr = config["addr"]
        self._verbose = config["verbose"]
        self._nodes : dict[str, tuple[deque, int]] = {}
        self._nodes_lock = Locker(name="nodes_lock", async_lock=True)
        self._round_missing_nodes = set()
        self._grace_rounds = self.GRACE_ROUNDS
        self._last_check = 0
        self._evaluation_results = set()
        
    def __str__(self):
        return "QDS"

    async def init(self, config):
        async with self._nodes_lock:
            nodes = config["nodes"]
            self._nodes : dict[str, tuple[deque, int]] = {node_id: (deque(maxlen=self.MAX_HISTORIC_SIZE), 0) for node_id in nodes}
        await EventManager.get_instance().subscribe_node_event(AggregationEvent, self.process_aggregation_event)

    async def update_neighbors(self, node, remove=False):
        async with self._nodes_lock:
            if remove:
                self._nodes.pop(node, None)
            else:
                if not node in self._nodes:
                    self._nodes.update({node : (deque(maxlen=self.MAX_HISTORIC_SIZE), 0)})

    async def process_aggregation_event(self, agg_ev : AggregationEvent):
        if self._verbose: logging.info("Processing aggregation event")
        (updates, expected_nodes, missing_nodes) = await agg_ev.get_event_data()
        self._round_missing_nodes = missing_nodes
        self_updt = updates[self._addr]
        async with self._nodes_lock:
            for addr, updt in updates.items():
                if addr == self._addr: continue
                if not addr in self._nodes.keys(): continue
                
                deque_history, missed_count = self._nodes[addr]
                if addr in missing_nodes:
                    if self._verbose: logging.info(f"Node inactivity counter increased for: {addr}")
                    self._nodes[addr] = (deque_history, missed_count + 1)   # Inactive rounds counter +1
                else:
                    self._nodes[addr] = (deque_history, 0)                  # Reset inactive counter
                    
                #TODO hacerlo solo para los q no se está utilizando la ultima update guardada                       
                (model,_) = updt
                (self_model, _) = self_updt 
                cos_sim = cosine_metric(self_model, model, similarity=True)
                self._nodes[addr][0].append(cos_sim)
        self._evaluation_results = await self.evaluate()
        
    async def _get_nodes(self):
        async with self._nodes_lock:
            nodes = self._nodes.copy()
        return nodes    
    
    async def evaluate(self):
        if self._grace_rounds:  # Grace rounds
            self._grace_rounds -= 1
            if self._verbose: logging.info("Grace time hasnt finished...")
            return None
        
        if self._verbose: logging.info("Evaluation in process")
    
        result = set()     
        if self._last_check == 0:
            nodes = await self._get_nodes()
            redundant_nodes = set()
            inactive_nodes = set()
            for node in nodes:
                if nodes[node][0]:
                    last_sim = nodes[node][0][-1]
                    inactivity_counter =  nodes[node][1]
                    if inactivity_counter >= self.INACTIVE_THRESHOLD:
                        inactive_nodes.add(node)
                        if self._verbose: logging.info(f"Node: {node} hadn't participated in any of the last {self.INACTIVE_THRESHOLD} rounds")
                    else:
                        if self._verbose: logging.info(f"Node: {node} inactivity counter: {inactivity_counter}")
                        
                    if node not in self._round_missing_nodes:
                        if last_sim < self.SIMILARITY_THRESHOLD:
                            if self._verbose: logging.info(f"Node: {node} got a similarity value of: {last_sim} under threshold: {self.SIMILARITY_THRESHOLD}")
                        else:
                            if self._verbose: logging.info(f"Node: {node} got a redundant model, cossine simmilarity: {last_sim} over threshold: {self.SIMILARITY_THRESHOLD}")
                            redundant_nodes.add((node, last_sim))
                        
            if self._verbose: logging.info(f"Inactive nodes on aggregations: {inactive_nodes}")
            if self._verbose: logging.info(f"Redundant nodes on aggregations: {redundant_nodes}")
            if inactive_nodes:
                result = result.union(inactive_nodes)    
            if len(redundant_nodes):
                sorted_redundant_nodes = sorted(redundant_nodes, key=lambda x: x[1])
                n_discarded = math.ceil((len(redundant_nodes)/2))
                discard_nodes = sorted_redundant_nodes[:n_discarded]
                if self._verbose: logging.info(f"Discarded redundant nodes: {discard_nodes}")
                result = result.union(discard_nodes)
        else:
            if self._verbose: logging.info(f"Evaluation is on cooldown... | {self.CHECK_COOLDOWN - self._last_check} rounds remaining")
            
        self._last_check = (self._last_check + 1)  % self.CHECK_COOLDOWN
                             
        return result
    
    async def get_evaluation_results(self):
        return self._evaluation_results.copy()