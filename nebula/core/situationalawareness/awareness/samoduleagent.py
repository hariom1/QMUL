from abc import abstractmethod, ABC
from nebula.core.situationalawareness.awareness.sacommand import SACommand

class SAModuleAgent(ABC):
#TODO hacer el diccionario de tipos de agentes para luego tenerlo en cuenta en el arbitraje
    @abstractmethod
    async def get_agent(self):
        raise NotImplementedError

    @abstractmethod
    async def register_sa_agent(self):
        raise NotImplementedError
    
    @abstractmethod
    async def suggest_action(self, sac : SACommand):
        raise NotImplementedError
    
    @abstractmethod
    async def notify_all_suggestions_done(self, sac : SACommand):
        raise NotImplementedError