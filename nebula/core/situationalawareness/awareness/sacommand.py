from abc import abstractmethod
from enum import Enum
import asyncio
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.situationalawareness.awareness.samoduleagent import SAModuleAgent

class SACommandType(Enum):
    CONNECTIVITY = "Connectivity"
    AGGREGATION = "Aggregation"

#TODO separar por tipos de commands
class SACommandAction(Enum):
    DISCONNECT = "disconnect"
    RECONNECT = "reconnect"
    SEARCH_CONNECTIONS = "search_connections"
    MAINTAIN_CONNECTIONS = "maintain_connections"
    ADJUST_WEIGHT = "adjust_weight"
    DISCARD_UPDATE = "discard_update"

class SACommandPRIO(Enum):
    HIGH = 10
    MEDIUM = 5
    LOW = 1

class SACommandState(Enum):
    PENDING = "pending"
    DISCARDED = "discarded"
    EXECUTED = "executed"

    """                                             ###############################
                                                    #      SA COMMAND CLASS       #
                                                    ###############################
    """
#TODO añadir estados ene xecute
class SACommand:
    """Base class for Situational Awareness module commands."""
    def __init__(
        self, 
        command_type: SACommandType, 
        action: SACommandAction,
        owner: "SAModuleAgent",  
        target, 
        priority: SACommandPRIO = SACommandPRIO.MEDIUM,
        parallelizable = False
    ):
        self._command_type = command_type
        self._action = action
        self._owner = owner
        self._target = target  # Could be a node, parameter, etc.
        self._priority = priority
        self._parallelizable = parallelizable
        self._state = SACommandState.PENDING

    @abstractmethod
    async def execute(self):
        raise NotImplementedError
    
    @abstractmethod
    async def conflicts_with(self, other: "SACommand") -> bool:
        raise NotImplementedError
    
    def get_owner(self):
        return self._owner.get_agent()
    
    def update_command_state(self, sacs : SACommandState):
        self._state = sacs
    
    def is_parallelizable(self):
        return self._parallelizable

    def __repr__(self):
        return (f"{self.__class__.__name__}(Type={self._command_type.value}, "
                f"Action={self._action.value}, Target={self._target}, Priority={self._priority.value})")
    
    """                                             ###############################
                                                    #     SA COMMAND SUBCLASS     #
                                                    ###############################
    """
class ConnectivityCommand(SACommand):
    """Commands related to connectivity."""
    def __init__(
        self, 
        action: SACommandAction, 
        target: str, 
        priority: SACommandPRIO = SACommandPRIO.MEDIUM,
        parallelizable = False,
        action_function = None,
        *args
    ):
        super().__init__(SACommandType.CONNECTIVITY, action, target, priority, parallelizable)
        self._action_function = action_function
        self._args = args

    async def execute(self):
        """Executes the assigned action function with the given parameters."""
        if self._action_function:
            if asyncio.iscoroutinefunction(self._action_function):
                await self._action_function(*self._args)  
            else:
                self._action_function(*self._args)

    def conflicts_with(self, other: "ConnectivityCommand") -> bool:
        """Determines if two commands conflict with each other."""
        if self._target == other._target:
            conflict_pairs = [
                {SACommandAction.DISCONNECT, SACommandAction.RECONNECT},
                {SACommandAction.DISCONNECT, SACommandAction.MAINTAIN_CONNECTIONS}
            ]
            return {self._action, other._action} in conflict_pairs
        return False 

class AggregationCommand(SACommand):
    """Commands related to data aggregation."""
    def __init__(
        self, 
        action: SACommandAction, 
        target: dict, 
        priority: SACommandPRIO = SACommandPRIO.MEDIUM,
        parallelizable = False,
    ):
        super().__init__(SACommandType.CONNECTIVITY, action, target, priority, parallelizable)

    async def execute(self):
        return self._target
    
    def conflicts_with(self, other: "AggregationCommand") -> bool:
        """Determines if two commands conflict with each other."""
        topologic_conflict = False
        weight_conflict = False

        if set(self._target.keys()) != set(other._target.keys()):
            topologic_conflict = True

        weight_conflict = any(
            abs(self._target[node][1] - other._target[node][1]) > 0
            for node in self._target.keys() if node in other._target.keys()
        )

        return weight_conflict and topologic_conflict

    """                                             ###############################
                                                    #     SA COMMAND FACTORY      #
                                                    ###############################
    """

def factory_sa_command(sacommand_type, *config) -> SACommand:
    options = {
        "connectivity": ConnectivityCommand,
        "aggregation": AggregationCommand,
    } 
    
    cs = options.get(sacommand_type, None)
    return cs(*config)


