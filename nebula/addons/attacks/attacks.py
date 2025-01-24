from abc import ABC, abstractmethod
from functools import wraps
import asyncio
import importlib
import logging
import copy
import types
import numpy as np
import torch
from torchmetrics.functional import pairwise_cosine_similarity

from nebula.addons.attacks.poisoning.datapoison import datapoison
from nebula.addons.attacks.poisoning.labelflipping import labelFlipping
from nebula.addons.attacks.poisoning.modelpoison import modelPoison

# To take into account:
# - Malicious nodes do not train on their own data
# - Malicious nodes aggregate the weights of the other nodes, but not their own
# - The received weights may be the node own weights (aggregated of neighbors), or
#   if the attack is performed specifically for one of the neighbors, it can take
#   its weights only (should be more effective if they are different).


class AttackException(Exception):
    pass
    

##########
# Attack #
##########


class Attack(ABC):
    """
    Base class for implementing various attack behaviors by dynamically injecting
    malicious behavior into existing functions or methods.

    This class provides an interface for replacing benign functions with malicious
    behaviors and for defining specific attack implementations. Subclasses must
    implement the `attack` and `_inject_malicious_behaviour` methods.
    """
    async def _replace_benign_function(function_route: str, malicious_behaviour):
        """
        Dynamically replace a method in a class with a malicious behavior.

        Args:
            function_route (str): The route to the class and method to be replaced, in the format 'module.class.method'.
            malicious_behaviour (callable): The malicious function that will replace the target method.

        Raises:
            AttributeError: If the specified class does not have the target method.
            ImportError: If the module specified in `function_route` cannot be imported.
            Exception: If any other error occurs during the process.

        Returns:
            None
        """
        try:
            *module_route, class_and_func = function_route.rsplit(".", maxsplit=1)
            module = ".".join(module_route)
            class_name, function_name = class_and_func.split(".")

            # Import the module
            module_obj = importlib.import_module(module)

            # Retrieve the class
            changing_class = getattr(module_obj, class_name)

            # Verify the class has the target method
            if not hasattr(changing_class, function_name):
                raise AttributeError(f"Class '{class_name}' has no method named: '{function_name}'.")

            # Replace the original method with the malicious behavior
            setattr(changing_class, function_name, malicious_behaviour)
            print(f"Function '{function_name}' has been replaced with '{malicious_behaviour.__name__}'.")
        except Exception as e:
            logging.error(f"Error replacing function: {e}")

    @abstractmethod
    async def attack(self):
        """
        Abstract method to define the attack logic.

        Subclasses must implement this method to specify the actions to perform
        during an attack.

        Raises:
            NotImplementedError: If the method is not implemented in a subclass.
        """
        raise NotImplementedError

    @abstractmethod
    async def _inject_malicious_behaviour(self, target_function: callable, *args, **kwargs) -> None:
        """
        Abstract method to inject a malicious behavior into an existing function.

        This method must be implemented in subclasses to define how the malicious
        behavior should interact with the target function.

        Args:
            target_function (callable): The function to inject the malicious behavior into.
            *args: Positional arguments for the malicious behavior.
            **kwargs: Keyword arguments for the malicious behavior.

        Raises:
            NotImplementedError: If the method is not implemented in a subclass.
        """
        raise NotImplementedError


#######################
# Communication Attacks#
#######################


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


#################
# Dataset Attacks#
#################


