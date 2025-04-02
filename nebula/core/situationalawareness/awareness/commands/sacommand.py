from nebula.core.utils.locker import Locker
from abc import ABC, abstractmethod
from enum import Enum

# -----------------------------------------------
# ENUMS for types of SACommands
# -----------------------------------------------
class SACommandType(Enum):
    CONNECTIVITY = "Connectivity"
    AGGREGATION = "Aggregation"

# -----------------------------------------------
# ENUM for available actions
# -----------------------------------------------
class SACommandAction(Enum):
    DISCONNECT = "disconnect"
    RECONNECT = "reconnect"
    SEARCH_CONNECTIONS = "search_connections"
    ADJUST_WEIGHT = "adjust_weight"
    DISCARD_UPDATE = "discard_update"

class SACOmmandPRIO(Enum):
    HIGH = 10
    MEDIUM = 5
    LOW = 1

    """                                             ###############################
                                                    #      SA COMMAND CLASS       #
                                                    ###############################
    """

class SACommand:
    """Base class for Situational Awareness module commands."""
    def __init__(
        self, 
        command_type: SACommandType, 
        action: SACommandAction, 
        target: str, 
        priority: SACOmmandPRIO = SACOmmandPRIO.MEDIUM,
        paralelelizable = False
    ):
        self._command_type = command_type
        self._action = action
        self._target = target  # Could be a node, parameter, etc.
        self._priority = priority
        self._parallelizable = paralelelizable

    @abstractmethod
    async def execute(self):
        raise NotImplementedError
    
    def is_parallelizable(self):
        return self._parallelizable

    def conflicts_with(self, other: "SACommand") -> bool:
        """Determines if two commands conflict with each other."""
        if self._target == other._target:
            conflict_pairs = [
                {SACommandAction.DISCONNECT, SACommandAction.RECONNECT},
                {SACommandAction.ADJUST_WEIGHT, SACommandAction.DISCARD_UPDATE}
            ]
            return {self._action, other._action} in conflict_pairs
        return False

    def __repr__(self):
        return (f"{self.__class__.__name__}(Type={self._command_type.value}, "
                f"Action={self._action.value}, Target={self._target}, Priority={self._priority})")
    
    
def factory_sa_command(sacommand_type, *config) -> SACommand:
    from nebula.core.situationalawareness.awareness.commands.connectivitycommand import ConnectivityCommand

    options = {
        "connectivity": ConnectivityCommand,
    } 
    
    cs = options.get(sacommand_type, None)
    return cs(*config)
