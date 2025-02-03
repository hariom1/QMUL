import asyncio
import logging
from collections import deque
from nebula.core.utils.helper import cosine_metric
from nebula.core.utils.locker import Locker
import numpy as np

from typing import TYPE_CHECKING, Callable, OrderedDict, Optional
from typing_extensions import Annotated
if TYPE_CHECKING:
    from nebula.core.neighbormanagement.nodemanager import NodeManager

SimilarityMetricType = Callable[[OrderedDict, OrderedDict, bool], Optional[float]]
MappingSimilarityType = Callable[[float, float], Annotated[float, "Value in (0, 1]"]]

MAX_HISTORIC_SIZE = 10      # Number of historic data storaged
GLOBAL_PRIORITY = 0.5       # Parameter to priorize global vs local metrics
EPSILON = 0.001
SIGMOID_THRESHOLD = 0.92
TOLERANCE_THRESHOLD = 2     # Threshold to start appliying full penalty
SMOOTH_FACTOR = 0.5

class Momentum():

    def __init__(
        self,  
        node_manager: "NodeManager",
        nodes,
        dispersion_penalty=True,
        global_priority=GLOBAL_PRIORITY,     
        similarity_metric : SimilarityMetricType = cosine_metric,
        mapping_similarity : MappingSimilarityType = lambda sim_value, e=EPSILON: e + ((sim_value + 1) / 2),
    ):
        self._node_manager = node_manager
        self._similarities_historic = {node_id: deque(maxlen=MAX_HISTORIC_SIZE) for node_id in nodes}
        self._similarities_historic_lock = Locker(name="_similarities_historic_lock", async_lock=True)
        self._model_similarity_metric_lock = Locker(name="_model_similarity_metric_lock", async_lock=True)
        self._model_similarity_metric = similarity_metric
        self._mapping_similarity_func = mapping_similarity
        self._global_prio = global_priority
        self._dispersion_penalty = dispersion_penalty
        self._addr = self._node_manager.engine.addr

    @property
    def nm(self):
        return self._node_manager
    
    @property
    def msm(self):
        return self._model_similarity_metric
    
    @property
    def msf(self):
        return self._mapping_similarity_func

    async def _add_similarity_to_node(self, node_id, sim_value):
        logging.info(f"Adding | node ID: {node_id}, cossine similarity value: {sim_value}")
        self._similarities_historic_lock.acquire_async()
        self._similarities_historic[node_id].append(sim_value)
        self._similarities_historic_lock.release_async()
        
    async def _get_similarity_historic(self, addrs):
        """
            Get historic storaged for node IDs on 'addrs'

        Args:
            addrs (List)): List of node IDs that has sent update this round
        """
        self._similarities_historic_lock.acquire_async()
        historic = {}
        for key, value in self._similarities_historic.items():
            if key in addrs:
                historic[key] = value
        self._similarities_historic_lock.release_async()
        return historic    

    async def update_node(self, node_id, remove=False):
        self._similarities_historic_lock.acquire_async()
        if remove:
            self._similarities_historic.pop(node_id, None)
        else:
            self._similarities_historic.update({node_id: deque(maxlen=MAX_HISTORIC_SIZE)})
        self._similarities_historic_lock.release_async()
        
    async def change_similarity_metric(self, new_metric: SimilarityMetricType, new_mapping: MappingSimilarityType):
        self._model_similarity_metric_lock.acquire_async()
        self.msm = new_metric
        self.msf = new_mapping
        # maybe we should remove historic data due to incongruous data
        self._model_similarity_metric_lock.release_async()
        
    async def _calculate_similarities(self, updates: dict):
        """
            Function to calculate similarity between local model and models received
            using metric function. The value is storaged on the historic

        Args:
            updates (dict): {node ID: model}
        """
        logging.info(f"Calculate | Model Similarity values are being calculated...")
        model = self.nm.engine.trainer.get_model_parameters()
        for addr,update in updates.items():
            if addr == self._addr:
                continue
            sim_value = self.msm(
                model,
                update,
                similarity=True,
            )
            logging.info(f"Model similarity for node: {addr}, sim: {sim_value}")
            await self._add_similarity_to_node(addr, sim_value)
            
    def _calculate_dispersion_penalty(self, historic: dict, updates: dict):
        from math import sqrt
        logging.info("Calculate | Dispersion penalty")
        round_similarities = [(addr, n_hist[-1]) for addr,n_hist in historic.items() if n_hist]
        if round_similarities:
            mean_similarity = np.mean(round_similarities)
            std_similarity = np.std(round_similarities)
            n_updates = len(updates) - 1
            logging.info(f"Calculate | mean similarity: {mean_similarity}, standar deviation: {std_similarity}")
            for addr,sim in round_similarities:
                if abs(sim - mean_similarity) < TOLERANCE_THRESHOLD * std_similarity:
                    logging.info(f"Penalty | Dispersion is lower than threshold, for node: {addr}")
                    penalty = (SMOOTH_FACTOR * (abs(sim - mean_similarity) / (std_similarity + EPSILON))) * (1/sqrt(n_updates))
                else:
                    logging.info(f"Penalty | Dispersion is higher than threshold, for node: {addr}")
                    penalty = (abs(sim - mean_similarity) / (std_similarity + EPSILON)) * (1/sqrt(n_updates)) 
                
                penalty = min(1.0, max(0.0, penalty))
                logging.info(f"Penalty value: {penalty}")
                dispersion_penalty = 1 - penalty        
    
    def map_value(sim_value, e=EPSILON):
            return e + ((sim_value + 1) / 2)
                          
    async def calculate_momentum_weights(self, updates: dict):
        if not updates:
            return
        logging.info("Calculate | Momemtum weights are being calculated...")
        self._model_similarity_metric_lock.acquire_async() 
        await self._calculate_similarities(updates)                                         # Calculate similarity value between self model and updates received
        historic = await self._get_similarity_historic(updates.keys())                      # Get historic similarities values from nodes that has sent update this round
              
        def sigmoid(similarity, k=2.5):
            if similarity >= SIGMOID_THRESHOLD:  # threshold to consider better updates
                sigmoid = 1
            else:
                sigmoid = 1 / (1 + np.exp(-k * (similarity)))
            return sigmoid 
             
        for node_addr, n_hist in historic.items():
            if not n_hist or node_addr == self._addr:
                continue 
            sim_value = n_hist[-1]                                  # Get last similarity value
            mapped_sim_value = self.msf(sim_value)                  # Mapped into [0, 1] interval
            smoothed_value = sigmoid(mapped_sim_value)
            adjusted_weight = smoothed_value * self._global_prio + (1 - self._global_prio) * mapped_sim_value
            logging.info(f"Momemtum values | adjusted_weight: {adjusted_weight}, map_value: {mapped_sim_value}, smoothed_value: {smoothed_value}")
        
        if self._dispersion_penalty:
            self._calculate_dispersion_penalty(historic, updates)
        
        self._model_similarity_metric_lock.release_async() 