class DatasetAttack(Attack):
    """
    Implements an attack that replaces the training dataset with a malicious version
    during specific rounds of the engine's execution.

    This attack modifies the dataset used by the engine's trainer to introduce malicious
    data, potentially impacting the model's training process.
    """
    def __init__(self, engine):
        """
        Initializes the DatasetAttack with the given engine.

        Args:
            engine: The engine managing the attack context.
        """
        self.engine = engine
        self.round_start_attack = 0
        self.round_stop_attack = 10

    async def attack(self):
        """
        Performs the attack by replacing the training dataset with a malicious version.

        During the specified rounds of the attack, the engine's trainer is provided
        with a malicious dataset. The attack is stopped when the engine reaches the
        designated stop round.
        """
        if self.engine.round in range(self.round_start_attack, self.round_stop_attack):
            logging.info("[DatasetAttack] Performing attack")
            self.engine.trainer.datamodule.train_set = self.get_malicious_dataset()
        elif self.engine.round == self.round_stop_attack + 1:
            logging.info("[DatasetAttack] Stopping attack")

    async def _inject_malicious_behaviour(self, target_function, *args, **kwargs):
        """
        Abstract method for injecting malicious behavior into a target function.

        This method is not implemented in this class and must be overridden by subclasses
        if additional malicious behavior is required.

        Args:
            target_function (callable): The function to inject the malicious behavior into.
            *args: Positional arguments for the malicious behavior.
            **kwargs: Keyword arguments for the malicious behavior.

        Raises:
            NotImplementedError: This method is not implemented in this class.
        """
        pass

    @abstractmethod
    def get_malicious_dataset(self):
        """
        Abstract method to retrieve the malicious dataset.

        Subclasses must implement this method to define how the malicious dataset
        is created or retrieved.

        Raises:
            NotImplementedError: If the method is not implemented in a subclass.
        """
        raise NotImplementedError


class LabelFlippingAttack(DatasetAttack):
    """
    Implements an attack that flips the labels of a portion of the training dataset.

    This attack alters the labels of certain data points in the training set to
    mislead the training process.
    """
    def __init__(self, engine, attack_params):
        """
        Initializes the LabelFlippingAttack with the engine and attack parameters.

        Args:
            engine: The engine managing the attack context.
            attack_params (dict): Parameters for the attack, including the percentage of
                                  poisoned data, targeting options, and label specifications.
        """
        super().__init__(engine)
        self.datamodule = engine._trainer.datamodule
        self.poisoned_percent = float(attack_params["poisoned_percent"])
        self.targeted = attack_params["targeted"]
        self.target_label = int(attack_params["target_label"])
        self.target_changed_label = int(attack_params["target_changed_label"])
        self.round_start_attack = int(attack_params["round_start_attack"])
        self.round_stop_attack = int(attack_params["round_stop_attack"])

    def get_malicious_dataset(self):
        """
        Creates a malicious dataset by flipping the labels of selected data points.

        Returns:
            Dataset: The modified dataset with flipped labels.
        """
        return labelFlipping(
            self.datamodule.train_set, 
            self.datamodule.train_set_indices, 
            self.poisoned_percent, 
            self.targeted, 
            self.target_label, 
            self.target_changed_label)
    
    
class SamplePoisoningAttack(DatasetAttack):
    """
    Implements a data poisoning attack on a training dataset.

    This attack introduces noise or modifies specific data points to influence 
    the behavior of a machine learning model.

    Args:
        engine (object): The training engine object, including the associated 
                         datamodule.
        attack_params (dict): Attack parameters including:
            - poisoned_percent (float): The percentage of data points to be poisoned.
            - poisoned_ratio (float): The ratio of poisoned data relative to the total dataset.
            - targeted (bool): Whether the attack is targeted at a specific label.
            - target_label (int): The target label for the attack (used if targeted is True).
            - noise_type (str): The type of noise to introduce during the attack.
    """

    def __init__(self, engine, attack_params):
        """
        Initializes the SamplePoisoningAttack with the specified engine and parameters.

        Args:
            engine (object): The training engine object.
            attack_params (dict): Dictionary of attack parameters.
        """
        super().__init__(engine)
        self.datamodule = engine._trainer.datamodule
        self.poisoned_percent = float(attack_params["poisoned_percent"])
        self.poisoned_ratio = float(attack_params["poisoned_ratio"])
        self.targeted = attack_params["targeted"]
        self.target_label = int(attack_params["target_label"])
        self.noise_type = attack_params["noise_type"]
        self.round_start_attack = int(attack_params["round_start_attack"])
        self.round_stop_attack = int(attack_params["round_stop_attack"])

    def get_malicious_dataset(self):
        """
        Generates a poisoned dataset based on the specified parameters.

        Returns:
            Dataset: A modified version of the training dataset with poisoned data.
        """
        return datapoison(
            self.datamodule.train_set,
            self.datamodule.train_set_indices,
            self.poisoned_percent,
            self.poisoned_ratio,
            self.targeted,
            self.target_label,
            self.noise_type
        )


