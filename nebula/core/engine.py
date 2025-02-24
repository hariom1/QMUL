import asyncio
import logging
import os

import docker

from nebula.addons.attacks.attacks import create_attack
from nebula.addons.functions import print_msg_box
from nebula.addons.reporter import Reporter
from nebula.core.aggregation.aggregator import create_aggregator
from nebula.core.eventmanager import EventManager
from nebula.core.network.communications import CommunicationsManager
from nebula.core.pb import nebula_pb2
from nebula.core.reputation.Reputation import Reputation
from nebula.core.utils.locker import Locker

logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("fsspec").setLevel(logging.WARNING)
logging.getLogger("matplotlib").setLevel(logging.ERROR)
logging.getLogger("plotly").setLevel(logging.ERROR)

import pdb
import sys

from nebula.config.config import Config
from nebula.core.training.lightning import Lightning


def handle_exception(exc_type, exc_value, exc_traceback):
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    pdb.set_trace()
    pdb.post_mortem(exc_traceback)


def signal_handler(sig, frame):
    print("Signal handler called with signal", sig)
    print("Exiting gracefully")
    sys.exit(0)


def print_banner():
    banner = """
                    ███╗   ██╗███████╗██████╗ ██╗   ██╗██╗      █████╗
                    ████╗  ██║██╔════╝██╔══██╗██║   ██║██║     ██╔══██╗
                    ██╔██╗ ██║█████╗  ██████╔╝██║   ██║██║     ███████║
                    ██║╚██╗██║██╔══╝  ██╔══██╗██║   ██║██║     ██╔══██║
                    ██║ ╚████║███████╗██████╔╝╚██████╔╝███████╗██║  ██║
                    ╚═╝  ╚═══╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝
                      A Platform for Decentralized Federated Learning
                        Created by Enrique Tomás Martínez Beltrán
                          https://github.com/CyberDataLab/nebula
                """
    logging.info(f"\n{banner}\n")


