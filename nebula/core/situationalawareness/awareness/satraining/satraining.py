import asyncio
import logging
from nebula.core.utils.locker import Locker
from nebula.core.situationalawareness.awareness.satraining.trainingpolicy.trainingpolicy import factory_training_policy
from nebula.addons.functions import print_msg_box
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.situationalawareness.awareness.samodule import SAModule
    from nebula.core.eventmanager import EventManager
    
RESTRUCTURE_COOLDOWN = 5    
    
class SATraining():
    def __init__(
        self,
        sam: "SAModule",
        addr,
        training_policy,
        weight_strategies
    ):
        print_msg_box(
            msg=f"Starting Training SA\nTraining policy: {training_policy}\nWeight strategies: {weight_strategies}",
            indent=2,
            title="Training SA module",
        )
        self._sam = sam
        config = {}
        config["addr"] = addr
        self._trainning_policy = factory_training_policy(training_policy, config)
        self._weight_strategies = weight_strategies

    @property
    def tp(self):
        return self._trainning_policy    

    async def init(self):
        config = {}
        config["nodes"] = set(self._sam.get_nodes_known(neighbors_only=True))
        await self.tp.init(config)

    async def module_actions(self):
        logging.info("SA Trainng evaluating current scenario")
        await self.tp.evaluate()
