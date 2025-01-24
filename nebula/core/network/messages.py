import logging
from typing import TYPE_CHECKING

from nebula.core.pb import nebula_pb2
from nebula.core.network.actions import factory_message_action
import inspect

if TYPE_CHECKING:
    from nebula.core.network.communications import CommunicationsManager


class MessagesManager:
    def __init__(self, addr, config, cm: "CommunicationsManager"):
        self.addr = addr
        self.config = config
        self.cm = cm

    def generate_discovery_message(self, action, latitude=0.0, longitude=0.0):
        message = nebula_pb2.DiscoveryMessage(
            action=action,
            latitude=latitude,
            longitude=longitude,
        )
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.discovery_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data

    def generate_control_message(self, action, log="Control message"):
        message = nebula_pb2.ControlMessage(
            action=action,
            log=log,
        )
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.control_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data

    def generate_federation_message(self, action, arguments=[], round=None):
        logging.info(f"Building federation message with [Action {action}], arguments {arguments}, and round {round}")

        message = nebula_pb2.FederationMessage(
            action=action,
            arguments=[str(arg) for arg in (arguments or [])],
            round=round,
        )
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.federation_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data

    def generate_model_message(self, round, serialized_model, weight=1):
        message = nebula_pb2.ModelMessage(
            round=round,
            parameters=serialized_model,
            weight=weight,
        )
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.model_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data

    def generate_connection_message(self, action):
        message = nebula_pb2.ConnectionMessage(
            action=action,
        )
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.connection_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data

    def generate_reputation_message(self, reputation):
        message = nebula_pb2.ReputationMessage(
            reputation=reputation,
        )
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.reputation_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data
    
    def generate_discover_message(self, action):
        message = nebula_pb2.DiscoverMessage(
            action=action,
        )
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.discover_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data


    def generate_offer_message(self, action, n_neighbors, loss, serialized_model=None, rounds=1, round=-1, epochs = 1):
        message = nebula_pb2.OfferMessage(
            action=action,
            n_neighbors = n_neighbors,
            loss = loss,
            parameters = serialized_model,
            rounds = rounds,
            round = round,
            epochs = epochs
        )
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.offer_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data


    def generate_link_message(self, action, addrs):
        message = nebula_pb2.LinkMessage(
            action=action,
            addrs = addrs,
        )
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.link_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data
    

    def create_message(self, message_type: str, action: str = "", **kwargs):
        message_action = None
        if action:
            message_action = factory_message_action(message_type, action)

        message_generators_map = {
            "model": self.generate_model_message,
            "reputation": self.generate_reputation_message,
            "connection": self.generate_connection_message,
            "federation": self.generate_federation_message,
            "discovery": self.generate_discovery_message,
            "control": self.generate_control_message,
            "discover": self.generate_discover_message,
            "offer": self.generate_offer_message,
            "link": self.generate_link_message,
        }
        message_generator_function = message_generators_map.get(message_type)
        if not message_generator_function:
            raise ValueError(f"Invalid message type '{message_type}'")
        
        generator_signature = inspect.signature(message_generator_function)
        generator_params = generator_signature.parameters

        generator_args = []
        generator_kwargs = {}

        if "action" in generator_params and message_action is not None:
            generator_args.append(message_action)

        if "kwargs" in generator_params:
            generator_kwargs.update(kwargs)

        if generator_kwargs:  
            message = message_generator_function(*generator_args, **generator_kwargs)
        else:
            message = message_generator_function(*generator_args)

        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        field_name = f"{message_type}_message"
        getattr(message_wrapper, field_name).CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data
