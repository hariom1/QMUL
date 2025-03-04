from nebula.core.situationalawareness.awareness.satraining.trainingpolicy.trainingpolicy import TrainingPolicy
from nebula.core.utils.locker import Locker
from collections import deque
import logging
from nebula.core.eventmanager import EventManager
from nebula.core.nebulaevents import UpdateReceivedEvent, AggregationEvent, RoundStartEvent
import time
import asyncio

# "Speed-Oriented Selection"    (SOS)
class SOSTrainingPolicy(TrainingPolicy):
    MAX_HISTORIC_SIZE = 10
    INACTIVE_THRESHOLD = 3
    GRACE_ROUNDS = 10
    CHECK_COOLDOWN = 10
    
    def __init__(self, config):
        self._addr = config["addr"]
        self._verbose = config["verbose"]
        self._nodes : dict[str, tuple[deque, int, float, float]] = {}  # _nodes estructura: {node_id: (deque updates epr round, inactivity, time gap between updates, time since last aggregation)}
        
        self._nodes_lock = Locker(name="nodes_lock", async_lock=True)
        self._round_missing_nodes = set()
        self._grace_rounds = self.GRACE_ROUNDS
        self._last_check = 0
        self._internal_rounds_done = 0
        self._last_aggregation_time = None

    async def init(self, config):
        async with self._nodes_lock:
            nodes = config["nodes"]
            self._nodes = {node_id: (deque(maxlen=self.MAX_HISTORIC_SIZE), 0, float('inf'), float('inf')) for node_id in nodes}
        await EventManager.get_instance().subscribe_node_event(UpdateReceivedEvent, self._process_update_received_event)
        await EventManager.get_instance().subscribe_node_event(AggregationEvent, self._process_aggregation_event)
        await EventManager.get_instance().subscribe_node_event(RoundStartEvent, self._process_first_round_start)


    async def _get_nodes(self):
        async with self._nodes_lock:
            nodes = self._nodes.copy()
        return nodes
    
    async def _process_first_round_start(self, rse : RoundStartEvent):
        if not self._last_aggregation_time:
            (_, start_time) = await rse.get_event_data()
            self._last_aggregation_time = start_time
            asyncio.create_task(EventManager.get_instance().unsubscribe_event(RoundStartEvent, self._process_first_round_start))

    async def _process_aggregation_event(self, are : AggregationEvent):
        self._last_aggregation_time = time.time()
        if self._verbose: logging.info("Processing aggregation event")
        self._internal_rounds_done += 1
        (_, expected_nodes, missing_nodes) = await are.get_event_data()

        async with self._nodes_lock:
            for node in expected_nodes:
                if node in self._nodes:
                    history, missed_count, _, _ = self._nodes[node]
                    history.append((self._internal_rounds_done, 0))  
                    self._nodes[node] = (history, 0 if node not in missing_nodes else missed_count + 1, float('inf'), float('inf'))


    async def _process_update_received_event(self, ure : UpdateReceivedEvent):
        time_received = time.time()
        if self._verbose: logging.info("Processing Update Received event")
        (_, _, source, _, _) = await ure.get_event_data()
        async with self._nodes_lock:
            if source not in self._nodes:
                return  

        history, missed_count, first_update_time, last_update_time = self._nodes[source]

        if history and history[-1][0] == self._internal_rounds_done:
            num_updates = history[-1][1] + 1
            history[-1] = (self._internal_rounds_done, num_updates)
        else:
            history.append((self._internal_rounds_done, 1))

        if first_update_time == float('inf'):
            if self._last_aggregation_time:
                first_update_time = time_received - self._last_aggregation_time
            else:
                first_update_time = 0

        if last_update_time == float('inf'):
            last_update_time = first_update_time
        else:
            last_update_time = time_received - last_update_time

        self._nodes[source] = (history, missed_count, first_update_time, last_update_time)

    async def update_neighbors(self, node, remove=False):
        async with self._nodes_lock:
            if remove:
                self._nodes.pop(node, None)
            else:
                if not node in self._nodes:
                    self._nodes.update({node : (deque(maxlen=self.MAX_HISTORIC_SIZE), 0, float('inf'), float('inf'))})
    
    async def evaluate(self):
        if self._grace_rounds:  # Grace rounds
            self._grace_rounds -= 1
            if self._verbose: logging.info("Grace time hasnt finished...")
            return None
        
        result = set()
        if self._last_check == 0:
            pass
        else:
            if self._verbose: logging.info(f"Evaluation is on cooldown... | {self.CHECK_COOLDOWN - self._last_check} rounds remaining")
            
        self._last_check = (self._last_check + 1)  % self.CHECK_COOLDOWN
                             
        return result