class Engine:
    def __init__(
        self,
        model,
        datamodule,
        config=Config,
        trainer=Lightning,
        security=False,
    ):
        self.config = config
        self.idx = config.participant["device_args"]["idx"]
        self.experiment_name = config.participant["scenario_args"]["name"]
        self.ip = config.participant["network_args"]["ip"]
        self.port = config.participant["network_args"]["port"]
        self.addr = config.participant["network_args"]["addr"]
        self.role = config.participant["device_args"]["role"]
        self.name = config.participant["device_args"]["name"]
        self.docker_id = config.participant["device_args"]["docker_id"]
        self.client = docker.from_env()

        print_banner()

        print_msg_box(
            msg=f"Name {self.name}\nRole: {self.role}",
            indent=2,
            title="Node information",
        )

        self._trainer = None
        self._aggregator = None
        self.round = None
        self.total_rounds = None
        self.federation_nodes = set()
        self.initialized = False
        self.log_dir = os.path.join(config.participant["tracking_args"]["log_dir"], self.experiment_name)

        self.security = security

        self._trainer = trainer(model, datamodule, config=self.config)
        self._aggregator = create_aggregator(config=self.config, engine=self)

        self._secure_neighbors = []
        self._is_malicious = True if self.config.participant["adversarial_args"]["attacks"] != "No Attack" else False

        msg = f"Trainer: {self._trainer.__class__.__name__}"
        msg += f"\nDataset: {self.config.participant['data_args']['dataset']}"
        msg += f"\nIID: {self.config.participant['data_args']['iid']}"
        msg += f"\nModel: {model.__class__.__name__}"
        msg += f"\nAggregation algorithm: {self._aggregator.__class__.__name__}"
        msg += f"\nNode behavior: {'malicious' if self._is_malicious else 'benign'}"
        print_msg_box(msg=msg, indent=2, title="Scenario information")
        print_msg_box(
            msg=f"Logging type: {self._trainer.logger.__class__.__name__}",
            indent=2,
            title="Logging information",
        )

        self.learning_cycle_lock = Locker(name="learning_cycle_lock", async_lock=True)
        self.federation_setup_lock = Locker(name="federation_setup_lock", async_lock=True)
        self.federation_ready_lock = Locker(name="federation_ready_lock", async_lock=True)
        self.round_lock = Locker(name="round_lock", async_lock=True)

        self.config.reload_config_file()

        self._cm = CommunicationsManager(engine=self)
        # Set the communication manager in the model (send messages from there)
        self.trainer.model.set_communication_manager(self._cm)

        self._reporter = Reporter(config=self.config, trainer=self.trainer, cm=self.cm)

        self._event_manager = EventManager(
            # default_callbacks=[
            #     self._discovery_discover_callback,
            #     self._control_alive_callback,
            #     self._connection_connect_callback,
            #     self._connection_disconnect_callback,
            #     # self._federation_ready_callback,
            #     # self._start_federation_callback,
            #     # self._federation_models_included_callback,
            # ]
        )

        # # Register additional callbacks
        # self._event_manager.register_callback(
        #     self._reputation_callback,
        #     # ... add more callbacks here
        # )

        # Reputation
        self.reputation_instance = Reputation(self)
        self.reputation = {}
        self.reputation_with_feedback = {}
        self.rejected_nodes = set()
        self.change_weight_nodes = set()

        self.with_reputation = self.config.participant["defense_args"]["with_reputation"]
        msg = f"Reputation system: {self.with_reputation}"
        print_msg_box(msg=msg, indent=2, title="Defense information")
        # self.is_dynamic_topology = self.config.participant["defense_args"]["is_dynamic_topology"]
        # self.is_dynamic_aggregation = self.config.participant["defense_args"]["is_dynamic_aggregation"]
        # self.target_aggregation = (
        #     create_target_aggregator(config=self.config, engine=self) if self.is_dynamic_aggregation else None
        # )
        # msg = f"Reputation system: {self.with_reputation}\nDynamic topology: {self.is_dynamic_topology}\nDynamic aggregation: {self.is_dynamic_aggregation}"
        # msg += (
        #     f"\nTarget aggregation: {self.target_aggregation.__class__.__name__}" if self.is_dynamic_aggregation else ""
        # )
        # print_msg_box(msg=msg, indent=2, title="Defense information")

        # if self.with_reputation:
        #     logging.info("Reputation system enabled")
        #     federation = self.config.participant["network_args"]["neighbors"].split()
        #     self.reputation_instance.init_reputation(federation_nodes=federation)
        self.register_message_events_callbacks()

    @property
    def cm(self):
        return self._cm

    @property
    def reporter(self):
        return self._reporter

    @property
    def event_manager(self):
        return self._event_manager

    @property
    def aggregator(self):
        return self._aggregator

    def get_aggregator_type(self):
        return type(self.aggregator)

    @property
    def trainer(self):
        return self._trainer

    def get_addr(self):
        return self.addr

    def get_config(self):
        return self.config

    def get_federation_nodes(self):
        return self.federation_nodes

    def get_initialization_status(self):
        return self.initialized

    def set_initialization_status(self, status):
        self.initialized = status

    def get_round(self):
        return self.round

    def get_federation_ready_lock(self):
        return self.federation_ready_lock

    def get_federation_setup_lock(self):
        return self.federation_setup_lock

    def get_round_lock(self):
        return self.round_lock

    def get_reputation(self):
        return self.reputation

    @event_handler(nebula_pb2.DiscoveryMessage, nebula_pb2.DiscoveryMessage.Action.DISCOVER)
    def register_message_events_callbacks(self):
        me_dict = self.cm.get_messages_events()
        message_events = [
            (message_name, message_action)
            for (message_name, message_actions) in me_dict.items()
            for message_action in message_actions
        ]
        logging.info(f"{message_events}")
        for event_type, action in message_events:
            callback_name = f"_{event_type}_{action}_callback"
            logging.info(f"Searching callback named: {callback_name}")
            method = getattr(self, callback_name, None)

            if callable(method):
                self.event_manager.subscribe((event_type, action), method)

    async def trigger_event(self, message_event):
        logging.info(f"Publishing MessageEvent: {message_event.message_type}")
        await self.event_manager.publish(message_event)

    async def _discovery_discover_callback(self, source, message):
        logging.info(
            f"🔍  handle_discovery_message | Trigger | Received discovery message from {source} (network propagation)"
        )
        current_connections = await self.cm.get_addrs_current_connections(myself=True)
        if source not in current_connections:
            logging.info(f"🔍  handle_discovery_message | Trigger | Connecting to {source} indirectly")
            await self.cm.connect(source, direct=False)
        async with self.cm.get_connections_lock():
            if source in self.cm.connections:
                # Update the latitude and longitude of the node (if already connected)
                if (
                    message.latitude is not None
                    and -90 <= message.latitude <= 90
                    and message.longitude is not None
                    and -180 <= message.longitude <= 180
                ):
                    self.cm.connections[source].update_geolocation(message.latitude, message.longitude)
                else:
                    logging.warning(
                        f"🔍  Invalid geolocation received from {source}: latitude={message.latitude}, longitude={message.longitude}"
                    )

    async def _control_alive_callback(self, source, message):
        logging.info(f"🔧  handle_control_message | Trigger | Received alive message from {source}")
        current_connections = await self.cm.get_addrs_current_connections(myself=True)
        if source in current_connections:
            try:
                await self.cm.health.alive(source)
            except Exception as e:
                logging.exception(f"Error updating alive status in connection: {e}")
        else:
            logging.error(f"❗️  Connection {source} not found in connections...")

    async def _connection_connect_callback(self, source, message):
        logging.info(f"🔗  handle_connection_message | Trigger | Received connection message from {source}")
        current_connections = await self.cm.get_addrs_current_connections(myself=True)
        if source not in current_connections:
            logging.info(f"🔗  handle_connection_message | Trigger | Connecting to {source}")
            await self.cm.connect(source, direct=True)

    async def _connection_disconnect_callback(self, source, message):
        logging.info(f"🔗  handle_connection_message | Trigger | Received disconnection message from {source}")
        await self.cm.disconnect(source, mutual_disconnection=False)

    async def _federation_federation_ready_callback(self, source, message):
        logging.info(f"📝  handle_federation_message | Trigger | Received ready federation message from {source}")
        if self.config.participant["device_args"]["start"]:
            logging.info(f"📝  handle_federation_message | Trigger | Adding ready connection {source}")
            await self.cm.add_ready_connection(source)

    async def _federation_federation_start_callback(self, source, message):
        logging.info(f"📝  handle_federation_message | Trigger | Received start federation message from {source}")
        await self.create_trainer_module()

    # @event_handler(nebula_pb2.FederationMessage, nebula_pb2.FederationMessage.Action.REPUTATION)
    # async def _reputation_callback(self, source, message):
    #     malicious_nodes = message.arguments  # List of malicious nodes
    #     if self.with_reputation:
    #         if len(malicious_nodes) > 0 and not self._is_malicious:
    #             if self.is_dynamic_topology:
    #                 await self._disrupt_connection_using_reputation(malicious_nodes)
    #             if self.is_dynamic_aggregation and self.aggregator != self.target_aggregation:
    #                 await self._dynamic_aggregator(
    #                     self.aggregator.get_nodes_pending_models_to_aggregate(),
    #                     malicious_nodes,
    #                 )

    async def _federation_federation_models_included_callback(self, source, message):
        logging.info(f"📝  handle_federation_message | Trigger | Received aggregation finished message from {source}")
        try:
            await self.cm.get_connections_lock().acquire_async()
            if self.round is not None and source in self.cm.connections:
                try:
                    if message is not None and len(message.arguments) > 0:
                        self.cm.connections[source].update_round(int(message.arguments[0])) if message.round in [
                            self.round - 1,
                            self.round,
                        ] else None
                except Exception as e:
                    logging.exception(f"Error updating round in connection: {e}")
            else:
                logging.error(f"Connection not found for {source}")
        except Exception as e:
            logging.exception(f"Error updating round in connection: {e}")
        finally:
            await self.cm.get_connections_lock().release_async()

    async def create_trainer_module(self):
        asyncio.create_task(self._start_learning())
        logging.info("Started trainer module...")

    async def start_communications(self):
        logging.info(f"Neighbors: {self.config.participant['network_args']['neighbors']}")
        logging.info(
            f"💤  Cold start time: {self.config.participant['misc_args']['grace_time_connection']} seconds before connecting to the network"
        )
        await asyncio.sleep(self.config.participant["misc_args"]["grace_time_connection"])
        await self.cm.start()
        initial_neighbors = self.config.participant["network_args"]["neighbors"].split()
        for i in initial_neighbors:
            addr = f"{i.split(':')[0]}:{i.split(':')[1]}"
            await self.cm.connect(addr, direct=True)
            await asyncio.sleep(1)
        while not self.cm.verify_connections(initial_neighbors):
            await asyncio.sleep(1)
        current_connections = await self.cm.get_addrs_current_connections()
        logging.info(f"Connections verified: {current_connections}")
        await self._reporter.start()
        await self.cm.deploy_additional_services()
        await asyncio.sleep(self.config.participant["misc_args"]["grace_time_connection"] // 2)

    async def deploy_federation(self):
        await self.federation_ready_lock.acquire_async()
        if self.config.participant["device_args"]["start"]:
            logging.info(
                f"💤  Waiting for {self.config.participant['misc_args']['grace_time_start_federation']} seconds to start the federation"
            )
            await asyncio.sleep(self.config.participant["misc_args"]["grace_time_start_federation"])
            if self.round is None:
                while not await self.cm.check_federation_ready():
                    await asyncio.sleep(1)
                logging.info("Sending FEDERATION_START to neighbors...")
                # message = self.cm.mm.generate_federation_message(nebula_pb2.FederationMessage.Action.FEDERATION_START)
                message = self.cm.create_message("federation", "federation_start")
                await self.cm.send_message_to_neighbors(message)
                await self.get_federation_ready_lock().release_async()
                await self.create_trainer_module()
            else:
                logging.info("Federation already started")

        else:
            logging.info("Sending FEDERATION_READY to neighbors...")
            # message = self.cm.mm.generate_federation_message(nebula_pb2.FederationMessage.Action.FEDERATION_READY)
            message = self.cm.create_message("federation", "federation_ready")
            await self.cm.send_message_to_neighbors(message)
            logging.info("💤  Waiting until receiving the start signal from the start node")

    async def _start_learning(self):
        await self.learning_cycle_lock.acquire_async()
        try:
            if self.round is None:
                self.total_rounds = self.config.participant["scenario_args"]["rounds"]
                epochs = self.config.participant["training_args"]["epochs"]
                await self.get_round_lock().acquire_async()
                self.round = 0
                await self.get_round_lock().release_async()
                await self.learning_cycle_lock.release_async()
                print_msg_box(
                    msg="Starting Federated Learning process...",
                    indent=2,
                    title="Start of the experiment",
                )
                direct_connections = await self.cm.get_addrs_current_connections(only_direct=True)
                undirected_connections = await self.cm.get_addrs_current_connections(only_undirected=True)
                logging.info(
                    f"Initial DIRECT connections: {direct_connections} | Initial UNDIRECT participants: {undirected_connections}"
                )
                logging.info("💤  Waiting initialization of the federation...")
                # Lock to wait for the federation to be ready (only affects the first round, when the learning starts)
                # Only applies to non-start nodes --> start node does not wait for the federation to be ready
                await self.get_federation_ready_lock().acquire_async()
                if self.config.participant["device_args"]["start"]:
                    logging.info("Propagate initial model updates.")
                    await self.cm.propagator.propagate("initialization")
                    await self.get_federation_ready_lock().release_async()

                self.trainer.set_epochs(epochs)
                self.trainer.create_trainer()

                await self._learning_cycle()
            else:
                if await self.learning_cycle_lock.locked_async():
                    await self.learning_cycle_lock.release_async()
        finally:
            if await self.learning_cycle_lock.locked_async():
                await self.learning_cycle_lock.release_async()

    async def _disrupt_connection_using_reputation(self, malicious_nodes):
        malicious_nodes = list(set(malicious_nodes) & set(self.get_current_connections()))
        logging.info(f"Disrupting connection with malicious nodes at round {self.round}")
        logging.info(f"Removing {malicious_nodes} from {self.get_current_connections()}")
        logging.info(f"Current connections before aggregation at round {self.round}: {self.get_current_connections()}")
        for malicious_node in malicious_nodes:
            if (self.get_name() != malicious_node) and (malicious_node not in self._secure_neighbors):
                await self.cm.disconnect(malicious_node)
        logging.info(f"Current connections after aggregation at round {self.round}: {self.get_current_connections()}")

        await self._connect_with_benign(malicious_nodes)

    async def _connect_with_benign(self, malicious_nodes):
        lower_threshold = 1
        higher_threshold = len(self.federation_nodes) - 1
        if higher_threshold < lower_threshold:
            higher_threshold = lower_threshold

        benign_nodes = [i for i in self.federation_nodes if i not in malicious_nodes]
        logging.info(f"_reputation_callback benign_nodes at round {self.round}: {benign_nodes}")
        if len(self.get_current_connections()) <= lower_threshold:
            for node in benign_nodes:
                if len(self.get_current_connections()) <= higher_threshold and self.get_name() != node:
                    connected = await self.cm.connect(node)
                    if connected:
                        logging.info(f"Connect new connection with at round {self.round}: {connected}")

    async def _dynamic_aggregator(self, aggregated_models_weights, malicious_nodes):
        logging.info(f"malicious detected at round {self.round}, change aggergation protocol!")
        if self.aggregator != self.target_aggregation:
            logging.info(f"Current aggregator is: {self.aggregator}")
            self.aggregator = self.target_aggregation
            await self.aggregator.update_federation_nodes(self.federation_nodes)

            for subnodes in aggregated_models_weights.keys():
                sublist = subnodes.split()
                (submodel, weights) = aggregated_models_weights[subnodes]
                for node in sublist:
                    if node not in malicious_nodes:
                        await self.aggregator.include_model_in_buffer(
                            submodel, weights, source=self.get_name(), round=self.round
                        )
            logging.info(f"Current aggregator is: {self.aggregator}")

    async def _waiting_model_updates(self):
        logging.info(f"💤  Waiting convergence in round {self.round}.")
        params = await self.aggregator.get_aggregation()
        if params is not None:
            logging.info(
                f"_waiting_model_updates | Aggregation done for round {self.round}, including parameters in local model."
            )
            self.trainer.set_model_parameters(params)
            if self.with_reputation:
                await self.calculate_reputation()
        else:
            logging.error("Aggregation finished with no parameters")

    def learning_cycle_finished(self):
        return not (self.round < self.total_rounds)

    async def calculate_reputation(self):
        logging.info(f"rejected nodes at round {self.round}: {self.rejected_nodes}")
        if self.rejected_nodes is not None:
            self.rejected_nodes.clear()
        logging.info(f"rejected nodes after clear at round {self.round}: {self.rejected_nodes}")

        logging.info(f"change weight nodes at round {self.round}: {self.change_weight_nodes}")
        if self.change_weight_nodes is not None:
            self.change_weight_nodes.clear()
        logging.info(f"change weight nodes after clear at round {self.round}: {self.change_weight_nodes}")

        current_round = self.get_round()
        neighbors = set(await self.cm.get_addrs_current_connections(only_direct=True))
        reputation_with_weights = None

        for nei in neighbors:
            metric_messages_time, metric_similarity, metric_fraction, metric_model_arrival_latency = (
                self.reputation_instance.calculate_value_metrics(
                    self.config.participant["scenario_args"]["name"],
                    self.log_dir,
                    self.idx,
                    self.addr,
                    nei,
                    current_round=current_round,
                )
            )

            logging.info(f"metric_messages_time at round {self.round}: {metric_messages_time}")
            logging.info(f"metric_similarity at round {self.round}: {metric_similarity}")
            logging.info(f"metric_fraction at round {self.round}: {metric_fraction}")
            logging.info(f"metric_model_arrival_latency at round {self.round}: {metric_model_arrival_latency}")

            history_data = self.reputation_instance.history_data
            self.reputation_instance.calculate_weighted_values(
                metric_messages_time,
                metric_similarity,
                metric_fraction,
                metric_model_arrival_latency,
                history_data,
                current_round,
                self.addr,
                nei,
            )
            # logging.info(f"history_data after calculate_weighted_values at {self.round}: {history_data}")

        if current_round >= 5:
            average_weights = {}
            for metric_name in history_data.keys():
                valid_entries = [
                    entry
                    for entry in history_data[metric_name]
                    if entry["round"] >= current_round and entry.get("weight") not in [None, -1]
                ]
                # logging.info(f"valid_entries for {metric_name} at round {self.round}: {valid_entries}")

                if valid_entries:
                    average_weight = sum([entry["weight"] for entry in valid_entries]) / len(valid_entries)
                    average_weights[metric_name] = average_weight
                    # logging.info(f"average_weight for {metric_name} at round {self.round}: {average_weight}")
                else:
                    average_weights[metric_name] = 0

            for nei in neighbors:
                metric_messages_time_history = None
                metric_similarity_history = None
                metric_fraction_history = None
                metric_model_arrival_latency_history = None

                for metric_name in history_data.keys():
                    for entry in history_data.get(metric_name, []):
                        if entry["round"] == current_round and entry["nei"] == nei:
                            if metric_name == "messages_time":
                                metric_messages_time_history = entry["metric_value"]
                            elif metric_name == "similarity":
                                metric_similarity_history = entry["metric_value"]
                            elif metric_name == "fraction":
                                metric_fraction_history = entry["metric_value"]
                            elif metric_name == "model_arrival_latency":
                                metric_model_arrival_latency_history = entry["metric_value"]
                            break

                logging.info(f"metric_messages_time_history at round {self.round}: {metric_messages_time_history}")
                logging.info(f"metric_similarity_history at round {self.round}: {metric_similarity_history}")
                logging.info(f"metric_fraction_history at round {self.round}: {metric_fraction_history}")
                logging.info(
                    f"metric_model_arrival_latency_history at round {self.round}: {metric_model_arrival_latency_history}"
                )

                logging.info(f"average_weights at round {self.round}: {average_weights}")

                if (
                    metric_messages_time_history is not None
                    and metric_similarity_history is not None
                    and metric_fraction_history is not None
                    and metric_model_arrival_latency_history is not None
                ):
                    reputation_with_weights = (
                        metric_messages_time_history * average_weights["messages_time"]
                        + metric_similarity_history * average_weights["similarity"]
                        + metric_fraction_history * average_weights["fraction"]
                        + metric_model_arrival_latency_history * average_weights["model_arrival_latency"]
                    )
                    logging.info(f"Reputation with weights: {reputation_with_weights}")

                    metrics_data = {
                        "addr": self.addr.split(":")[0].strip(),
                        "nei": nei.split(":")[0].strip(),
                        "round": self.round,
                        "average_time_messages": average_weights["messages_time"],
                        "average_similarity": average_weights["similarity"],
                        "average_fraction": average_weights["fraction"],
                        "average_model_arrival_latency": average_weights["model_arrival_latency"],
                    }

                    self.reputation_instance.metrics(
                        self.experiment_name,
                        metrics_data,
                        self.addr.split(":")[0].strip(),
                        nei.split(":")[0].strip(),
                        "reputation",
                        update_field="reputation_without_feedback",
                    )
                    # logging.info(f"reputation_with_weights at round {self.round}: {reputation_with_weights}")
                else:
                    reputation_with_weights = None
                    # logging.info(f"reputation_with_weights at round {self.round}: {reputation_with_weights}")

                if reputation_with_weights is not None:
                    avg_reputation = self.reputation_instance.save_reputation_history_in_memory(
                        self.addr, nei, reputation_with_weights, current_round
                    )
                    logging.info(f"Average reputation for node {nei}: {avg_reputation}")
                else:
                    avg_reputation = 0
                    # logging.info(f"Average reputation for node {nei}: {avg_reputation}")

                if nei not in self.reputation:
                    self.reputation[nei] = {
                        "reputation": avg_reputation,
                        "round": current_round,
                        "last_feedback_round": -1,
                    }
                else:
                    self.reputation[nei]["reputation"] = avg_reputation
                    self.reputation[nei]["round"] = current_round

                if self.reputation[nei]["reputation"] is not None:
                    metrics_data = {
                        "addr": self.addr.split(":")[0].strip(),
                        "nei": nei.split(":")[0].strip(),
                        "round": self.round,
                        "reputation_without_feedback": self.reputation[nei]["reputation"],
                    }

                    self.reputation_instance.metrics(
                        self.experiment_name,
                        metrics_data,
                        self.addr.split(":")[0].strip(),
                        nei.split(":")[0].strip(),
                        "reputation",
                        update_field="model_arrival_latency",
                    )

                if self.reputation[nei]["reputation"] is not None:
                    logging.info(f"Reputation of node {nei}: {self.reputation[nei]['reputation']}")
                    if self.reputation[nei]["reputation"] < 0.6:
                        self.rejected_nodes.add(nei)
                        logging.info(f"Rejected nodes: {self.rejected_nodes}")
                    # elif 0.6 < self.reputation[nei]["reputation"] < 0.8:
                    #     logging.info(f"Change weight node: {nei}")
                    #     self.change_weight_nodes.add(nei)
        else:
            # logging.info(f"No weights calculated at round {self.round}")
            if self.with_reputation:
                # logging.info("Reputation system enabled")
                federation = self.config.participant["network_args"]["neighbors"].split()
                self.reputation_instance.init_reputation(
                    self.addr,
                    federation_nodes=federation,
                    round_num=current_round,
                    last_feedback_round=-1,
                    scenario=self.experiment_name,
                )

        status = await self.include_feedback_in_reputation()
        if status:
            logging.info(f"Feedback included in reputation at round {self.round}")
        else:
            logging.info(f"Feedback not included in reputation at round {self.round}")

        if self.reputation is not None:
            reputation_dict_with_values = {
                f"Reputation/{self.addr}": {
                    node_id: float(data["reputation"])
                    for node_id, data in self.reputation.items()
                    if data["reputation"] is not None
                }
            }

            logging.info(f"Reputation dict: {reputation_dict_with_values}")
            self.trainer._logger.log_data(reputation_dict_with_values, step=self.round)

            for nei, data in self.reputation.items():
                if nei not in self.reputation[nei]:
                    if data["reputation"] is not None:
                        neighbors_to_send = [neighbor for neighbor in neighbors if neighbor != nei]

                        message_data = self.cm.mm.generate_reputation_message(
                            node_id=nei,
                            score=data["reputation"],
                            round=data["round"],
                        )

                        metrics_data = {
                            "addr": self.addr.split(":")[0].strip(),
                            "nei": nei.split(":")[0].strip(),
                            "round": self.round,
                            "reputation_with_feedback": data["reputation"],
                        }

                        self.reputation_instance.metrics(
                            self.experiment_name,
                            metrics_data,
                            self.addr.split(":")[0].strip(),
                            nei.split(":")[0].strip(),
                            "reputation",
                            update_field="reputation_with_feedback",
                        )

                        for neighbor in neighbors_to_send:
                            logging.info(
                                f"Sending reputation to node {nei} from node {neighbor} with reputation {data['reputation']}"
                            )
                            # self.cm.store_send_timestamp(nei, current_round, "reputation")
                            await self.cm.send_message_to_neighbors(message_data, [neighbor])
                else:
                    logging.info(f"Reputation already sent to node {nei}")

    async def include_feedback_in_reputation(self):
        data = None
        weight_current_reputation = 0.9
        weight_feedback = 0.1

        if self._cm.reputation_with_all_feedback is not None:
            current_round = self.get_round()
            for (current_node, node_ip, round_num), scores in self._cm.reputation_with_all_feedback.items():
                if node_ip in self.reputation and "last_feedback_round" in self.reputation[node_ip]:
                    if self.reputation[node_ip]["last_feedback_round"] >= round_num:
                        continue

                logging.info(
                    f"current_node: {current_node} | node_ip: {node_ip} | round_num: {round_num} | scores: {scores}"
                )

                if scores:
                    avg_feedback = sum(scores) / len(scores)
                    logging.info(f"Receive feedback to node {node_ip} with average score {avg_feedback}")

                    logging.info(f"self.reputation: {self.reputation}")
                    if node_ip in self.reputation:
                        current_reputation = self.reputation[node_ip]["reputation"]
                        logging.info(f"Current reputation for node {node_ip}: {current_reputation}")
                    else:
                        logging.info(f"No node {node_ip} in reputation history.")
                        return False

                    if current_reputation:
                        combined_reputation = (current_reputation * weight_current_reputation) + (
                            avg_feedback * weight_feedback
                        )
                        logging.info(
                            f"Combined reputation for node {node_ip} in round {round_num}: {combined_reputation}"
                        )
                    else:
                        combined_reputation = current_reputation
                        logging.info(f"No reputation calculate for node {node_ip}.")

                    self.reputation[node_ip] = {
                        "reputation": combined_reputation,
                        "round": current_round,
                        "last_feedback_round": round_num,
                    }

                    logging.info(f"Updated self.reputation for {node_ip}: {self.reputation[node_ip]}")

            return True
        else:
            return False, None

    async def _learning_cycle(self):
        while self.round is not None and self.round < self.total_rounds:
            print_msg_box(
                msg=f"Round {self.round} of {self.total_rounds} started.",
                indent=2,
                title="Round information",
            )
            self.trainer.on_round_start()
            self.federation_nodes = await self.cm.get_addrs_current_connections(only_direct=True, myself=True)
            logging.info(f"Federation nodes: {self.federation_nodes}")
            direct_connections = await self.cm.get_addrs_current_connections(only_direct=True)
            undirected_connections = await self.cm.get_addrs_current_connections(only_undirected=True)
            logging.info(f"Direct connections: {direct_connections} | Undirected connections: {undirected_connections}")
            logging.info(f"[Role {self.role}] Starting learning cycle...")
            await self.aggregator.update_federation_nodes(self.federation_nodes)
            await self._extended_learning_cycle()

            # await self.calculate_reputation()

            await self.get_round_lock().acquire_async()
            print_msg_box(
                msg=f"Round {self.round} of {self.total_rounds} finished.",
                indent=2,
                title="Round information",
            )
            await self.aggregator.reset()
            self.trainer.on_round_end()
            self.round = self.round + 1
            self.config.participant["federation_args"]["round"] = (
                self.round
            )  # Set current round in config (send to the controller)
            await self.get_round_lock().release_async()

        # End of the learning cycle
        self.trainer.on_learning_cycle_end()
        await self.trainer.test()
        print_msg_box(
            msg="Federated Learning process has been completed.",
            indent=2,
            title="End of the experiment",
        )
        # Report
        if self.config.participant["scenario_args"]["controller"] != "nebula-test":
            result = await self.reporter.report_scenario_finished()
            if result:
                pass
            else:
                logging.error("Error reporting scenario finished")

        logging.info("Checking if all my connections reached the total rounds...")
        while not self.cm.check_finished_experiment():
            await asyncio.sleep(1)

        await asyncio.sleep(5)

        # Kill itself
        if self.config.participant["scenario_args"]["deployment"] == "docker":
            try:
                self.client.containers.get(self.docker_id).stop()
            except Exception as e:
                print(f"Error stopping Docker container with ID {self.docker_id}: {e}")

    async def _extended_learning_cycle(self):
        """
        This method is called in each round of the learning cycle. It is used to extend the learning cycle with additional
        functionalities. The method is called in the _learning_cycle method.
        """
        pass

    # def reputation_calculation(self, aggregated_models_weights):
    #     cossim_threshold = 0.5
    #     loss_threshold = 0.5

    #     current_models = {}
    #     for subnodes in aggregated_models_weights.keys():
    #         sublist = subnodes.split()
    #         submodel = aggregated_models_weights[subnodes][0]
    #         for node in sublist:
    #             current_models[node] = submodel

    #     malicious_nodes = []
    #     reputation_score = {}
    #     local_model = self.trainer.get_model_parameters()
    #     untrusted_nodes = list(current_models.keys())
    #     logging.info(f"reputation_calculation untrusted_nodes at round {self.round}: {untrusted_nodes}")

    #     for untrusted_node in untrusted_nodes:
    #         logging.info(f"reputation_calculation untrusted_node at round {self.round}: {untrusted_node}")
    #         logging.info(f"reputation_calculation self.get_name() at round {self.round}: {self.get_name()}")
    #         if untrusted_node != self.get_name():
    #             untrusted_model = current_models[untrusted_node]
    #             cossim = cosine_metric(local_model, untrusted_model, similarity=True)
    #             logging.info(f"reputation_calculation cossim at round {self.round}: {untrusted_node}: {cossim}")
    #             self.trainer._logger.log_data({f"Reputation/cossim_{untrusted_node}": cossim}, step=self.round)

    #             avg_loss = self.trainer.validate_neighbour_model(untrusted_model)
    #             logging.info(f"reputation_calculation avg_loss at round {self.round} {untrusted_node}: {avg_loss}")
    #             self.trainer._logger.log_data({f"Reputation/avg_loss_{untrusted_node}": avg_loss}, step=self.round)
    #             reputation_score[untrusted_node] = (cossim, avg_loss)

    #             if cossim < cossim_threshold or avg_loss > loss_threshold:
    #                 malicious_nodes.append(untrusted_node)
    #             else:
    #                 self._secure_neighbors.append(untrusted_node)

    #     return malicious_nodes, reputation_score

    # async def send_reputation(self, malicious_nodes):
    # logging.info(f"Sending REPUTATION to the rest of the topology: {malicious_nodes}")
    # message = self.cm.mm.generate_federation_message(
    #     nebula_pb2.FederationMessage.Action.REPUTATION, malicious_nodes
    # )
    # await self.cm.send_message_to_neighbors(message)


class MaliciousNode(Engine):
    def __init__(
        self,
        model,
        datamodule,
        config=Config,
        trainer=Lightning,
        security=False,
    ):
        super().__init__(
            model,
            datamodule,
            config,
            trainer,
            security,
        )
        self.attack = create_attack(self)
        self.aggregator_bening = self._aggregator

    async def _extended_learning_cycle(self):
        try:
            if self.with_reputation:
                self.with_reputation = False
            logging.info(f"Reputation: {self.with_reputation}")
            await self.attack.attack()
        except:
            attack_name = self.config.participant["adversarial_args"]["attacks"]
            logging.exception(f"Attack {attack_name} failed")

        if self.role == "aggregator":
            await AggregatorNode._extended_learning_cycle(self)
        if self.role == "trainer":
            await TrainerNode._extended_learning_cycle(self)
        if self.role == "server":
            await ServerNode._extended_learning_cycle(self)


class AggregatorNode(Engine):
    def __init__(
        self,
        model,
        datamodule,
        config=Config,
        trainer=Lightning,
        security=False,
    ):
        super().__init__(
            model,
            datamodule,
            config,
            trainer,
            security,
        )

    async def _extended_learning_cycle(self):
        # Define the functionality of the aggregator node
        await self.trainer.test()
        await self.trainer.train()

        await self.aggregator.include_model_in_buffer(
            self.trainer.get_model_parameters(),
            self.trainer.get_model_weight(),
            source=self.addr,
            round=self.round,
        )

        await self.cm.propagator.propagate("stable")
        await self._waiting_model_updates()


class ServerNode(Engine):
    def __init__(
        self,
        model,
        datamodule,
        config=Config,
        trainer=Lightning,
        security=False,
    ):
        super().__init__(
            model,
            datamodule,
            config,
            trainer,
            security,
        )

    async def _extended_learning_cycle(self):
        # Define the functionality of the server node
        await self.trainer.test()

        # In the first round, the server node doest take into account the initial model parameters for the aggregation
        await self.aggregator.include_model_in_buffer(
            self.trainer.get_model_parameters(),
            self.trainer.BYPASS_MODEL_WEIGHT,
            source=self.addr,
            round=self.round,
        )
        await self._waiting_model_updates()
        await self.cm.propagator.propagate("stable")


class TrainerNode(Engine):
    def __init__(
        self,
        model,
        datamodule,
        config=Config,
        trainer=Lightning,
        security=False,
    ):
        super().__init__(
            model,
            datamodule,
            config,
            trainer,
            security,
        )

    async def _extended_learning_cycle(self):
        # Define the functionality of the trainer node
        logging.info("Waiting global update | Assign _waiting_global_update = True")
        self.aggregator.set_waiting_global_update()

        await self.trainer.test()
        await self.trainer.train()

        await self.aggregator.include_model_in_buffer(
            self.trainer.get_model_parameters(),
            self.trainer.get_model_weight(),
            source=self.addr,
            round=self.round,
            local=True,
        )

        await self.cm.propagator.propagate("stable")
        await self._waiting_model_updates()


class IdleNode(Engine):
    def __init__(
        self,
        model,
        datamodule,
        config=Config,
        trainer=Lightning,
        security=False,
    ):
        super().__init__(
            model,
            datamodule,
            config,
            trainer,
            security,
        )

    async def _extended_learning_cycle(self):
        # Define the functionality of the idle node
        logging.info("Waiting global update | Assign _waiting_global_update = True")
        self.aggregator.set_waiting_global_update()
        await self._waiting_model_updates()