#################
# Model Attacks#
#################


class ModelAttack(Attack):
    """
    Base class for implementing model attacks, which modify the behavior of 
    model aggregation methods.

    This class defines a decorator for introducing malicious behavior into the 
    aggregation process and requires subclasses to implement the model-specific 
    attack logic.

    Args:
        engine (object): The engine object that manages the aggregator for 
                         model aggregation.
    """
    def __init__(self, engine):
        """
        Initializes the ModelAttack with the specified engine.

        Args:
            engine (object): The engine object that includes the aggregator.
        """
        super().__init__()
        self.engine = engine
        self.aggregator = engine._aggregator
        self.original_aggregation = engine.aggregator.run_aggregation
        self.round_start_attack = 0
        self.round_stop_attack = 10

    def aggregator_decorator(self):
        """
        Decorator that adds a delay to the execution of the original method.

        Args:
            delay (int or float): The time in seconds to delay the method execution.

        Returns:
            function: A decorator function that wraps the target method with 
                      the delay logic and potentially modifies the aggregation 
                      behavior to inject malicious changes.
        """
        # The actual decorator function that will be applied to the target method
        def decorator(func):
            @wraps(func)  # Preserves the metadata of the original function
            def wrapper(*args):
                _, *new_args = args  # Exclude self argument
                accum = func(*new_args)
                logging.info(f"malicious_aggregate | original aggregation result={accum}")

                if new_args is not None:
                    accum = self.model_attack(accum)
                    logging.info(f"malicious_aggregate | attack aggregation result={accum}")
                return accum
            return wrapper
        return decorator

    @abstractmethod
    def model_attack(self, received_weights):
        """
        Abstract method that applies the specific model attack logic.

        This method should be implemented in subclasses to define the attack
        logic on the received model weights.

        Args:
            received_weights (any): The aggregated model weights to be modified.

        Returns:
            any: The modified model weights after applying the attack.
        """
        raise NotImplementedError

    async def _inject_malicious_behaviour(self):
        """
        Modifies the `propagate` method of the aggregator to include the delay 
        introduced by the decorator.

        This method wraps the original aggregation method with the malicious 
        decorator to inject the attack behavior into the aggregation process.
        """
        decorated_aggregation = self.aggregator_decorator()(self.aggregator.run_aggregation)
        self.aggregator.run_aggregation = types.MethodType(decorated_aggregation, self.aggregator)

    async def _restore_original_behaviour(self):
        """
        Restores the original behaviour of the `run_aggregation` method.
        """
        self.aggregator.run_aggregation = self.original_aggregation

    async def attack(self):
        """
        Initiates the malicious attack by injecting the malicious behavior 
        into the aggregation process.

        This method logs the attack and calls the method to modify the aggregator.
        """
        if self.engine.round == self.round_start_attack:
            logging.info("[ModelAttack] Injecting malicious behaviour")
            await self._inject_malicious_behaviour()
        elif self.engine.round == self.round_stop_attack + 1:
            logging.info("[ModelAttack] Stopping attack")
            await self._restore_original_behaviour()
        elif self.engine.round in range(self.round_start_attack, self.round_stop_attack):
            logging.info("[ModelAttack] Performing attack")


class ModelPoisonAttack(ModelAttack):
    """
    Implements a model poisoning attack by modifying the received model weights 
    during the aggregation process.

    This attack introduces specific modifications to the model weights to 
    influence the global model's behavior.

    Args:
        engine (object): The training engine object that manages the aggregator.
        attack_params (dict): Parameters for the attack, including:
            - poisoned_ratio (float): The ratio of model weights to be poisoned.
            - noise_type (str): The type of noise to introduce during the attack.
    """
    def __init__(self, engine, attack_params):
        """
        Initializes the ModelPoisonAttack with the specified engine and parameters.

        Args:
            engine (object): The training engine object.
            attack_params (dict): Dictionary of attack parameters.
        """
        super().__init__(engine)
        self.poisoned_ratio = float(attack_params["poisoned_ratio"])
        self.noise_type = attack_params["noise_type"].lower()
        self.round_start_attack = int(attack_params["round_start_attack"])
        self.round_stop_attack = int(attack_params["round_stop_attack"])

    def model_attack(self, received_weights):
        """
        Applies the model poisoning attack by modifying the received model weights.

        Args:
            received_weights (any): The aggregated model weights to be poisoned.

        Returns:
            any: The modified model weights after applying the poisoning attack.
        """
        logging.info("[ModelPoisonAttack] Performing model poison attack")
        received_weights = modelPoison(received_weights, self.poisoned_ratio, self.noise_type)
        return received_weights

 
