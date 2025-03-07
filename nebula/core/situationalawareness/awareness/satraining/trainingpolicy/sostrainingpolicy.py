from nebula.core.situationalawareness.awareness.satraining.trainingpolicy.trainingpolicy import TrainingPolicy
from nebula.core.utils.locker import Locker
from collections import deque
import logging
from nebula.core.eventmanager import EventManager
from nebula.core.nebulaevents import UpdateReceivedEvent, AggregationEvent, RoundStartEvent
import time
import asyncio

class TimeStamp():
        def __init__(self, time_received = None, time_since_last_event = None):
            self.tr = time_received
            self.tsle = time_since_last_event

        def __sub__(self, other):
            if not isinstance(other, TimeStamp):
                raise TypeError("Subtraction is only supported between TimeStamp instances")   
            if self.tr is None or other.tr is None:
                raise ValueError("Cannot subtract TimeStamp instances with undefined 'tr' values")
            return self.tr - other.tr
        
        def __str__(self):
            return f"{self.tsle}s"
        
        def is_empty(self):
            return self.tr == None
            
        def reset(self):
            self.tr = None
            self.tsle = None

# "Speed-Oriented Selection"    (SOS)
class SOSTrainingPolicy(TrainingPolicy):
    MAX_HISTORIC_SIZE = 10
    INACTIVE_THRESHOLD = 3
    GRACE_ROUNDS = 1
    CHECK_COOLDOWN = 1
    W_UPDATE_FREQ = 0.4  # Update frequency weight
    W_UPDATE_LATENCY = 0.3  # update latency weight
    W_AGG_WAITING = 0.2  # time waited since start waiting for aggregation until update is received weight
    W_INACTIVITY_PEN = 0.1  # inactivity penalty weight
     
    def __init__(self, config):
        self._addr = config["addr"]
        self._verbose = config["verbose"]
        self._nodes : dict[str, tuple[deque, int, deque[TimeStamp], TimeStamp]] = {}  # _nodes estructura: {node_id: (deque updates epr round, inactivity, time gaps between updates, time since last aggregation)}
        
        self._nodes_lock = Locker(name="nodes_lock", async_lock=True)
        self._grace_rounds = self.GRACE_ROUNDS
        self._last_check = 0
        self._internal_rounds_done = -1
        self._last_aggregation_time = None

    async def init(self, config):
        async with self._nodes_lock:
            nodes = config["nodes"]
            self._nodes = {node_id: (deque(maxlen=self.MAX_HISTORIC_SIZE), 0, deque(maxlen=self.MAX_HISTORIC_SIZE), TimeStamp()) for node_id in nodes}
        await EventManager.get_instance().subscribe_node_event(UpdateReceivedEvent, self._process_update_received_event)
        await EventManager.get_instance().subscribe_node_event(RoundStartEvent, self._process_round_start)
        await EventManager.get_instance().subscribe_node_event(AggregationEvent, self._process_aggregation_event)

    async def _get_nodes(self):
        async with self._nodes_lock:
            nodes = self._nodes.copy()
        return nodes
    
    async def _process_round_start(self, rse : RoundStartEvent):
        if self._verbose: logging.info("Processing round start event")
        if not self._last_aggregation_time:
            if self._verbose: logging.info("First round start timing assigment")
            (_, start_time) = await rse.get_event_data()
            self._last_aggregation_time = start_time
        self._internal_rounds_done += 1

    async def _process_aggregation_event(self, are : AggregationEvent):
        self._last_aggregation_time = time.time()
        if self._verbose: logging.info("Processing aggregation event")
        (_, expected_nodes, missing_nodes) = await are.get_event_data()

        async with self._nodes_lock:
            for node in expected_nodes:
                if node in self._nodes:
                    history, missed_count, gap_btween_updts, time_since_agg = self._nodes[node]
                    self._nodes[node] = (history, 0 if node not in missing_nodes else missed_count + 1, gap_btween_updts, time_since_agg)

    async def _process_update_received_event(self, ure : UpdateReceivedEvent):
        time_received = time.time()
        if self._verbose: logging.info("Processing Update Received event")
        (_, _, source, _, _) = await ure.get_event_data()

        async with self._nodes_lock:
            if source not in self._nodes:
                return  

            history, missed_count, time_between_updts_historic, last_update_time = self._nodes[source]

            if history and history[-1][0] == self._internal_rounds_done:
                num_updates = history[-1][1] + 1
                history[-1] = (self._internal_rounds_done, num_updates)
            else:
                history.append((self._internal_rounds_done, 1))

            if not len(time_between_updts_historic):
                time_between_updts_historic.append(TimeStamp(time_received, None))
            else:
                ts = TimeStamp(time_received)
                ts.tsle = ts - time_between_updts_historic[-1]
                time_between_updts_historic.append(ts)

            last_update_time.tr = time_received
            last_update_time.tsle = time_received - self._last_aggregation_time

            self._nodes[source] = (history, missed_count, time_between_updts_historic, last_update_time)

    async def update_neighbors(self, node, remove=False):
        async with self._nodes_lock:
            if remove:
                self._nodes.pop(node, None)
            else:
                if not node in self._nodes:
                    self._nodes.update({node : (deque(maxlen=self.MAX_HISTORIC_SIZE), 0, float('inf'), float('inf'))})
    
    async def evaluate(self):
        if self._verbose: logging.info("Evaluating using speed-driven strategy")
        if self._grace_rounds:  # Grace rounds
            self._grace_rounds -= 1
            if self._verbose: logging.info("Grace time hasnt finished...")
            return None
        
        result = set()
        if self._last_check == 0:
            nodes = await self._get_nodes()
            for node in nodes.keys():
                pass
                # logging.info(f"Internal rounds done: {self._internal_rounds_done}")
                # logging.info(f"Node: {node}, {nodes[node][0]}")
                # updates_received = {x[1] for x in nodes[node][0] if x[0] == self._internal_rounds_done}
                # logging.info(f"Node: {node} | Updates received this round: {updates_received}")
                # logging.info(f"Time waited since last aggregation event {nodes[node][3]}")
        else:
            if self._verbose: logging.info(f"Evaluation is on cooldown... | {self.CHECK_COOLDOWN - self._last_check} rounds remaining")
            
        # Extraer valores máximos y mínimos para normalización
        max_updates = max(
        (
            max((x[1] for x in nodes[n][0] if x[0] == self._internal_rounds_done), default=0)
            for n in nodes
        ),
        default=1
        )

        min_latency = min(
            (
                sum(t.tsle for t in nodes[n][2] if t.tsle is not None and t.tsle != float('inf')) / len(nodes[n][2])
                if any(t.tsle is not None and t.tsle != float('inf') for t in nodes[n][2])
                else float('inf')
                for n in nodes
            ),
            default=1
        )

        min_wait_time = min(
            (
                nodes[n][3].tsle if nodes[n][3] and nodes[n][3].tsle is not None else float('inf')
                for n in nodes
            ),
            default=1
        )

        scores = {}

        for node, (history, missed_count, time_between_updts_historic, last_update_time) in nodes.items():
            # 1. Frecuencia de updates normalizada
            updates_received = max((x[1] for x in history if x[0] == self._internal_rounds_done), default=0)
            F_updt_freq = updates_received / max_updates if max_updates > 0 else 0

            # 2. Latencia media entre updates normalizada
            valid_latencies = [t.tsle for t in time_between_updts_historic if t.tsle is not None and t.tsle != float('inf')]
            avg_latency = sum(valid_latencies) / len(valid_latencies) if valid_latencies else float('inf')
            F_updt_latency = min_latency / avg_latency if avg_latency > 0 and avg_latency != float('inf') else 0

            # 3. Tiempo desde última agregación normalizado
            wait_time = last_update_time.tsle if last_update_time.tsle is not None else float('inf')
            F_agg_waiting = min_wait_time / wait_time if wait_time > 0 else 0

            # 4. Penalización por inactividad
            P_n = 1 / (1 + missed_count)  # Penalización inversamente proporcional

            # Calcular puntuación final
            score = (
                (self.W_UPDATE_FREQ * F_updt_freq) +
                (self.W_UPDATE_LATENCY * F_updt_latency) +
                (self.W_AGG_WAITING * F_agg_waiting) +
                (self.W_INACTIVITY_PEN * P_n)
            )
            scores[node] = score
        
        # Ordenar nodos por puntuación descendente
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if self._verbose:
            for node, score in sorted_nodes:
                logging.info(f"Node: {node} | Score: {score:.3f}")
            self._last_check = (self._last_check + 1)  % self.CHECK_COOLDOWN
                             
        return result
    
    