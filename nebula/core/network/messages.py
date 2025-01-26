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
                "parameters": ["round", "parameters", "weight"],
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

    def create_message(self, message_type: str, action: str = "", *args, **kwargs):
        #logging.info(f"Creating message | type: {message_type}, action: {action}, positionals: {args}, explicits: {kwargs.keys()}")
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
        logging.info(f"kwargs parameters: {kwargs.keys()}")
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
