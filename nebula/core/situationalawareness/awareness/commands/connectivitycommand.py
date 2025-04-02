import asyncio
import logging
from nebula.core.utils.locker import Locker
from nebula.core.situationalawareness.awareness.commands.sacommand import SACommand, SACommandAction, SACOmmandPRIO, SACommandType

class ConnectivityCommand(SACommand):
    """Commands related to connectivity."""
    def __init__(
        self, 
        action: SACommandAction, 
        target: str, 
        priority: SACOmmandPRIO = SACOmmandPRIO.MEDIUM.name,
        paralelelizable = False
    ):
        super().__init__(SACommandType.CONNECTIVITY, action, target, priority, paralelelizable)

    async def execute(self):
        return await super().execute()