class GLLNeuronInversionAttack(ModelAttack):
    """
    Implements a neuron inversion attack on the received model weights.

    This attack aims to invert the values of neurons in specific layers 
    by replacing their values with random noise, potentially disrupting the model's 
    functionality during aggregation.

    Args:
        engine (object): The training engine object that manages the aggregator.
        _ (any): A placeholder argument (not used in this class).
    """
    def __init__(self, engine, attack_params):
        """
        Initializes the GLLNeuronInversionAttack with the specified engine.

        Args:
            engine (object): The training engine object.
            _ (any): A placeholder argument (not used in this class).
        """
        super().__init__(engine)
        self.round_start_attack = int(attack_params["round_start_attack"])
        self.round_stop_attack = int(attack_params["round_stop_attack"])

    def model_attack(self, received_weights):
        """
        Performs the neuron inversion attack by modifying the weights of a specific 
        layer with random noise.

        This attack replaces the weights of a chosen layer with random values, 
        which may disrupt the functionality of the model.

        Args:
            received_weights (dict): The aggregated model weights to be modified.

        Returns:
            dict: The modified model weights after applying the neuron inversion attack.
        """
        logging.info("[GLLNeuronInversionAttack] Performing neuron inversion attack")
        lkeys = list(received_weights.keys())
        logging.info(f"Layer inverted: {lkeys[-2]}")
        received_weights[lkeys[-2]].data = torch.rand(received_weights[lkeys[-2]].shape) * 10000
        return received_weights


class NoiseInjectionAttack(ModelAttack):
    """
    Implements a noise injection attack on the received model weights.

    This attack introduces noise into the model weights by adding random values 
    scaled by a specified strength, potentially disrupting the model’s behavior.

    Args:
        engine (object): The training engine object that manages the aggregator.
        attack_params (dict): Parameters for the attack, including:
            - strength (int): The strength of the noise to be injected into the weights.
    """
    def __init__(self, engine, attack_params):
        """
        Initializes the NoiseInjectionAttack with the specified engine and parameters.

        Args:
            engine (object): The training engine object.
            attack_params (dict): Dictionary of attack parameters, including strength.
        """
        super().__init__(engine)
        self.strength = int(attack_params["strength"])
        self.round_start_attack = int(attack_params["round_start_attack"])
        self.round_stop_attack = int(attack_params["round_stop_attack"])

    def model_attack(self, received_weights):
        """
        Performs the noise injection attack by adding random noise to the model weights.

        The noise is generated from a normal distribution and scaled by the 
        specified strength, modifying each layer's weights in the model.

        Args:
            received_weights (dict): The aggregated model weights to be modified.

        Returns:
            dict: The modified model weights after applying the noise injection attack.
        """
        logging.info(f"[NoiseInjectionAttack] Performing noise injection attack with a strength of {self.strength}")
        lkeys = list(received_weights.keys())
        for k in lkeys:
            logging.info(f"Layer noised: {k}")
            received_weights[k].data += torch.randn(received_weights[k].shape) * self.strength
        return received_weights


