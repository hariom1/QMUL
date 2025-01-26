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
        self._message_templates = {}
        self._define_message_templates() 

    def _define_message_templates(self):
        # Dictionary that maps message types to their required parameters and default values
         self._message_templates = {
            "offer": {
                "parameters": ["action", "n_neighbors", "loss", "parameters", "rounds", "round", "epochs"],
                "defaults": {
                    "parameters": None,
                    "rounds": 1,
                    "round": -1,
                    "epochs": 1,
                }
            },
            "connection": {
                "parameters": ["action"],
                "defaults": {}
            },
            "discovery": {
                "parameters": ["action", "latitude", "longitude"],
                "defaults": {
                    "latitude": 0.0,
                    "longitude": 0.0,
                }
            },
            "control": {
                "parameters": ["action", "log"],
                "defaults": {
                    "log": "Control message",
                }
            },
            "federation": {
                "parameters": ["action", "arguments", "round"],
                "defaults": {
                    "arguments": [],
                    "round": None,
                }
            },
            "model": {
                "parameters": ["action", "round", "parameters", "weight"],
                "defaults": {
                    "weight": 1,
                }
            },
            "reputation": {
                "parameters": ["reputation"],
                "defaults": {}
            },
            "discover": {
                "parameters": ["action"],
                "defaults": {}
            },
            "link": {
                "parameters": ["action", "addrs"],
                "defaults": {}
            },
            # Add additional message types here
        }


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

    def generate_model_message(self, round, parameters, weight=1):
        message = nebula_pb2.ModelMessage(
            round=round,
            parameters=parameters,
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
        return message
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.discover_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data

    def generate_offer_message(self, action, n_neighbors, loss, parameters=None, rounds=1, round=-1, epochs = 1):
        message = nebula_pb2.OfferMessage(
            action=action,
            n_neighbors = n_neighbors,
            loss = loss,
            parameters = parameters,
            rounds = rounds,
            round = round,
            epochs = epochs
        )
        return message
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.offer_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data

    def generate_link_message(self, action, addrs):
        pass
        message = nebula_pb2.LinkMessage(
            action=action,
            addrs = addrs,
        )
        return message
        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        message_wrapper.link_message.CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data
    

    def create_message(self, message_type: str, action: str = "", *args, **kwargs):
        # If an action is provided, convert it to its corresponding enum value using the factory
        message_action = None
        if action:
            message_action = factory_message_action(message_type, action)
              
        # Retrieve the template for the provided message type
        message_template = self._message_templates.get(message_type)
        if not message_template:
            raise ValueError(f"Invalid message type '{message_type}'")
        
        # Extract parameters and defaults from the template
        template_params = message_template["parameters"]
        default_values: dict = message_template.get("defaults", {})
        
        # Dynamically retrieve the class for the protobuf message (e.g., OfferMessage)
        class_name =  message_type.capitalize() + "Message"
        message_class = getattr(nebula_pb2, class_name, None)
    
        if message_class is None:
            raise AttributeError(f"Message type {message_type} not found on the protocol")
            
        # Set the 'action' parameter if required and if the message_action is available
        if "action" in template_params and message_action is not None:
            kwargs["action"] = message_action
    
        # Map positional arguments to template parameters
        remaining_params = [param_name for param_name in template_params if param_name not in kwargs] 
        if args:
            for param_name, arg_value in zip(remaining_params, args):
                if param_name in kwargs:
                    continue 
                kwargs[param_name] = arg_value
        
        # Fill in missing parameters with their default values
        # logging.info(f"kwargs parameters: {kwargs.keys()}")
        for param_name in template_params:
            if param_name not in kwargs:
                logging.info(f"Filling parameter '{param_name}' with default value: {default_values.get(param_name)}")
                kwargs[param_name] = default_values.get(param_name)
        
        # Create an instance of the protobuf message class using the constructed kwargs   
        message = message_class(**kwargs)

        message_wrapper = nebula_pb2.Wrapper()
        message_wrapper.source = self.addr
        field_name = f"{message_type}_message"
        getattr(message_wrapper, field_name).CopyFrom(message)
        data = message_wrapper.SerializeToString()
        return data
