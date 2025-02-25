import asyncio
import logging
from nebula.core.utils.locker import Locker
from nebula.addons.functions import print_msg_box
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.situationalawareness.awareness.samodule import SAModule
    
RESTRUCTURE_COOLDOWN = 5    
    
class SATraining():
    def __init__(
        self,
        sam: "SAModule",
        training_policy,
        weight_strategies
    ):
        print_msg_box(
            msg=f"Starting Training SA\nTraining policy: {training_policy}\nWeight strategies: {weight_strategies}",
            indent=2,
            title="Training SA module",
        )
        self._sam = sam
        self._trainning_policy = training_policy
        self._weight_strategies = weight_strategies