class SwappingWeightsAttack(ModelAttack):
    """
    Implements a swapping weights attack on the received model weights.

    This attack performs stochastic swapping of weights in a specified layer of the model, 
    potentially disrupting its performance. The attack is not deterministic, and its performance 
    can vary. The code may not work as expected for some layers due to reshaping, and its 
    computational cost scales quadratically with the layer size. It should not be applied to 
    the last layer, as it would make the attack detectable due to high loss on the malicious node.

    Args:
        engine (object): The training engine object that manages the aggregator.
        attack_params (dict): Parameters for the attack, including:
            - layer_idx (int): The index of the layer where the weights will be swapped.
    """
    def __init__(self, engine, attack_params):
        """
        Initializes the SwappingWeightsAttack with the specified engine and parameters.

        Args:
            engine (object): The training engine object.
            attack_params (dict): Dictionary of attack parameters, including the layer index.
        """
        super().__init__(engine)
        self.layer_idx = int(attack_params["layer_idx"])
        self.round_start_attack = int(attack_params["round_start_attack"])
        self.round_stop_attack = int(attack_params["round_stop_attack"])

    def model_attack(self, received_weights):
        """
        Performs the swapping weights attack by computing a similarity matrix and 
        swapping the weights of a specified layer based on their similarity.

        This method applies a greedy algorithm to swap weights in the selected layer 
        in a way that could potentially disrupt the training process. The attack also 
        ensures that some rows are fully permuted, and others are swapped based on 
        similarity.

        Args:
            received_weights (dict): The aggregated model weights to be modified.

        Returns:
            dict: The modified model weights after performing the swapping attack.
        """
        logging.info("[SwappingWeightsAttack] Performing swapping weights attack")
        lkeys = list(received_weights.keys())
        wm = received_weights[lkeys[self.layer_idx]]

        # Compute similarity matrix
        sm = torch.zeros((wm.shape[0], wm.shape[0]))
        for j in range(wm.shape[0]):
            sm[j] = pairwise_cosine_similarity(wm[j].reshape(1, -1), wm.reshape(wm.shape[0], -1))

        # Check rows/cols where greedy approach is optimal
        nsort = np.full(sm.shape[0], -1)
        rows = []
        for j in range(sm.shape[0]):
            k = torch.argmin(sm[j])
            if torch.argmin(sm[:, k]) == j:
                nsort[j] = k
                rows.append(j)
        not_rows = np.array([i for i in range(sm.shape[0]) if i not in rows])

        # Ensure the rest of the rows are fully permuted (not optimal, but good enough)
        nrs = copy.deepcopy(not_rows)
        nrs = np.random.permutation(nrs)
        while np.any(nrs == not_rows):
            nrs = np.random.permutation(nrs)
        nsort[not_rows] = nrs
        nsort = torch.tensor(nsort)

        # Apply permutation to weights
        received_weights[lkeys[self.layer_idx]] = received_weights[lkeys[self.layer_idx]][nsort]
        received_weights[lkeys[self.layer_idx + 1]] = received_weights[lkeys[self.layer_idx + 1]][nsort]
        if self.layer_idx + 2 < len(lkeys):
            received_weights[lkeys[self.layer_idx + 2]] = received_weights[lkeys[self.layer_idx + 2]][:, nsort]
        
        return received_weights


def create_attack(engine) -> Attack:
    """
    Creates an attack object based on the attack name specified in the engine configuration.

    This function uses a predefined map of available attacks (`ATTACK_MAP`) to instantiate
    the corresponding attack class based on the attack name in the configuration. The attack 
    parameters are also extracted from the configuration and passed when creating the attack object.

    Args:
        engine (object): The training engine object containing the configuration for the attack.

    Returns:
        Attack: An instance of the specified attack class.

    Raises:
        AttackException: If the specified attack name is not found in the `ATTACK_MAP`.
    """
    ATTACK_MAP = {
        "GLLNeuronInversionAttack": GLLNeuronInversionAttack,
        "NoiseInjectionAttack": NoiseInjectionAttack,
        "SwappingWeightsAttack": SwappingWeightsAttack,
        "DelayerAttack": DelayerAttack,
        "Label Flipping": LabelFlippingAttack,
        "Sample Poisoning": SamplePoisoningAttack,
        "Model Poisoning": ModelPoisonAttack,
    }
    
    # Get attack name and parameters from the engine configuration
    attack_name = engine.config.participant["adversarial_args"]["attacks"]
    attack_params = engine.config.participant["adversarial_args"].get("attack_params", {}).items()
    
    # Look up the attack class based on the attack name
    attack = ATTACK_MAP.get(attack_name)

    # If the attack is found, return an instance of the attack class
    if attack:
        return attack(engine, dict(attack_params))
    else:
        # If the attack name is not found, raise an exception
        raise AttackException(f"Attack {attack_name} not found")
