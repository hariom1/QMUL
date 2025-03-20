import csv
import json
import logging
import os
import random
from typing import TYPE_CHECKING, ClassVar

import numpy as np

if TYPE_CHECKING:
    from nebula.core.engine import Engine


def save_data(
    scenario,
    type_data,
    source_ip,
    addr,
    num_round=None,
    time=None,
    type_message=None,
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

    Args:
        source_ip (str): Source IP address.
        addr (str): Destination IP address.
        round (int): Round number.
        time (float): Time taken to process the data.
    """

    try:
        combined_data = {}

        if type_data == "number_message":
            combined_data["number_message"] = {
                "time": time,
                "type_message": type_message,
                "round": num_round,
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

        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_name = f"{addr}_storing_{source_ip}_info.json"
        full_file_path = os.path.join(script_dir, scenario, file_name)
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

class Reputation:
    """
    Class to define the reputation of a participant.
    """

    reputation_history: ClassVar[dict] = {}
    number_message_history: ClassVar[dict] = {}
    neighbor_reputation_history: ClassVar[dict] = {}
    fraction_changed_history: ClassVar[dict] = {}
    messages_number_message: ClassVar[list] = []
    previous_threshold_number_message: ClassVar[dict] = {}
    previous_std_dev_number_message: ClassVar[dict] = {}
    messages_model_arrival_latency: ClassVar[dict] = {}
    model_arrival_latency_history: ClassVar[dict] = {}
    previous_percentile_25_number_message: ClassVar[dict] = {}
    previous_percentile_85_number_message: ClassVar[dict] = {}

    def __init__(self, engine: "Engine"):
        self._engine = engine
        self.model_arrival_latency_data = {}
        self.history_data = {}
        self.metric_weights = {}

    @property
    def engine(self):
        return self._engine

    def init_reputation(self, addr, federation_nodes=None, round_num=None, last_feedback_round=None, scenario=None, init_reputation=None):
        """
        Initialize the reputation system.
        """
        if not federation_nodes:
            logging.error("init_reputation | No federation nodes provided")
            return

        if self._engine.with_reputation:
            # logging.info("init_reputation | Reputation system enabled")
            neighbors = Reputation.is_valid_ip(federation_nodes)

            if not neighbors:
                logging.error("init_reputation | No neighbors found")
                return

            for nei in neighbors:
                if nei not in self._engine.reputation:
                    self._engine.reputation[nei] = {
                        "reputation": init_reputation,
                        "round": round_num,
                        "last_feedback_round": last_feedback_round,
                    }
                elif self._engine.reputation[nei].get("reputation") is None:
                    self._engine.reputation[nei]["reputation"] = init_reputation
                    self._engine.reputation[nei]["round"] = round_num
                    self._engine.reputation[nei]["last_feedback_round"] = last_feedback_round

                avg_reputation = self.save_reputation_history_in_memory(
                    self._engine.addr, nei, init_reputation, round_num
                )

                metrics_data = {
                    "addr": addr,
                    "nei": nei,
                    "round": round_num,
                    "reputation_without_feedback": avg_reputation,
                }

                self.metrics(
                    scenario,
                    metrics_data,
                    addr,
                    nei,
                    "reputation",
                    update_field="reputation_without_feedback",
                )

    def is_valid_ip(federation_nodes):
        """
        Check if the IP addresses are valid.
        """
        valid_ip = []
        for i in federation_nodes:   
            valid_ip.append(i)

        return valid_ip

    def _calculate_static_reputation(self, addr, nei, metric_messages_number, metric_similarity, metric_fraction, metric_model_arrival_latency, current_round,
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
            current_round (int): The current round number.
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

        avg_reputation = self.save_reputation_history_in_memory(
            self.engine.addr, nei, reputation_static, current_round
        )

        metrics_data = {
            "addr": addr,
            "nei": nei,
            "round": self.engine.get_round(),
            "reputation_without_feedback": avg_reputation,
        }

        for metric_name in metric_values:
            metrics_data[f"average_{metric_name}"] = static_weights[metric_name]

        self._update_reputation_record(nei, avg_reputation, current_round, metrics_data)

    async def _calculate_dynamic_reputation(self, addr, current_round, neighbors):
        """
        Calculate the dynamic reputation of a participant.

        Args:
            addr (str): The IP address of the participant.
            current_round (int): The current round number.
            neighbors (list): The list of neighbors.

        Returns:
            dict: The dynamic reputation of the participant.
        """
        average_weights = {}

        for metric_name in self.history_data.keys():
            if self.engine.reputation_metrics.get(metric_name, False):
                valid_entries = [
                    entry for entry in self.history_data[metric_name]
                    if entry["round"] >= current_round and entry.get("weight") not in [None, -1]
                ]

                if valid_entries:
                    average_weight = sum([entry["weight"] for entry in valid_entries]) / len(valid_entries)
                    average_weights[metric_name] = average_weight
                else:
                    average_weights[metric_name] = 0

        for nei in neighbors:
            metric_values = {}
            for metric_name in self.history_data.keys():
                if self.engine.reputation_metrics.get(metric_name, False):
                    for entry in self.history_data.get(metric_name, []):
                        if entry["round"] == current_round and entry["metric_name"] == metric_name and entry["nei"] == nei:
                            metric_values[metric_name] = entry["metric_value"]
                            break

            if all(metric_name in metric_values for metric_name in average_weights):
                reputation_with_weights = sum(
                    metric_values.get(metric_name, 0) * average_weights[metric_name]
                    for metric_name in average_weights
                )
                logging.info(f"Dynamic reputation with weights for {nei} at round {self.engine.get_round()}: {reputation_with_weights}")

                avg_reputation = self.save_reputation_history_in_memory(
                    self.engine.addr, nei, reputation_with_weights, current_round
                )

                metrics_data = {
                    "addr": addr,
                    "nei": nei,
                    "round": self.engine.get_round(),
                    "reputation_without_feedback": avg_reputation,
                }

                for metric_name in metric_values:
                    metrics_data[f"average_{metric_name}"] = average_weights[metric_name]

                self._update_reputation_record(nei, avg_reputation, current_round, metrics_data)

    def _update_reputation_record(self, nei, reputation, current_round, data):
        """
        Update the reputation record of a participant.

        Args:
            nei (str): The IP address of the participant.
            reputation (float): The reputation of the participant.
            current_round (int): The current round number.
        """
        if nei not in self.engine.reputation:
            self.engine.reputation[nei] = {
                "reputation": reputation,
                "round": current_round,
                "last_feedback_round": -1,
            }
        else:
            self.engine.reputation[nei]["reputation"] = reputation
            self.engine.reputation[nei]["round"] = current_round

        logging.info(f"Reputation of node {nei}: {self.engine.reputation[nei]['reputation']}")
        if self.engine.reputation[nei]["reputation"] < 0.6:
            self.engine.rejected_nodes.add(nei)
            logging.info(f"Rejected node {nei} at round {self.engine.get_round()}")

        self.metrics(
            self.engine.experiment_name,
            data,
            self.engine.addr,
            nei,
            "reputation",
            update_field="reputation_without_feedback",
        )

    @staticmethod
    def calculate_weighted_values(
        avg_messages_number_message_normalized,
        similarity_reputation,
        fraction_score_asign,
        avg_model_arrival_latency,
        history_data: dict,
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

    def calculate_value_metrics(self, scenario, log_dir, id_node, addr, nei, current_round=None, metrics_active=None):
        """
        Calculate the reputation of each participant based on the data stored.

        Args:
            scenario (str): Scenario name.
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

        logging.info(f"Metrics active: {metrics_active}")

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            file_name = f"{addr}_storing_{nei}_info.json"
            full_file_path = os.path.join(script_dir, scenario, file_name)
            os.makedirs(os.path.dirname(full_file_path), exist_ok=True)

            if os.path.exists(full_file_path) and os.path.getsize(full_file_path) > 0:
                with open(full_file_path) as json_file:
                    all_metrics = json.load(json_file)
                    for metric in all_metrics:
                        if "number_message" in metric and metrics_active.get("num_messages", False):
                            round_time = metric["number_message"]["round"]
                            current_round_time = metric["number_message"]["current_round"]
                            time = metric["number_message"]["time"]
                            type_message = metric["number_message"]["type_message"]
                            previous_round_time = current_round - 1
                            if round_time == previous_round_time:
                                Reputation.messages_number_message.append({
                                    "number_message": time,
                                    "type_message": type_message,
                                    "round": round_time,
                                    "current_round": current_round_time,
                                    "key": (addr, nei),
                                })

                        if "fraction_of_params_changed" in metric and metrics_active.get("fraction_parameters_changed", False):
                            round_fraction = metric["fraction_of_params_changed"]["round"]
                            fraction_changed = metric["fraction_of_params_changed"]["fraction_changed"]
                            threshold = metric["fraction_of_params_changed"]["threshold"]
                            if round_fraction == current_round:
                                fraction_score_normalized = Reputation.analyze_anomalies(
                                    addr,
                                    nei,
                                    round_fraction,
                                    current_round,
                                    fraction_changed,
                                    threshold,
                                    scenario,
                                )

                        if "model_arrival_latency" in metric and metrics_active.get("model_arrival_latency", False):
                            round_latency = metric["model_arrival_latency"]["round"]
                            round_received = metric["model_arrival_latency"]["round_received"]
                            latency = metric["model_arrival_latency"]["latency"]
                            score_asigned = None
                            if round_received == current_round:
                                messages_model_arrival_latency_normalized = Reputation.manage_model_arrival_latency(
                                    round_latency,
                                    addr,
                                    nei,
                                    latency,
                                    scenario,
                                    self.model_arrival_latency_data,
                                    current_round,
                                    self.engine.config.participant["aggregator_args"]["aggregation_timeout"],
                                )
                            # elif round_latency < current_round:
                            #     if current_round in Reputation.model_arrival_latency_history:
                            #         if nei in Reputation.model_arrival_latency_history[current_round]:
                            #             if "latency" in Reputation.model_arrival_latency_history[current_round][nei]:
                            #                 if "score" in Reputation.model_arrival_latency_history[current_round][nei]:
                            #                     score_asigned = Reputation.model_arrival_latency_history[current_round][
                            #                         nei
                            #                     ]["score"]

                            #     if score_asigned is None:
                            #         for round in range(current_round, current_round + 1):
                            #             latency = self.engine.config.participant["aggregator_args"][
                            #                 "aggregation_timeout"
                            #             ]
                            #             messages_model_arrival_latency_normalized = (
                            #                 Reputation.manage_model_arrival_latency(
                            #                     round_latency,
                            #                     addr,
                            #                     nei,
                            #                     latency,
                            #                     scenario,
                            #                     self.model_arrival_latency_data,
                            #                     current_round,
                            #                 )
                            #             )

                    if current_round >= 5 and metrics_active.get("model_similarity", False):
                        similarity_file = os.path.join(log_dir, f"participant_{id_node}_similarity.csv")
                        similarity_reputation = Reputation.read_similarity_file(similarity_file, nei, current_round)
                    else:
                        similarity_reputation = 0

                    if messages_model_arrival_latency_normalized >= 0:
                        avg_model_arrival_latency = Reputation.save_model_arrival_latency_history(
                            addr, nei, messages_model_arrival_latency_normalized, current_round
                        )
                        if avg_model_arrival_latency is None and current_round > 4:
                            avg_model_arrival_latency = Reputation.model_arrival_latency_history[(addr, nei)][
                                current_round - 1
                            ]["score"]

                    if Reputation.messages_number_message is not None:
                        messages_number_message_normalized, messages_number_message_count = (
                            Reputation.manage_metric_number_message(
                                Reputation.messages_number_message, addr, nei, current_round, scenario, metrics_active.get("num_messages", False)
                            )
                        )
                        avg_messages_number_message_normalized = Reputation.save_number_message_history(
                            addr, nei, messages_number_message_normalized, current_round
                        )
                        if avg_messages_number_message_normalized is None and current_round > 4:
                            avg_messages_number_message_normalized = Reputation.number_message_history[(addr, nei)][current_round - 1]["avg_number_message"]

                    if current_round >= 5:
                        if fraction_score_normalized > 0:
                            key_previous_round = (addr, nei, current_round - 1) if current_round - 1 > 0 else None
                            fraction_previous_round = None

                            if (key_previous_round is not None and key_previous_round in Reputation.fraction_changed_history):
                                fraction_score = Reputation.fraction_changed_history[key_previous_round].get("fraction_score")
                                fraction_previous_round = fraction_score if fraction_score is not None else None

                            if fraction_previous_round is not None:
                                fraction_score_asign = fraction_score_normalized * 0.8 + fraction_previous_round * 0.2
                                Reputation.fraction_changed_history[(addr, nei, current_round)]["fraction_score"] = (fraction_score_asign)
                            else:
                                fraction_score_asign = fraction_score_normalized
                                Reputation.fraction_changed_history[(addr, nei, current_round)]["fraction_score"] = (fraction_score_asign)
                        else:
                            fraction_previous_round = None
                            key_previous_round = (addr, nei, current_round - 1) if current_round - 1 > 0 else None
                            if (key_previous_round is not None and key_previous_round in Reputation.fraction_changed_history):
                                fraction_score = Reputation.fraction_changed_history[key_previous_round].get("fraction_score")
                                fraction_previous_round = fraction_score if fraction_score is not None else None

                            if fraction_previous_round is not None:
                                fraction_score_asign = fraction_previous_round - (fraction_previous_round * 0.5)
                            else:
                                if fraction_neighbors_scores is None:
                                    fraction_neighbors_scores = {}

                                for key, value in Reputation.fraction_changed_history.items():
                                    score = value.get("fraction_score")
                                    if score is not None:
                                        fraction_neighbors_scores[key] = score

                                if fraction_neighbors_scores:
                                    fraction_score_asign = np.mean(list(fraction_neighbors_scores.values()))
                                else:
                                    fraction_score_asign = 0  # O un valor predeterminado adecuado
                    else:
                        fraction_score_asign = 0

                    # Create graphics to metrics
                    self.create_graphics_to_metrics(
                        messages_number_message_count,
                        avg_messages_number_message_normalized,
                        similarity_reputation,
                        fraction_score_asign,
                        avg_model_arrival_latency,
                        addr,
                        nei,
                        current_round,
                        self.engine.total_rounds,
                        scenario,
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
        scenario,
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

            data = {
                "addr": addr,
                "nei": nei,
                "round": current_round,
                "number_message_count": number_message_count,
                "number_message_norm": number_message_norm,
                "similarity": similarity,
                "fraction": fraction,
                "model_arrival_latency": model_arrival_latency,
            }
            Reputation.metrics(scenario, data, addr, nei, "reputation")

    @staticmethod
    def analyze_anomalies(
        addr,
        nei,
        round_num,
        current_round,
        fraction_changed,
        threshold,
        scenario,
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
            scenario (str): The scenario name for logging and metric storage.

        Returns:
            float: The fraction score between 0 and 1.
        """
        try:
            key = (addr, nei, round_num)

            if key not in Reputation.fraction_changed_history:
                prev_key = (addr, nei, round_num - 1)
                if round_num > 0 and prev_key in Reputation.fraction_changed_history:
                    previous_data = Reputation.fraction_changed_history[prev_key]
                    fraction_changed = (
                        fraction_changed if fraction_changed is not None else previous_data["fraction_changed"]
                    )
                    threshold = threshold if threshold is not None else previous_data["threshold"]
                else:
                    fraction_changed = fraction_changed if fraction_changed is not None else 0
                    threshold = threshold if threshold is not None else 0

                Reputation.fraction_changed_history[key] = {
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
                    if past_key in Reputation.fraction_changed_history:
                        past_fractions.append(Reputation.fraction_changed_history[past_key]["fraction_changed"])
                        past_thresholds.append(Reputation.fraction_changed_history[past_key]["threshold"])

                if past_fractions:
                    mean_fraction = np.mean(past_fractions)
                    std_dev_fraction = np.std(past_fractions)
                    Reputation.fraction_changed_history[key]["mean_fraction"] = mean_fraction
                    Reputation.fraction_changed_history[key]["std_dev_fraction"] = std_dev_fraction

                if past_thresholds:
                    mean_threshold = np.mean(past_thresholds)
                    std_dev_threshold = np.std(past_thresholds)
                    Reputation.fraction_changed_history[key]["mean_threshold"] = mean_threshold
                    Reputation.fraction_changed_history[key]["std_dev_threshold"] = std_dev_threshold

                return 0
            else:
                fraction_value = 0
                threshold_value = 0
                prev_key = (addr, nei, round_num - 1)
                if prev_key not in Reputation.fraction_changed_history:
                    for i in range(0, round_num + 1):
                        potential_prev_key = (addr, nei, round_num - i)
                        if potential_prev_key in Reputation.fraction_changed_history:
                            mean_fraction_prev = Reputation.fraction_changed_history[potential_prev_key][
                                "mean_fraction"
                            ]
                            if mean_fraction_prev is not None:
                                prev_key = potential_prev_key
                                break

                if prev_key:
                    mean_fraction_prev = Reputation.fraction_changed_history[prev_key]["mean_fraction"]
                    std_dev_fraction_prev = Reputation.fraction_changed_history[prev_key]["std_dev_fraction"]
                    mean_threshold_prev = Reputation.fraction_changed_history[prev_key]["mean_threshold"]
                    std_dev_threshold_prev = Reputation.fraction_changed_history[prev_key]["std_dev_threshold"]

                    current_fraction = Reputation.fraction_changed_history[key]["fraction_changed"]
                    current_threshold = Reputation.fraction_changed_history[key]["threshold"]

                    upper_mean_fraction_prev = (mean_fraction_prev + std_dev_fraction_prev) * 1.05
                    upper_mean_threshold_prev = (mean_threshold_prev + std_dev_threshold_prev) * 1.10

                    fraction_anomaly = current_fraction > upper_mean_fraction_prev
                    threshold_anomaly = current_threshold > upper_mean_threshold_prev

                    Reputation.fraction_changed_history[key]["fraction_anomaly"] = fraction_anomaly
                    Reputation.fraction_changed_history[key]["threshold_anomaly"] = threshold_anomaly

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

                    Reputation.fraction_changed_history[key]["mean_fraction"] = (current_fraction + mean_fraction_prev) / 2
                    Reputation.fraction_changed_history[key]["std_dev_fraction"] = np.sqrt(((current_fraction - mean_fraction_prev) ** 2 + std_dev_fraction_prev**2) / 2)
                    Reputation.fraction_changed_history[key]["mean_threshold"] = (current_threshold + mean_threshold_prev) / 2
                    Reputation.fraction_changed_history[key]["std_dev_threshold"] = np.sqrt(((0.1 * (current_threshold - mean_threshold_prev) ** 2) + std_dev_threshold_prev**2) / 2)

                    data = {
                        "addr": addr,
                        "nei": nei,
                        "round": current_round,
                        "fraction_changed": current_fraction,
                        "threshold": current_threshold,
                        "mean_fraction": mean_fraction_prev,
                        "std_dev_fraction": std_dev_fraction_prev,
                        "mean_threshold": mean_threshold_prev,
                        "std_dev_threshold": std_dev_threshold_prev,
                        "upper_mean_fraction": upper_mean_fraction_prev,
                        "upper_mean_threshold": upper_mean_threshold_prev,
                        "fraction_anomaly": fraction_anomaly,
                        "threshold_anomaly": threshold_anomaly,
                        "penalization_factor_fraction": penalization_factor_fraction,
                        "penalization_factor_threshold": penalization_factor_threshold,
                        "k_fraction": k_fraction,
                        "k_threshold": k_threshold,
                        "fraction_value": fraction_value,
                        "threshold_value": threshold_value,
                        "fraction_score": fraction_score,
                    }
                    Reputation.metrics(scenario, data, addr, nei, "fraction_changed")

                    return max(fraction_score, 0)
                else:
                    return -1
        except Exception:
            logging.exception("Error analyzing anomalies")
            return -1

    @staticmethod
    def manage_model_arrival_latency(
        round_num, addr, nei, latency, scenario, model_arrival_latency_data, current_round, aggregation_timeout
    ):
        """
        Manage the model_arrival_latency metric with persistent storage of mean latency.

        Args:
            round_num (int): The round number.
            addr (str): Source IP address.
            nei (str): Destination IP address.
            latency (float): Latency value for the current model_arrival_latency.
            scenario (str): The scenario name for logging and metric storage.
            model_arrival_latency_data (dict): model_arrival_latency-related data.
            current_round (int): The current round of the program.

        Returns:
            float: Normalized model_arrival_latency latency value between 0 and 1.
        """
        try:
            current_key = nei

            if current_round not in Reputation.model_arrival_latency_history:
                Reputation.model_arrival_latency_history[current_round] = {}

            Reputation.model_arrival_latency_history[current_round][current_key] = {
                "latency": latency,
                "score": 0.0,
            }

            prev_mean_latency = 0
            prev_percentil_25 = 0
            prev_percentil_75 = 0
            difference = 0

            if current_round >= 5:
                for r in range(current_round - 1, 4, -1):
                    if r in Reputation.model_arrival_latency_history and current_key in Reputation.model_arrival_latency_history[r]:
                        prev_mean_latency = Reputation.model_arrival_latency_history[r][current_key].get("mean_latency", 0)
                        prev_percentil_25 = Reputation.model_arrival_latency_history[r][current_key].get("percentil_25", 0)
                        prev_percentil_75 = Reputation.model_arrival_latency_history[r][current_key].get("percentil_75", 0)
                        if prev_mean_latency and prev_percentil_25 and prev_percentil_75:
                            break

                if current_round == 5:
                    all_latencies = [
                        data["latency"]
                        for r in range(5)
                        if r in Reputation.model_arrival_latency_history
                        for key, data in Reputation.model_arrival_latency_history[r].items()
                        if "latency" in data and data["latency"] != 0
                    ]

                    prev_mean_latency = np.mean(all_latencies) if all_latencies else 0
                    prev_percentil_25 = np.percentile(all_latencies, 25) if all_latencies else 0
                    prev_percentil_75 = np.percentile(all_latencies, 75) if all_latencies else 0

                k = 0.2
                prev_mean_latency += k * (prev_percentil_75 - prev_percentil_25)

                if latency == 0.0:
                    latency = 0.5

                difference = latency - prev_mean_latency
                # if latency <= prev_mean_latency or abs(difference) <= prev_mean_latency:
                if latency <= prev_mean_latency or latency <= aggregation_timeout:
                    score = 1.0
                else:
                    score = 1 / (1 + np.exp(abs(difference) / prev_mean_latency))

                if round_num < current_round:
                    logging.info(f"Round: {round_num} < Current round: {current_round} to node {nei}")
                    round_diff = current_round - round_num
                    penalty_factor = round_diff * 0.1
                    penalty = penalty_factor * (1 - score)
                    score -= penalty * score

                accumulated_latencies = [
                    data["latency"]
                    for r in range(current_round + 1)
                    if r in Reputation.model_arrival_latency_history
                    for key, data in Reputation.model_arrival_latency_history[r].items()
                    if "latency" in data and data["latency"] != 0
                ]

                updated_percentil_25 = np.percentile(accumulated_latencies, 25) if accumulated_latencies else 0
                updated_percentil_75 = np.percentile(accumulated_latencies, 75) if accumulated_latencies else 0

                Reputation.model_arrival_latency_history[current_round][current_key].update({
                    "mean_latency": prev_mean_latency,
                    "percentil_25": updated_percentil_25,
                    "percentil_75": updated_percentil_75,
                    "score": score,
                })
            else:
                score = 0

            data = {
                "addr": addr,
                "nei": nei,
                "round": current_round,
                "latency": latency,
                "mean_latency": prev_mean_latency if current_round >= 5 else None,
                "percentil_25": prev_percentil_25 if current_round >= 5 else None,
                "percentil_75": prev_percentil_75 if current_round >= 5 else None,
                "difference": difference if current_round >= 5 else None,
                "score": score,
            }
            Reputation.metrics(scenario, data, addr, nei, "model_arrival_latency")

            return score

        except Exception as e:
            logging.exception(f"Error managing model_arrival_latency: {e}")
            return 0

    @staticmethod
    def save_model_arrival_latency_history(addr, nei, model_arrival_latency, round_num):
        """
        Save the model_arrival_latency history of a participant (addr) regarding its neighbor (nei) in memory.

        Args:
            addr (str): The identifier of the node whose model_arrival_latency history is being saved.
            nei (str): The neighboring node involved.
            model_arrival_latency (float): The model_arrival_latency value to be saved.
            current_round (int): The current round number.

        Returns:
            float: The cumulative model_arrival_latency including the current round.
        """
        try:
            current_key = nei

            if round_num not in Reputation.model_arrival_latency_history:
                Reputation.model_arrival_latency_history[round_num] = {}

            if current_key not in Reputation.model_arrival_latency_history[round_num]:
                Reputation.model_arrival_latency_history[round_num][current_key] = {}

            Reputation.model_arrival_latency_history[round_num][current_key].update({
                "score": model_arrival_latency,
            })

            if model_arrival_latency > 0 and round_num > 5:
                previous_avg = (
                    Reputation.model_arrival_latency_history.get(round_num - 1, {})
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
                    Reputation.model_arrival_latency_history.get(round_num - 1, {})
                    .get(current_key, {})
                    .get("avg_model_arrival_latency", None)
                )
                avg_model_arrival_latency = previous_avg - (previous_avg * 0.05)
            else:
                avg_model_arrival_latency = model_arrival_latency

            Reputation.model_arrival_latency_history[round_num][current_key]["avg_model_arrival_latency"] = (
                avg_model_arrival_latency
            )

            return avg_model_arrival_latency
        except Exception:
            logging.exception("Error saving model_arrival_latency history")

    @staticmethod
    def manage_metric_number_message(messages_number_message, addr, nei, current_round, scenario, metric_active=True):
        """
        Manage the number_message metric using percentiles for normalization, considering the last 5 rounds dynamically.

        Args:
            messages_number_message (list): List of messages number_message.
            addr (str): Source IP address.
            nei (str): Destination IP address.
            current_round (int): Current round number.

        Returns:
            float: Normalized number_message value.
            int: Messages count.
        """
        try:
            if current_round == 0:
                return 0.0, 0

            if not metric_active:
                return 0.0, 0

            previous_round = current_round - 1

            current_addr_nei = (addr, nei)
            relevant_messages = [
                msg
                for msg in messages_number_message
                if msg["key"] == current_addr_nei and msg["round"] == previous_round
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
                len([m for m in messages_number_message if m["key"] == current_addr_nei and m["round"] == r])
                for r in rounds_to_consider
            ]

            Reputation.previous_percentile_25_number_message[current_addr_nei] = (
                np.percentile(previous_counts, 25) if previous_counts else 0
            )
            Reputation.previous_percentile_85_number_message[current_addr_nei] = (
                np.percentile(previous_counts, 85) * 1.20 if previous_counts else 0
            )

            normalized_messages = 1.0
            relative_position = 0

            if previous_round > 4:
                percentile_25 = Reputation.previous_percentile_25_number_message.get(current_addr_nei, 0)
                percentile_85 = Reputation.previous_percentile_85_number_message.get(current_addr_nei, 0)

                if messages_count > percentile_85:
                    relative_position = (messages_count - percentile_85) / (percentile_85 - percentile_25)
                    normalized_messages = np.exp(-relative_position)

                normalized_messages = max(0.01, normalized_messages)

            data = {
                "addr": addr,
                "nei": nei,
                "round": current_round,
                "messages_count": messages_count,
                "normalized_messages": normalized_messages,
                "percentile_25": Reputation.previous_percentile_25_number_message[current_addr_nei],
                "percentile_85": Reputation.previous_percentile_85_number_message[current_addr_nei],
            }
            Reputation.metrics(scenario, data, addr, nei, "number_message")

            return normalized_messages, messages_count
        except Exception:
            logging.exception("Error managing metric number_message")
            return 0.0, 0
    
    @staticmethod
    def save_number_message_history(addr, nei, messages_number_message_normalized, current_round):
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

            if key not in Reputation.number_message_history:
                Reputation.number_message_history[key] = {}

            Reputation.number_message_history[key][current_round] = {"number_message": messages_number_message_normalized}

            
            if messages_number_message_normalized != 0 and current_round > 4:
                previous_avg = (
                    Reputation.number_message_history[key].get(current_round - 1, {}).get("avg_number_message", None)
                )
                if previous_avg is not None:
                    avg_number_message = messages_number_message_normalized * 0.8 + previous_avg * 0.2
                else:
                    avg_number_message = messages_number_message_normalized

                Reputation.number_message_history[key][current_round]["avg_number_message"] = avg_number_message
            else:
                avg_number_message = 0

            return avg_number_message
        except Exception:
            logging.exception("Error saving number_message history")
            return -1

        except Exception as e:
            logging.exception(f"Error managing model_arrival_latency latency: {e}")
            return 0.0
    
    @staticmethod
    def save_reputation_history_in_memory(addr, nei, reputation, current_round):
        """
        Save the reputation history of a participant (addr) regarding its neighbor (nei) in memory
        and calculate the average reputation.

        Args:
            addr (str): The identifier of the node whose reputation is being saved.
            nei (str): The neighboring node involved.
            reputation (float): The reputation value to be saved.
            current_round (int): The current round number.

        Returns:
            float: The cumulative reputation including the current round.
        """
        try:
            key = (addr, nei)

            if key not in Reputation.reputation_history:
                Reputation.reputation_history[key] = {}

            Reputation.reputation_history[key][current_round] = reputation

            avg_reputation = 0
            rounds = sorted(Reputation.reputation_history[key].keys(), reverse=True)[:2]
            # logging.info(f"Rounds in save_reputation_history: {rounds}")

            if len(rounds) >= 2:
                current_round = rounds[0]
                previous_round = rounds[1]

                current_rep = Reputation.reputation_history[key][current_round]
                previous_rep = Reputation.reputation_history[key][previous_round]
                logging.info(f"Current reputation: {current_rep}, Previous reputation: {previous_rep}")

                avg_reputation = (current_rep * 0.8) + (previous_rep * 0.2)
                logging.info(f"Reputation ponderated: {avg_reputation}")
            else:
                logging.info(f"Reputation history: {Reputation.reputation_history}")
                avg_reputation = Reputation.reputation_history[key][current_round]
                logging.info(f"Current reputation: {avg_reputation}")

            return avg_reputation

            # for i, n_round in enumerate(rounds, start=1):
            #     rep = Reputation.reputation_history[key][n_round]
            #     decay_factor = Reputation.calculate_decay_rate(rep) ** i
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

    @staticmethod
    def calculate_decay_rate(reputation):
        """
        Calculate the decay rate for a reputation value.

        Args:
            reputation (float): Reputation value.

        Returns:
            float: Decay rate.
        """

        if reputation > 0.8:
            return 0.9  # Muy bajo decaimiento
        elif reputation > 0.7:
            return 0.8  # Bajo decaimiento
        elif reputation > 0.6:
            return 0.6  # Bajo decaimiento
        elif reputation > 0.4:
            return 0.2  # Alto decaimiento
        else:
            return 0.1  # Muy alto decaimiento

    @staticmethod
    def read_similarity_file(file_path, nei, current_round):
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
        
    @staticmethod
    def metrics(scenario, data, addr, nei, type, update_field=None):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        csv_path = os.path.join(current_dir, f"{scenario}/metrics/{type}/{addr}_{nei}_{type}.csv")
        csv_dir = os.path.dirname(csv_path)

        if not os.path.exists(csv_dir):
            os.makedirs(csv_dir)

        if type != "reputation":
            try:
                with open(csv_path, mode="a", newline="") as file:
                    writer = csv.DictWriter(file, fieldnames=data.keys())
                    if file.tell() == 0:
                        writer.writeheader()
                    writer.writerow(data)
            except Exception:
                logging.exception("Error saving messages number_message data to CSV")
        else:
            rows = []
            updated = False

            fieldnames = [
                "addr",
                "nei",
                "round",
                "number_message_count",
                "number_message_norm",
                "similarity",
                "fraction",
                "model_arrival_latency",
                "reputation_without_feedback",
                "reputation_with_feedback",
                "average_model_arrival_latency",
                "average_model_similarity",
                "average_fraction_parameters_changed",
                "average_num_messages",
            ]

            if os.path.exists(csv_path):
                with open(csv_path, newline="") as file:
                    rows = list(csv.DictReader(file))

                if update_field:
                    for row in rows:
                        if int(row["round"]) == int(data["round"]):
                            row.update(data)
                            updated = True
                            break

            if not updated:
                rows.append(data)

            with open(csv_path, mode="w", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
