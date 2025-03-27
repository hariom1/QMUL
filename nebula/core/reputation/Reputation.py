import csv
import json
import logging
import os
import random
import torch
import numpy as np
import time
import numpy as np

from typing import TYPE_CHECKING
from nebula.addons.functions import print_msg_box
from nebula.core.nebulaevents import RoundStartEvent, UpdateReceivedEvent, MessageEvent, AggregationEvent
from nebula.core.eventmanager import EventManager
from datetime import datetime
from nebula.core.utils.helper import (
    cosine_metric,
    euclidean_metric,
    jaccard_metric,
    manhattan_metric,
    minkowski_metric,
    pearson_correlation_metric,
)

if TYPE_CHECKING:
    from nebula.core.engine import Engine
    from nebula.config.config import Config

class Reputation:
    """
    Class to define the reputation of a participant.
    """

    def __init__(self, engine: "Engine", config: "Config"):
        self._engine = engine
        self._config = config
        self.fraction_of_params_changed = {}
        self.history_data = {}
        self.metric_weights = {}
        self.reputation = {}
        self.reputation_with_feedback = {}
        self.reputation_with_all_feedback = {}
        self.rejected_nodes = set()
        self.round_timing_info = {}
        self._messages_received_from_sources = {}
        self.reputation_history = {}
        self.number_message_history = {}
        self.neighbor_reputation_history = {}
        self.fraction_changed_history = {}
        self.messages_number_message = []
        self.previous_threshold_number_message = {}
        self.previous_std_dev_number_message = {}
        self.messages_model_arrival_latency = {}
        self.model_arrival_latency_history = {}
        self.previous_percentile_25_number_message = {}
        self.previous_percentile_85_number_message = {}
        self._addr = engine.addr
        self._log_dir = engine.log_dir
        self._idx = engine.idx
        
        self._with_reputation = self._config.participant["defense_args"]["with_reputation"]
        self._reputation_metrics = self._config.participant["defense_args"]["reputation_metrics"]
        self._initial_reputation = float(self._config.participant["defense_args"]["initial_reputation"])
        self._weighting_factor = self._config.participant["defense_args"]["weighting_factor"]
        self._weight_model_arrival_latency = float(self._config.participant["defense_args"]["weight_model_arrival_latency"])
        self._weight_model_similarity = float(self._config.participant["defense_args"]["weight_model_similarity"])
        self._weight_num_messages = float(self._config.participant["defense_args"]["weight_num_messages"])
        self._weight_fraction_params_changed = float(self._config.participant["defense_args"]["weight_fraction_params_changed"])
        
        msg = f"Reputation system: {self._with_reputation}"
        msg += f"\nReputation metrics: {self._reputation_metrics}"
        msg += f"\nInitial reputation: {self._initial_reputation}"
        msg += f"\nWeighting factor: {self._weighting_factor}"
        if self._weighting_factor == "static":
            msg += f"\nWeight model arrival latency: {self._weight_model_arrival_latency}"
            msg += f"\nWeight model similarity: {self._weight_model_similarity}"
            msg += f"\nWeight number of messages: {self._weight_num_messages}"
            msg += f"\nWeight fraction of parameters changed: {self._weight_fraction_params_changed}"
        print_msg_box(msg=msg, indent=2, title="Defense information")
        
    @property
    def engine(self):
        return self._engine
    
    def save_data(
        self,
        type_data,
        source_ip,
        addr,
        num_round=None,
        time=None,
        current_round=None,
        fraction_changed=None,
        total_params=None,
        changed_params=None,
        threshold=None,
        changes_record=None,
        latency=None,
    ):
        """
        Save data between nodes and aggregated models.
        """

        try:
            combined_data = {}
            
            if addr == source_ip:
                return

            if type_data == "number_message":
                combined_data["number_message"] = {
                    "time": time,
                    "current_round": current_round,
                }
            elif type_data == "fraction_of_params_changed":
                combined_data["fraction_of_params_changed"] = {
                    "total_params": total_params,
                    "changed_params": changed_params,
                    "fraction_changed": fraction_changed,
                    "threshold": threshold,
                    "changes_record": changes_record,
                    "round": num_round,
                }
            elif type_data == "model_arrival_latency":
                combined_data["model_arrival_latency"] = {
                    "latency": latency,
                    "round": num_round,
                    "round_received": current_round,
                }

            script_dir = os.path.join(self._log_dir, "reputation")
            file_name = f"{addr}_storing_{source_ip}_info.json"
            full_file_path = os.path.join(script_dir, file_name)
            os.makedirs(os.path.dirname(full_file_path), exist_ok=True)

            all_metrics = []
            if os.path.exists(full_file_path):
                with open(full_file_path) as existing_file:
                    try:
                        all_metrics = json.load(existing_file)
                    except json.JSONDecodeError:
                        logging.exception(f"JSON decode error in file: {full_file_path}")
                        all_metrics = []

            all_metrics.append(combined_data)

            with open(full_file_path, "w") as json_file:
                json.dump(all_metrics, json_file, indent=4)

        except Exception:
            logging.exception("Error saving data")
    
    async def setup(self):
        """
            Setup the reputation system.
        """
        if self._with_reputation:
            logging.info("Reputation system enabled")
            await EventManager.get_instance().subscribe_node_event(RoundStartEvent, self.on_round_start)
            await EventManager.get_instance().subscribe_node_event(AggregationEvent, self.calculate_reputation)
            if self._reputation_metrics.get("model_similarity", False):
                await EventManager.get_instance().subscribe_node_event(UpdateReceivedEvent, self.recollect_similarity)
            if self._reputation_metrics.get("fraction_parameters_changed", False):
                await EventManager.get_instance().subscribe_node_event(UpdateReceivedEvent, self.recollect_fraction_of_parameters_changed)
            if self._reputation_metrics.get("num_messages", False):
                await EventManager.get_instance().subscribe(("model", "update"), self.recollect_number_message)
                await EventManager.get_instance().subscribe(("model", "initialization"), self.recollect_number_message)
                await EventManager.get_instance().subscribe(("control", "alive"), self.recollect_number_message)
                await EventManager.get_instance().subscribe(("federation", "federation_models_included"), self.recollect_number_message)
                await EventManager.get_instance().subscribe(("reputation", "share"), self.recollect_number_message)
            if self._reputation_metrics.get("model_arrival_latency", False):
                await EventManager.get_instance().subscribe_node_event(UpdateReceivedEvent, self.recollect_model_arrival_latency)
            
    def init_reputation(self, addr, federation_nodes=None, round_num=None, last_feedback_round=None, init_reputation=None):
        """
        Initialize the reputation system.
        """
        if not federation_nodes:
            logging.error("init_reputation | No federation nodes provided")
            return

        if self._with_reputation:
            neighbors = self.is_valid_ip(federation_nodes)

            if not neighbors:
                logging.error("init_reputation | No neighbors found")
                return

            for nei in neighbors:
                if nei not in self.reputation:
                    self.reputation[nei] = {
                        "reputation": init_reputation,
                        "round": round_num,
                        "last_feedback_round": last_feedback_round,
                    }
                elif self.reputation[nei].get("reputation") is None:
                    self.reputation[nei]["reputation"] = init_reputation
                    self.reputation[nei]["round"] = round_num
                    self.reputation[nei]["last_feedback_round"] = last_feedback_round

                avg_reputation = self.save_reputation_history_in_memory(self._addr, nei, init_reputation)

    def is_valid_ip(self, federation_nodes):
        """
        Check if the IP addresses are valid.
        """
        valid_ip = []
        for i in federation_nodes:   
            valid_ip.append(i)

        return valid_ip

    def _calculate_static_reputation(self, addr, nei, metric_messages_number, metric_similarity, metric_fraction, metric_model_arrival_latency,
                                     weight_messages_number, weight_similarity, weight_fraction, weight_model_arrival_latency):
        """
        Calculate the static reputation of a participant.

        Args:
            addr (str): The IP address of the participant.
            nei (str): The IP address of the participant.
            metric_messages_number (float): The number of messages.
            metric_similarity (float): The similarity between models.
            metric_fraction (float): The fraction of parameters changed.
            metric_model_arrival_latency (float): The model arrival latency.
            weight_messages_number (float): The weight of the number of messages.
            weight_similarity (float): The weight of the similarity.
            weight_fraction (float): The weight of the fraction.
            weight_model_arrival_latency (float): The weight of the model arrival latency.

        Returns:
            float: The static reputation of the participant.
        """

        static_weights = {
            "num_messages": weight_messages_number,
            "model_similarity": weight_similarity,
            "fraction_parameters_changed": weight_fraction,
            "model_arrival_latency": weight_model_arrival_latency,
        }

        metric_values = {
            "num_messages": metric_messages_number,
            "model_similarity": metric_similarity,
            "fraction_parameters_changed": metric_fraction,
            "model_arrival_latency": metric_model_arrival_latency,
        }

        reputation_static = sum(
            metric_values[metric_name] * static_weights[metric_name] for metric_name in static_weights
        )
        logging.info(f"Static reputation for node {nei} at round {self.engine.get_round()}: {reputation_static}")

        avg_reputation = self.save_reputation_history_in_memory(self.engine.addr, nei, reputation_static)

        metrics_data = {
            "addr": addr,
            "nei": nei,
            "round": self.engine.get_round(),
            "reputation_without_feedback": avg_reputation,
        }

        for metric_name in metric_values:
            metrics_data[f"average_{metric_name}"] = static_weights[metric_name]

        self._update_reputation_record(nei, avg_reputation, metrics_data)

    async def _calculate_dynamic_reputation(self, addr, neighbors):
        """
        Calculate the dynamic reputation of a participant.

        Args:
            addr (str): The IP address of the participant.
            neighbors (list): The list of neighbors.

        Returns:
            dict: The dynamic reputation of the participant.
        """
        average_weights = {}

        for metric_name in self.history_data.keys():
            if self._reputation_metrics.get(metric_name, False):
                valid_entries = [
                    entry for entry in self.history_data[metric_name]
                    if entry["round"] >= self._engine.get_round() and entry.get("weight") not in [None, -1]
                ]

                if valid_entries:
                    average_weight = sum([entry["weight"] for entry in valid_entries]) / len(valid_entries)
                    average_weights[metric_name] = average_weight
                else:
                    average_weights[metric_name] = 0

        for nei in neighbors:
            metric_values = {}
            for metric_name in self.history_data.keys():
                if self._reputation_metrics.get(metric_name, False):
                    for entry in self.history_data.get(metric_name, []):
                        if entry["round"] == self._engine.get_round() and entry["metric_name"] == metric_name and entry["nei"] == nei:
                            metric_values[metric_name] = entry["metric_value"]
                            break

            if all(metric_name in metric_values for metric_name in average_weights):
                reputation_with_weights = sum(
                    metric_values.get(metric_name, 0) * average_weights[metric_name]
                    for metric_name in average_weights
                )
                logging.info(f"Dynamic reputation with weights for {nei} at round {self.engine.get_round()}: {reputation_with_weights}")

                avg_reputation = self.save_reputation_history_in_memory(self.engine.addr, nei, reputation_with_weights)

                metrics_data = {
                    "addr": addr,
                    "nei": nei,
                    "round": self.engine.get_round(),
                    "reputation_without_feedback": avg_reputation,
                }

                for metric_name in metric_values:
                    metrics_data[f"average_{metric_name}"] = average_weights[metric_name]

                self._update_reputation_record(nei, avg_reputation, metrics_data)

    def _update_reputation_record(self, nei, reputation, data):
        """
        Update the reputation record of a participant.

        Args:
            nei (str): The IP address of the participant.
            reputation (float): The reputation of the participant.
            data (dict): The data to update.
        """
        if nei not in self.reputation:
            self.reputation[nei] = {
                "reputation": reputation,
                "round": self._engine.get_round(),
                "last_feedback_round": -1,
            }
        else:
            self.reputation[nei]["reputation"] = reputation
            self.reputation[nei]["round"] = self._engine.get_round()

        logging.info(f"Reputation of node {nei}: {self.reputation[nei]['reputation']}")
        if self.reputation[nei]["reputation"] < 0.6:
            self.rejected_nodes.add(nei)
            logging.info(f"Rejected node {nei} at round {self._engine.get_round()}")
 
    def calculate_weighted_values(
        self,
        avg_messages_number_message_normalized,
        similarity_reputation,
        fraction_score_asign,
        avg_model_arrival_latency,
        history_data,
        current_round,
        addr,
        nei,
        reputation_metrics
    ):
        """
        Calculate the weighted values for each metric.
        """
        if current_round is not None:

            normalized_weights = {}
            required_keys = [
                "num_messages",
                "model_similarity",
                "fraction_parameters_changed",
                "model_arrival_latency",
            ]

            for key in required_keys:
                if key not in history_data:
                    history_data[key] = []

            metrics = {
                "num_messages": avg_messages_number_message_normalized,
                "model_similarity": similarity_reputation,
                "fraction_parameters_changed": fraction_score_asign,
                "model_arrival_latency": avg_model_arrival_latency,                   
            }

            active_metrics = {k: v for k, v in metrics.items() if reputation_metrics.get(k, False)}
            num_active_metrics = len(active_metrics)

            for metric_name, current_value in active_metrics.items():
                history_data[metric_name].append({
                    "round": current_round,
                    "addr": addr,
                    "nei": nei,
                    "metric_name": metric_name,
                    "metric_value": current_value,
                    "weight": None
                })

            adjusted_weights = {}

            if current_round >= 5 and num_active_metrics > 0:
                desviations = {}
                for metric_name, current_value in active_metrics.items():
                    historical_values = history_data[metric_name]

                    metric_values = [entry['metric_value'] for entry in historical_values if 'metric_value' in entry and entry["metric_value"] != 0]

                    if metric_values:
                        mean_value = np.mean(metric_values)
                    else:
                        mean_value = 0

                    deviation = abs(current_value - mean_value)
                    desviations[metric_name] = deviation

                if all(deviation == 0.0 for deviation in desviations.values()):
                    random_weights = [random.random() for _ in range(num_active_metrics)]
                    total_random_weight = sum(random_weights)
                    normalized_weights = {metric_name: weight / total_random_weight for metric_name, weight in zip(active_metrics, random_weights)}
                else:
                    max_desviation = max(desviations.values()) if desviations else 1
                    normalized_weights = {
                        metric_name: (desviation / max_desviation) for metric_name, desviation in desviations.items()
                    }

                    total_weight = sum(normalized_weights.values())
                    if total_weight > 0:
                        normalized_weights = {
                            metric_name: weight / total_weight for metric_name, weight in normalized_weights.items()
                        }
                    else:
                        normalized_weights = {metric_name: 1 / num_active_metrics for metric_name in active_metrics}

                mean_deviation = np.mean(list(desviations.values()))
                dynamic_min_weight = max(0.1, mean_deviation / (mean_deviation + 1)) 

                total_adjusted_weight = 0

                for metric_name, weight in normalized_weights.items():
                    if weight < dynamic_min_weight:
                        adjusted_weights[metric_name] = dynamic_min_weight
                    else:
                        adjusted_weights[metric_name] = weight
                    total_adjusted_weight += adjusted_weights[metric_name]

                if total_adjusted_weight > 1:
                    for metric_name in adjusted_weights:
                        adjusted_weights[metric_name] /= total_adjusted_weight
                    total_adjusted_weight = 1
            else:
                adjusted_weights = {metric_name: 1 / num_active_metrics for metric_name in active_metrics}

            for metric_name, current_value in active_metrics.items():
                weight = adjusted_weights.get(metric_name, -1)
                for entry in history_data[metric_name]:
                    if entry["metric_name"] == metric_name and entry["round"] == current_round and entry["nei"] == nei:
                        entry["weight"] = weight

    async def calculate_value_metrics(self, log_dir, id_node, addr, nei, metrics_active=None):
        """
        Calculate the reputation of each participant based on the data stored.

        Args:
            log_dir (str): Log directory.
            id_node (str): Node ID.
            addr (str): Source IP address.
            nei (str): Destination IP address.
            metrics_active (dict): The active metrics.
        """

        messages_number_message_normalized = 0
        messages_number_message_count = 0
        avg_messages_number_message_normalized = 0
        fraction_score = 0
        fraction_score_normalized = 0
        fraction_score_asign = 0
        messages_model_arrival_latency_normalized = 0
        avg_model_arrival_latency = 0
        similarity_reputation = 0
        fraction_neighbors_scores = None

        try:
            script_dir = os.path.join(self._log_dir, "reputation")
            file_name = f"{addr}_storing_{nei}_info.json"
            full_file_path = os.path.join(script_dir, file_name)
            os.makedirs(os.path.dirname(full_file_path), exist_ok=True)

            if os.path.exists(full_file_path) and os.path.getsize(full_file_path) > 0:
                with open(full_file_path) as json_file:
                    all_metrics = json.load(json_file)
                    for metric in all_metrics:
                        if "number_message" in metric and metrics_active.get("num_messages", False):
                            current_round_time = metric["number_message"]["current_round"]
                            time = metric["number_message"]["time"]
                            if current_round_time == self._engine.get_round():
                                self.messages_number_message.append({
                                    "number_message": time,
                                    "current_round": current_round_time,
                                    "key": (addr, nei),
                                })

                        if "fraction_of_params_changed" in metric and metrics_active.get("fraction_parameters_changed", False):
                            round_fraction = metric["fraction_of_params_changed"]["round"]
                            fraction_changed = metric["fraction_of_params_changed"]["fraction_changed"]
                            threshold = metric["fraction_of_params_changed"]["threshold"]
                            if round_fraction == self._engine.get_round():
                                fraction_score_normalized = self.analyze_anomalies(
                                    addr,
                                    nei,
                                    round_fraction,
                                    self._engine.get_round(),
                                    fraction_changed,
                                    threshold,
                                )

                        if "model_arrival_latency" in metric and metrics_active.get("model_arrival_latency", False):
                            round_latency = metric["model_arrival_latency"]["round"]
                            round_received = metric["model_arrival_latency"]["round_received"]
                            latency = metric["model_arrival_latency"]["latency"]
                            if round_received == self._engine.get_round():
                                messages_model_arrival_latency_normalized = self.manage_model_arrival_latency(
                                    round_latency,
                                    addr,
                                    nei,
                                    latency,
                                    self._engine.get_round()
                                )

                    if self._engine.get_round() >= 5 and metrics_active.get("model_similarity", False):
                        similarity_file = os.path.join(log_dir, f"participant_{id_node}_similarity.csv")
                        similarity_reputation = self.read_similarity_file(similarity_file, nei, self._engine.get_round())
                    else:
                        similarity_reputation = 0

                    if messages_model_arrival_latency_normalized >= 0:
                        avg_model_arrival_latency = self.save_model_arrival_latency_history(
                            addr, nei, messages_model_arrival_latency_normalized, self._engine.get_round()
                        )
                        if avg_model_arrival_latency is None and self._engine.get_round() > 4:
                            avg_model_arrival_latency = self.model_arrival_latency_history[(addr, nei)][
                                self._engine.get_round() - 1
                            ]["score"]

                    if self.messages_number_message is not None:
                        messages_number_message_normalized, messages_number_message_count = self.manage_metric_number_message(
                                self.messages_number_message, addr, nei, self._engine.get_round(), metrics_active.get("num_messages", False)
                            )
                        
                        avg_messages_number_message_normalized = self.save_number_message_history(
                            addr, nei, messages_number_message_normalized, self._engine.get_round()
                        )
                        if avg_messages_number_message_normalized is None and self._engine.get_round() > 4:
                            avg_messages_number_message_normalized = self.number_message_history[(addr, nei)][self._engine.get_round() - 1]["avg_number_message"]

                    if self._engine.get_round() >= 5:
                        if fraction_score_normalized > 0:
                            key_previous_round = (addr, nei, self._engine.get_round() - 1) if self._engine.get_round() - 1 > 0 else None
                            fraction_previous_round = None

                            if (key_previous_round is not None and key_previous_round in self.fraction_changed_history):
                                fraction_score = self.fraction_changed_history[key_previous_round].get("fraction_score")
                                fraction_previous_round = fraction_score if fraction_score is not None else None

                            if fraction_previous_round is not None:
                                fraction_score_asign = fraction_score_normalized * 0.8 + fraction_previous_round * 0.2
                                self.fraction_changed_history[(addr, nei, self._engine.get_round())]["fraction_score"] = (fraction_score_asign)
                            else:
                                fraction_score_asign = fraction_score_normalized
                                self.fraction_changed_history[(addr, nei, self._engine.get_round())]["fraction_score"] = (fraction_score_asign)
                        else:
                            fraction_previous_round = None
                            key_previous_round = (addr, nei, self._engine.get_round() - 1) if self._engine.get_round() - 1 > 0 else None
                            if (key_previous_round is not None and key_previous_round in self.fraction_changed_history):
                                fraction_score = self.fraction_changed_history[key_previous_round].get("fraction_score")
                                fraction_previous_round = fraction_score if fraction_score is not None else None

                            if fraction_previous_round is not None:
                                fraction_score_asign = fraction_previous_round - (fraction_previous_round * 0.5)
                            else:
                                if fraction_neighbors_scores is None:
                                    fraction_neighbors_scores = {}

                                for key, value in self.fraction_changed_history.items():
                                    score = value.get("fraction_score")
                                    if score is not None:
                                        fraction_neighbors_scores[key] = score

                                if fraction_neighbors_scores:
                                    fraction_score_asign = np.mean(list(fraction_neighbors_scores.values()))
                                else:
                                    fraction_score_asign = 0 
                    else:
                        fraction_score_asign = 0

                    self.create_graphics_to_metrics(
                        messages_number_message_count,
                        avg_messages_number_message_normalized,
                        similarity_reputation,
                        fraction_score_asign,
                        avg_model_arrival_latency,
                        addr,
                        nei,
                        self._engine.get_round(),
                        self.engine.total_rounds,
                    )

            return avg_messages_number_message_normalized, similarity_reputation, fraction_score_asign, avg_model_arrival_latency
        except Exception as e:
            logging.exception(f"Error calculating reputation. Type: {type(e).__name__}")

    def create_graphics_to_metrics(
        self,
        number_message_count,
        number_message_norm,
        similarity,
        fraction,
        model_arrival_latency,
        addr,
        nei,
        current_round,
        total_rounds,
    ):
        """
        Create graphics to metrics.
        """

        if current_round is not None and current_round < total_rounds:

            model_arrival_latency_dict = {f"R-Model_arrival_latency_reputation/{addr}": {nei: model_arrival_latency}}
            messages_number_message_count_dict = {f"R-Count_messages_number_message_reputation/{addr}": {nei: number_message_count}}
            messages_number_message_norm_dict = {f"R-number_message_reputation/{addr}": {nei: number_message_norm}}
            similarity_dict = {f"R-Similarity_reputation/{addr}": {nei: similarity}}
            fraction_dict = {f"R-Fraction_reputation/{addr}": {nei: fraction}}

            if messages_number_message_count_dict is not None:
                self.engine.trainer._logger.log_data(messages_number_message_count_dict, step=current_round)

            if messages_number_message_norm_dict is not None:
                self.engine.trainer._logger.log_data(messages_number_message_norm_dict, step=current_round)

            if similarity_dict is not None:
                self.engine.trainer._logger.log_data(similarity_dict, step=current_round)

            if fraction_dict is not None:
                self.engine.trainer._logger.log_data(fraction_dict, step=current_round)

            if model_arrival_latency_dict is not None:
                self.engine.trainer._logger.log_data(model_arrival_latency_dict, step=current_round)

    def analyze_anomalies(
        self,
        addr,
        nei,
        round_num,
        current_round,
        fraction_changed,
        threshold,
    ):
        """
        Analyze anomalies in the fraction of parameters changed.

        Args:
            addr (str): Source IP address.
            nei (str): Destination IP address.
            round_num (int): Round number.
            current_round (int): Current round number.
            fraction_changed (float): Fraction of parameters changed.
            threshold (float): Threshold value.

        Returns:
            float: The fraction score between 0 and 1.
        """
        try:
            key = (addr, nei, round_num)

            if key not in self.fraction_changed_history:
                prev_key = (addr, nei, round_num - 1)
                if round_num > 0 and prev_key in self.fraction_changed_history:
                    previous_data = self.fraction_changed_history[prev_key]
                    fraction_changed = (
                        fraction_changed if fraction_changed is not None else previous_data["fraction_changed"]
                    )
                    threshold = threshold if threshold is not None else previous_data["threshold"]
                else:
                    fraction_changed = fraction_changed if fraction_changed is not None else 0
                    threshold = threshold if threshold is not None else 0

                self.fraction_changed_history[key] = {
                    "fraction_changed": fraction_changed,
                    "threshold": threshold,
                    "fraction_score": None,
                    "fraction_anomaly": False,
                    "threshold_anomaly": False,
                    "mean_fraction": None,
                    "std_dev_fraction": None,
                    "mean_threshold": None,
                    "std_dev_threshold": None,
                }

            if round_num < 5:
                past_fractions = []
                past_thresholds = []

                for r in range(round_num):
                    past_key = (addr, nei, r)
                    if past_key in self.fraction_changed_history:
                        past_fractions.append(self.fraction_changed_history[past_key]["fraction_changed"])
                        past_thresholds.append(self.fraction_changed_history[past_key]["threshold"])

                if past_fractions:
                    mean_fraction = np.mean(past_fractions)
                    std_dev_fraction = np.std(past_fractions)
                    self.fraction_changed_history[key]["mean_fraction"] = mean_fraction
                    self.fraction_changed_history[key]["std_dev_fraction"] = std_dev_fraction

                if past_thresholds:
                    mean_threshold = np.mean(past_thresholds)
                    std_dev_threshold = np.std(past_thresholds)
                    self.fraction_changed_history[key]["mean_threshold"] = mean_threshold
                    self.fraction_changed_history[key]["std_dev_threshold"] = std_dev_threshold

                return 0
            else:
                fraction_value = 0
                threshold_value = 0
                prev_key = (addr, nei, round_num - 1)
                if prev_key not in self.fraction_changed_history:
                    for i in range(0, round_num + 1):
                        potential_prev_key = (addr, nei, round_num - i)
                        if potential_prev_key in self.fraction_changed_history:
                            mean_fraction_prev = self.fraction_changed_history[potential_prev_key][
                                "mean_fraction"
                            ]
                            if mean_fraction_prev is not None:
                                prev_key = potential_prev_key
                                break

                if prev_key:
                    mean_fraction_prev = self.fraction_changed_history[prev_key]["mean_fraction"]
                    std_dev_fraction_prev = self.fraction_changed_history[prev_key]["std_dev_fraction"]
                    mean_threshold_prev = self.fraction_changed_history[prev_key]["mean_threshold"]
                    std_dev_threshold_prev = self.fraction_changed_history[prev_key]["std_dev_threshold"]

                    current_fraction = self.fraction_changed_history[key]["fraction_changed"]
                    current_threshold = self.fraction_changed_history[key]["threshold"]

                    upper_mean_fraction_prev = (mean_fraction_prev + std_dev_fraction_prev) * 1.05
                    upper_mean_threshold_prev = (mean_threshold_prev + std_dev_threshold_prev) * 1.10

                    fraction_anomaly = current_fraction > upper_mean_fraction_prev
                    threshold_anomaly = current_threshold > upper_mean_threshold_prev

                    self.fraction_changed_history[key]["fraction_anomaly"] = fraction_anomaly
                    self.fraction_changed_history[key]["threshold_anomaly"] = threshold_anomaly

                    penalization_factor_fraction = abs(current_fraction - mean_fraction_prev) / mean_fraction_prev if mean_fraction_prev != 0 else 1
                    penalization_factor_threshold = abs(current_threshold - mean_threshold_prev) / mean_threshold_prev if mean_threshold_prev != 0 else 1

                    k_fraction = penalization_factor_fraction if penalization_factor_fraction != 0 else 1
                    k_threshold = penalization_factor_threshold if penalization_factor_threshold != 0 else 1

                    if fraction_anomaly:
                        fraction_value = (
                            1 - (1 / (1 + np.exp(-k_fraction)))
                            if current_fraction is not None and mean_fraction_prev is not None
                            else 0
                        )
                    else:
                        fraction_value = (
                            1 - (1 / (1 + np.exp(k_fraction)))
                            if current_fraction is not None and mean_fraction_prev is not None
                            else 0
                        )

                    if threshold_anomaly:
                        threshold_value = (
                            1 - (1 / (1 + np.exp(-k_threshold)))
                            if current_threshold is not None and mean_threshold_prev is not None
                            else 0
                        )
                    else:
                        threshold_value = (
                            1 - (1 / (1 + np.exp(k_threshold)))
                            if current_threshold is not None and mean_threshold_prev is not None
                            else 0
                        )
                

                    fraction_weight = 0.5
                    threshold_weight = 0.5

                    fraction_score = fraction_weight * fraction_value + threshold_weight * threshold_value

                    self.fraction_changed_history[key]["mean_fraction"] = (current_fraction + mean_fraction_prev) / 2
                    self.fraction_changed_history[key]["std_dev_fraction"] = np.sqrt(((current_fraction - mean_fraction_prev) ** 2 + std_dev_fraction_prev**2) / 2)
                    self.fraction_changed_history[key]["mean_threshold"] = (current_threshold + mean_threshold_prev) / 2
                    self.fraction_changed_history[key]["std_dev_threshold"] = np.sqrt(((0.1 * (current_threshold - mean_threshold_prev) ** 2) + std_dev_threshold_prev**2) / 2)

                    return max(fraction_score, 0)
                else:
                    return -1
        except Exception:
            logging.exception("Error analyzing anomalies")
            return -1
    
    def manage_model_arrival_latency(
        self, round_num, addr, nei, latency, current_round
    ):
        """
        Manage the model_arrival_latency metric with persistent storage of mean latency.

        Args:
            round_num (int): The round number.
            addr (str): Source IP address.
            nei (str): Destination IP address.
            latency (float): Latency value for the current model_arrival_latency.
            current_round (int): The current round of the program.

        Returns:
            float: Normalized model_arrival_latency latency value between 0 and 1.
        """
        try:
            current_key = nei

            if current_round not in self.model_arrival_latency_history:
                self.model_arrival_latency_history[current_round] = {}

            self.model_arrival_latency_history[current_round][current_key] = {
                "latency": latency,
                "score": 0.0,
            }

            prev_mean_latency = 0
            prev_percentil_0 = 0
            prev_percentil_25 = 0
            difference = 0

            if current_round >= 5:
                all_latencies = [
                    data["latency"]
                    for r in self.model_arrival_latency_history
                    for key, data in self.model_arrival_latency_history[r].items()
                    if "latency" in data and data["latency"] != 0
                ]

                prev_mean_latency = np.mean(all_latencies) if all_latencies else 0
                prev_percentil_0 = np.percentile(all_latencies, 0) if all_latencies else 0
                prev_percentil_25 = np.percentile(all_latencies, 25) if all_latencies else 0

                k = 0.1
                prev_mean_latency += k * (prev_percentil_25 - prev_percentil_0)

                difference = latency - prev_mean_latency
                if latency <= prev_mean_latency:
                    score = 1.0
                else:
                    score = 1 / (1 + np.exp(abs(difference) / prev_mean_latency))

                if round_num < current_round:
                    round_diff = current_round - round_num
                    penalty_factor = round_diff * 0.1
                    penalty = penalty_factor * (1 - score)
                    score -= penalty * score

                self.model_arrival_latency_history[current_round][current_key].update({
                    "mean_latency": prev_mean_latency,
                    "percentil_0": prev_percentil_0,
                    "percentil_25": prev_percentil_25,
                    "score": score,
                })
            else:
                score = 0

            return score

        except Exception as e:
            logging.exception(f"Error managing model_arrival_latency: {e}")
            return 0

    def save_model_arrival_latency_history(self, addr, nei, model_arrival_latency, round_num):
        """
        Save the model_arrival_latency history of a participant (addr) regarding its neighbor (nei) in memory.

        Args:
            addr (str): The identifier of the node whose model_arrival_latency history is being saved.
            nei (str): The neighboring node involved.
            model_arrival_latency (float): The model_arrival_latency value to be saved.
            round_num (int): The current round number.

        Returns:
            float: The cumulative model_arrival_latency including the current round.
        """
        try:
            current_key = nei

            if round_num not in self.model_arrival_latency_history:
                self.model_arrival_latency_history[round_num] = {}

            if current_key not in self.model_arrival_latency_history[round_num]:
                self.model_arrival_latency_history[round_num][current_key] = {}

            self.model_arrival_latency_history[round_num][current_key].update({
                "score": model_arrival_latency,
            })

            if model_arrival_latency > 0 and round_num > 5:
                previous_avg = (
                    self.model_arrival_latency_history.get(round_num - 1, {})
                    .get(current_key, {})
                    .get("avg_model_arrival_latency", None)
                )

                if previous_avg is not None:
                    avg_model_arrival_latency = (
                        model_arrival_latency * 0.8 + previous_avg * 0.2
                        if previous_avg is not None
                        else model_arrival_latency
                    )
                else:
                    avg_model_arrival_latency = model_arrival_latency - (model_arrival_latency * 0.05)
            elif model_arrival_latency == 0 and round_num > 5:
                previous_avg = (
                    self.model_arrival_latency_history.get(round_num - 1, {})
                    .get(current_key, {})
                    .get("avg_model_arrival_latency", None)
                )
                avg_model_arrival_latency = previous_avg - (previous_avg * 0.05)
            else:
                avg_model_arrival_latency = model_arrival_latency

            self.model_arrival_latency_history[round_num][current_key]["avg_model_arrival_latency"] = (
                avg_model_arrival_latency
            )

            return avg_model_arrival_latency
        except Exception:
            logging.exception("Error saving model_arrival_latency history")
    
    def manage_metric_number_message(self, messages_number_message, addr, nei, current_round, metric_active=True):
        """
        Manage the number_message metric using percentiles for normalization, considering the last 5 rounds dynamically.

        Args:
            messages_number_message (list): List of messages number_message.
            addr (str): Source IP address.
            nei (str): Destination IP address.
            current_round (int): Current round number.
            metric_active (bool): The metric status.

        Returns:
            float: Normalized number_message value.
            int: Messages count.
        """
        try:
            if current_round == 0:
                return 0.0, 0

            if not metric_active:
                return 0.0, 0
            
            previous_round = current_round

            current_addr_nei = (addr, nei)
            relevant_messages = [
                msg
                for msg in messages_number_message
                if msg["key"] == current_addr_nei and msg["current_round"] == previous_round
            ]
            messages_count = len(relevant_messages) if relevant_messages else 0

            rounds_to_consider = []
            if previous_round >= 4:
                rounds_to_consider = [previous_round - 4, previous_round - 3, previous_round - 2, previous_round - 1]
            elif previous_round == 3:
                rounds_to_consider = [0, 1, 2, 3]
            elif previous_round == 2:
                rounds_to_consider = [0, 1, 2]
            elif previous_round == 1:
                rounds_to_consider = [0, 1]
            elif previous_round == 0:
                rounds_to_consider = [0]

            previous_counts = [
                len([m for m in messages_number_message if m["key"] == current_addr_nei and m["current_round"] == r])
                for r in rounds_to_consider
            ]

            self.previous_percentile_25_number_message[current_addr_nei] = (
                np.percentile(previous_counts, 25) if previous_counts else 0
            )
            self.previous_percentile_85_number_message[current_addr_nei] = (
                np.percentile(previous_counts, 85) if previous_counts else 0
            )

            normalized_messages = 1.0
            relative_position = 0

            if previous_round > 4:
                percentile_25 = self.previous_percentile_25_number_message.get(current_addr_nei, 0)
                percentile_85 = self.previous_percentile_85_number_message.get(current_addr_nei, 0)
                if messages_count > percentile_85:
                    relative_position = (messages_count - percentile_85) / (percentile_85 - percentile_25)
                    normalized_messages = np.exp(-relative_position)

                normalized_messages = max(0.01, normalized_messages)

            return normalized_messages, messages_count
        except Exception:
            logging.exception("Error managing metric number_message")
            return 0.0, 0
    
    def save_number_message_history(self, addr, nei, messages_number_message_normalized, current_round):
        """
        Save the number_message history of a participant (addr) regarding its neighbor (nei) in memory.

        Args:
            addr (str): The identifier of the node whose number_message history is being saved.
            nei (str): The neighboring node involved.
            messages_number_message_normalized (float): The number_message value to be saved.
            current_round (int): The current round number.

        Returns:
            float: The cumulative number_message including the current round.
        """

        try:
            key = (addr, nei)
            avg_number_message = 0

            if key not in self.number_message_history:
                self.number_message_history[key] = {}

            self.number_message_history[key][current_round] = {"number_message": messages_number_message_normalized}

            if messages_number_message_normalized != 0 and current_round > 4:
                previous_avg = (
                    self.number_message_history[key].get(current_round - 1, {}).get("avg_number_message", None)
                )
                if previous_avg is not None:
                    avg_number_message = messages_number_message_normalized * 0.8 + previous_avg * 0.2
                else:
                    avg_number_message = messages_number_message_normalized

                self.number_message_history[key][current_round]["avg_number_message"] = avg_number_message
            else:
                avg_number_message = 0

            return avg_number_message
        except Exception:
            logging.exception("Error saving number_message history")
            return -1

        except Exception as e:
            logging.exception(f"Error managing model_arrival_latency latency: {e}")
            return 0.0
    
    def save_reputation_history_in_memory(self, addr, nei, reputation):
        """
        Save the reputation history of a participant (addr) regarding its neighbor (nei) in memory
        and calculate the average reputation.

        Args:
            addr (str): The identifier of the node whose reputation is being saved.
            nei (str): The neighboring node involved.
            reputation (float): The reputation value to be saved.

        Returns:
            float: The cumulative reputation including the current round.
        """
        try:
            key = (addr, nei)

            if key not in self.reputation_history:
                self.reputation_history[key] = {}

            self.reputation_history[key][self._engine.get_round()] = reputation

            avg_reputation = 0
            current_round = self._engine.get_round()
            rounds = sorted(self.reputation_history[key].keys(), reverse=True)[:2]
            # logging.info(f"Rounds in save_reputation_history: {rounds}")

            if len(rounds) >= 2:
                current_round = rounds[0]
                previous_round = rounds[1]

                current_rep = self.reputation_history[key][current_round]
                previous_rep = self.reputation_history[key][previous_round]
                logging.info(f"Current reputation: {current_rep}, Previous reputation: {previous_rep}")

                avg_reputation = (current_rep * 0.8) + (previous_rep * 0.2)
                logging.info(f"Reputation ponderated: {avg_reputation}")
            else:
                # logging.info(f"Reputation history: {self.reputation_history}")
                avg_reputation = self.reputation_history[key][current_round]
                # logging.info(f"Current reputation: {avg_reputation}")

            return avg_reputation

            # for i, n_round in enumerate(rounds, start=1):
            #     rep = self.reputation_history[key][n_round]
            #     decay_factor = self.calculate_decay_rate(rep) ** i
            #     total_reputation += rep * decay_factor
            #     total_weights += decay_factor
            #     logging.info(
            #         f"Round: {n_round}, Reputation: {rep}, Decay: {decay_factor}, Total reputation: {total_reputation}"
            #     )

            # avg_reputation = total_reputation / total_weights
            # if total_weights > 0:
            #     return avg_reputation
            # else:
            #     return -1

        except Exception:
            logging.exception("Error saving reputation history")
            return -1

    def calculate_decay_rate(self, reputation):
        """
        Calculate the decay rate for a reputation value.

        Args:
            reputation (float): Reputation value.

        Returns:
            float: Decay rate.
        """

        if reputation > 0.8:
            return 0.9  # Very low decay
        elif reputation > 0.7:
            return 0.8  # Medium decay
        elif reputation > 0.6:
            return 0.6  # Low decay
        elif reputation > 0.4:
            return 0.2  # High decay
        else:
            return 0.1  # Very high decay

    def read_similarity_file(self, file_path, nei, current_round):
        """
        Read a similarity file and extract relevant data for each IP.

        Args:
            file_path (str): Path to the similarity file.
            nei (str): The IP address of the neighbor.
            current_round (int): The current round number.

        Returns:
            float: The similarity value.
        """
        similarity = 0.0
        try:
            with open(file_path, "r") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    source_ip = row["source_ip"].strip()
                    round_in_file = int(row.get("round", -1).strip())
                    if source_ip == nei and round_in_file == current_round:
                        weight_cosine = 0.25
                        weight_euclidean = 0.25
                        weight_manhattan = 0.25
                        weight_pearson = 0.25

                        cosine = float(row["cosine"])
                        euclidean = float(row["euclidean"])
                        manhattan = float(row["manhattan"])
                        pearson_correlation = float(row["pearson_correlation"])

                        similarity = (
                            weight_cosine * cosine
                            + weight_euclidean * euclidean
                            + weight_manhattan * manhattan
                            + weight_pearson * pearson_correlation
                        )                    
        except FileNotFoundError:
            logging.error(f"File {file_path} not found.")
        except Exception as e:
            logging.exception(f"Error reading similarity file: {e}")

        return similarity

    async def calculate_reputation(self, ae: AggregationEvent):
        """
            Calculate the reputation of the node based on the active metrics.

            Args:
                ae (AggregationEvent): The aggregation event.
        """
        (updates, _, _) = await ae.get_event_data()
        if self._with_reputation:
            logging.info(f"Calculating reputation at round {self._engine.get_round()}")
            logging.info(f"Active metrics: {self._reputation_metrics}")
            logging.info(f"rejected nodes at round {self._engine.get_round()}: {self.rejected_nodes}")

            neighbors = set(await self._engine._cm.get_addrs_current_connections(only_direct=True))
            history_data = self.history_data

            for nei in neighbors:
                metric_messages_number, metric_similarity, metric_fraction, metric_model_arrival_latency = (
                    await self.calculate_value_metrics(
                        self._log_dir,
                        self._idx,
                        self._addr,
                        nei,
                        metrics_active=self._reputation_metrics,
                    )
                )
                    
                if self._weighting_factor == "dynamic":
                    self.calculate_weighted_values(
                        metric_messages_number,
                        metric_similarity,
                        metric_fraction,
                        metric_model_arrival_latency,
                        history_data,
                        self._engine.get_round(),
                        self._addr,
                        nei,
                        self._reputation_metrics,
                    )

                if self._weighting_factor == "static" and self._engine.get_round() >= 5:
                    self._calculate_static_reputation(
                        self._addr,
                        nei,
                        metric_messages_number,
                        metric_similarity,
                        metric_fraction,
                        metric_model_arrival_latency,
                        self._weight_num_messages,
                        self._weight_model_similarity,
                        self._weight_fraction_params_changed,
                        self._weight_model_arrival_latency,
                    )
            
            if self._weighting_factor == "dynamic" and self._engine.get_round() >= 5:
                await self._calculate_dynamic_reputation(self._addr, neighbors)

            if self._engine.get_round() < 5 and self._with_reputation:
                federation = self._engine.config.participant["network_args"]["neighbors"].split()
                self.init_reputation(
                    self._addr,
                    federation_nodes=federation,
                    round_num=self._engine.get_round(),
                    last_feedback_round=-1,
                    init_reputation = self._initial_reputation,
                )

            status = await self.include_feedback_in_reputation()
            if status:
                logging.info(f"Feedback included in reputation at round {self._engine.get_round()}")
            else:
                logging.info(f"Feedback not included in reputation at round {self._engine.get_round()}")

            if self.reputation is not None:
                self.create_graphic_reputation(
                    self._addr,
                    self._engine.get_round(),
                )

                await self.update_process_aggregation(updates)
                await self.send_reputation_to_neighbors(neighbors)

    async def send_reputation_to_neighbors(self, neighbors):
        """
            Send the calculated reputation to the neighbors.
        """
        for nei, data in self.reputation.items():
            if data["reputation"] is not None:
                neighbors_to_send = [neighbor for neighbor in neighbors if neighbor != nei]

                for neighbor in neighbors_to_send:
                    message = self._engine.cm.create_message(
                        "reputation", "share", node_id=nei, score=float(data["reputation"]), round=self._engine.get_round()
                    )
                    await self._engine.cm.send_message(neighbor, message)
                    logging.info(
                        f"Sending reputation to node {nei} from node {neighbor} with reputation {data['reputation']}"
                    )
    
    def create_graphic_reputation(self, addr, round_num):
        """
        Create a graphic with the reputation of a node in a specific round.
        """
        try:
            reputation_dict_with_values = {
                f"Reputation/{addr}": {
                    node_id: float(data["reputation"])
                    for node_id, data in self.reputation.items()
                    if data["reputation"] is not None
                }
            }

            logging.info(f"Reputation dict: {reputation_dict_with_values}")
            self._engine.trainer._logger.log_data(reputation_dict_with_values, step=round_num)

        except Exception:
            logging.exception("Error creating reputation graphic")
            
    async def update_process_aggregation(self, updates):
        """
        Update the process of aggregation by removing rejected nodes from the updates.
        """
        for rn in self.rejected_nodes:
            if rn in updates:
                updates.pop(rn)

        logging.info(f"Updates after rejected nodes: {list(updates.keys())}")
        self.rejected_nodes.clear()
        logging.info(f"rejected nodes after clear at round {self._engine.get_round()}: {self.rejected_nodes}")

    async def include_feedback_in_reputation(self):
        weight_current_reputation = 0.9
        weight_feedback = 0.1

        if self.reputation_with_all_feedback is None:
            logging.info("No feedback received.")
            return False
        
        updated = False

        for(current_node, node_ip, round_num), scores in self.reputation_with_all_feedback.items():
            if not scores:
                logging.info(f"No feedback received for node {node_ip} in round {round_num}")
                continue

            if node_ip not in self.reputation:
                logging.info(f"No reputation for node {node_ip}")
                continue

            if "last_feedback_round" in self.reputation[node_ip] and self.reputation[node_ip]["last_feedback_round"] >= round_num:
                continue

            avg_feedback = sum(scores) / len(scores)
            logging.info(f"Receive feedback to node {node_ip} with average score {avg_feedback}")

            current_reputation = self.reputation[node_ip]["reputation"]
            if current_reputation is None:
                logging.info(f"No reputation calculate for node {node_ip}.")
                continue

            combined_reputation = (current_reputation * weight_current_reputation) + (avg_feedback * weight_feedback)
            logging.info(f"Combined reputation for node {node_ip} in round {round_num}: {combined_reputation}")

            self.reputation[node_ip] = {
                "reputation": combined_reputation,
                "round": self._engine.get_round(),
                "last_feedback_round": round_num,
            }
            updated = True
            logging.info(f"Updated self.reputation for {node_ip}: {self.reputation[node_ip]}")

        if updated:
            return True
        else:
            return False
    
    async def on_round_start(self, rse: RoundStartEvent):
        (round_id, start_time, expected_nodes) = await rse.get_event_data()
        if round_id not in self.round_timing_info:
            self.round_timing_info[round_id] = {}
        self.round_timing_info[round_id]["start_time"] = start_time
        expected_nodes.difference_update(self.rejected_nodes)

    async def recollect_model_arrival_latency(self, ure: UpdateReceivedEvent):
        (decoded_model, weight, source, round_num, local) = await ure.get_event_data()
        current_time = time.time()
        current_round = round_num

        if current_round not in self.round_timing_info:
            self.round_timing_info[current_round] = {}
        
        if "model_received_time" not in self.round_timing_info[current_round]:
            self.round_timing_info[current_round]["model_received_time"] = {}

        if source not in self.round_timing_info[current_round]["model_received_time"]:
            self.round_timing_info[current_round]["model_received_time"][source] = current_time

            if "start_time" in self.round_timing_info[current_round]:
                start = self.round_timing_info[current_round]["start_time"]
                received_time = self.round_timing_info[current_round]["model_received_time"][source]
                duration = received_time - start
                self.round_timing_info[current_round]["duration"] = duration
                logging.info(f"Source {source} , round {current_round}, duration: {duration:.4f} seconds")

                self.save_data(
                    "model_arrival_latency",
                    source,
                    self._addr,
                    num_round=current_round,
                    current_round=self._engine.get_round(),
                    latency=duration,
                )
        else:
            logging.info(f"Model arrival latency already calculated for node {source} in round {current_round}")

    async def recollect_similarity(self, ure: UpdateReceivedEvent):
        (decoded_model, weight, source, round_num, local) = await ure.get_event_data()
        if self._with_reputation and self._reputation_metrics.get("model_similarity"):
            if self._engine.config.participant["adaptive_args"]["model_similarity"]:
                if source != self._addr:
                    logging.info("🤖  handle_model_message | Checking model similarity")
                    cosine_value = cosine_metric(
                        self._engine.trainer.get_model_parameters(),
                        decoded_model,
                        similarity=True,
                    )
                    euclidean_value = euclidean_metric(
                        self._engine.trainer.get_model_parameters(),
                        decoded_model,
                        similarity=True,
                    )
                    minkowski_value = minkowski_metric(
                        self._engine.trainer.get_model_parameters(),
                        decoded_model,
                        p=2,
                        similarity=True,
                    )
                    manhattan_value = manhattan_metric(
                        self._engine.trainer.get_model_parameters(),
                        decoded_model,
                        similarity=True,
                    )
                    pearson_correlation_value = pearson_correlation_metric(
                        self._engine.trainer.get_model_parameters(),
                        decoded_model,
                        similarity=True,
                    )
                    jaccard_value = jaccard_metric(
                        self._engine.trainer.get_model_parameters(),
                        decoded_model,
                        similarity=True,
                    )
                    file = f"{self._log_dir}/participant_{self._idx}_similarity.csv"
                    directory = os.path.dirname(file)
                    os.makedirs(directory, exist_ok=True)
                    if not os.path.isfile(file):
                        with open(file, "w") as f:
                            f.write(
                                "timestamp,source_ip,round,current_round,cosine,euclidean,minkowski,manhattan,pearson_correlation,jaccard\n"
                            )
                    with open(file, "a") as f:
                        f.write(
                            f"{datetime.now()}, {source}, {round_num}, {self._engine.get_round()}, {cosine_value}, {euclidean_value}, {minkowski_value}, {manhattan_value}, {pearson_correlation_value}, {jaccard_value}\n"
                        )

                    if cosine_value < 0.6:
                        logging.info("🤖  handle_model_message | Model similarity is less than 0.6")
                        self.rejected_nodes.add(source)

    async def recollect_number_message(self, source, message):
        if source != self._addr:
            current_time = time.time()
            if current_time:
                self.save_data(
                    "number_message",
                    source,
                    self._addr,
                    time=current_time,
                    current_round=self._engine.get_round(),
                )

    async def recollect_fraction_of_parameters_changed(self, ure: UpdateReceivedEvent):
        (decoded_model, weight, source, round_num, local) = await ure.get_event_data()
        current_round = self._engine.get_round()
        parameters_local = self._engine.trainer.get_model_parameters()
        parameters_received = decoded_model
        differences = []
        total_params = 0
        changed_params = 0
        changes_record = {}
        prev_threshold = None

        if source in self.fraction_of_params_changed and current_round - 1 in self.fraction_of_params_changed[source]:
            prev_threshold = self.fraction_of_params_changed[source][current_round - 1][-1]["threshold"]

        for key in parameters_local.keys():
            # logging.info(f"🤖  fraction_of_parameters_changed | Key: {key}")
            if key in parameters_received:
                diff = torch.abs(parameters_local[key] - parameters_received[key])
                differences.extend(diff.flatten().tolist())
                total_params += diff.numel()
                # logging.info(f"🤖  fraction_of_parameters_changed | Total params: {total_params}")

        if differences:
            mean_threshold = torch.mean(torch.tensor(differences)).item()
            current_threshold = (prev_threshold + mean_threshold) / 2 if prev_threshold is not None else mean_threshold
        else:
            current_threshold = 0

        for key in parameters_local.keys():
            if key in parameters_received:
                diff = torch.abs(parameters_local[key] - parameters_received[key])
                num_changed = torch.sum(diff > current_threshold).item()
                changed_params += num_changed
                if num_changed > 0:
                    changes_record[key] = num_changed

        fraction_changed = changed_params / total_params if total_params > 0 else 0.0

        if source not in self.fraction_of_params_changed:
            self.fraction_of_params_changed[source] = {}
        if current_round not in self.fraction_of_params_changed[source]:
            self.fraction_of_params_changed[source][current_round] = []

        self.fraction_of_params_changed[source][current_round].append({
            "fraction_changed": fraction_changed,
            "total_params": total_params,
            "changed_params": changed_params,
            "threshold": current_threshold,
            "changes_record": changes_record,
        })

        self.save_data(
            "fraction_of_params_changed",
            source,
            self._addr,
            current_round,
            fraction_changed=fraction_changed,
            total_params=total_params,
            changed_params=changed_params,
            threshold=current_threshold,
            changes_record=changes_record,
        )