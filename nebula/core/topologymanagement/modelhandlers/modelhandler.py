from abc import ABC, abstractmethod
from typing import Type

class ModelHandler(ABC):
    
    @abstractmethod 
    def set_config(self, config):
        pass
    
    @abstractmethod 
    def accept_model(self, model):
        pass
    
    @abstractmethod 
    async def get_model(self, model):
        pass

    @abstractmethod
    def pre_process_model(self):
        pass
    
def factory_ModelHandler(model_handler) -> ModelHandler:
    from nebula.core.topologymanagement.modelhandlers.stdmodelhandler import STDModelHandler
    from nebula.core.topologymanagement.modelhandlers.aggmodelhandler import AGGModelHandler
    from nebula.core.topologymanagement.modelhandlers.defaultmodelhandler import DefaultModelHandler
    
    options = {
        "std": STDModelHandler,
        "default": DefaultModelHandler,
        "aggregator": AGGModelHandler,
    } 
    
    cs = options.get(model_handler, STDModelHandler)
    return cs() 