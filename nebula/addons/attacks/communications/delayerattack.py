import asyncio
from functools import wraps
import logging
import types
from nebula.addons.attacks.attacks import Attack


class DelayerAttack(Attack):
    """
    Implements an attack that delays the execution of a target method by a specified amount of time.

    This attack dynamically modifies the `propagate` method of the propagator to
    introduce a delay during its execution.
    """
    def __init__(self, engine, attack_params):
        """
        Initializes the DelayerAttack with the engine and attack parameters.

        Args:
            engine: The engine managing the attack context.
            attack_params (dict): Parameters for the attack, including the delay duration.
        """
        super().__init__()
        self.engine = engine
        self.propagator = self.engine._cm._propagator
        self.original_propagate = self.propagator.propagate
        self.delay = int(attack_params["delay"])
        self.round_start_attack = int(attack_params["round_start_attack"])
        self.round_stop_attack = int(attack_params["round_stop_attack"])

    def delay_decorator(self, delay):
        """
        Decorator that adds a delay to the execution of the original method.

        Args:
            delay (int or float): The time in seconds to delay the method execution.

        Returns:
            function: A decorator function that wraps the target method with the delay logic.
        """
        # The actual decorator function that will be applied to the target method
        def decorator(func):
            @wraps(func)  # Preserves the metadata of the original function
            async def wrapper(*args):
                logging.info(f"[DelayerAttack] Adding delay of {delay} seconds")

                await asyncio.sleep(delay)
                _, *new_args = args  # Exclude self argument
                return await func(*new_args)
            return wrapper
        return decorator

    async def _inject_malicious_behaviour(self):
        """
        Modifies the `propagate` method of the propagator to include a delay.
        """
        decorated_propagate = self.delay_decorator(self.delay)(self.propagator.propagate)

        self.propagator.propagate = types.MethodType(decorated_propagate, self.propagator)

    async def _restore_original_behaviour(self):
        """
        Restores the original behaviour of the `propagate` method.
        """
        self.propagator.propagate = self.original_propagate

    async def attack(self):
        """
        Starts the attack by injecting the malicious behaviour.

        If the current round matches the attack start round, the malicious behavior
        is injected. If it matches the stop round, the original behavior is restored.
        """
        if self.engine.round == self.round_stop_attack:
            logging.info(f"[DelayerAttack] Stopping Delayer attack")
            await self._restore_original_behaviour()
        elif self.engine.round == self.round_start_attack:
            logging.info("[DelayerAttack] Injecting malicious behaviour")
            await self._inject_malicious_behaviour()