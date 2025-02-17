import asyncio
import logging
from nebula.core.utils.locker import Locker
from nebula.core.aggregation.updatehandlers.updatehandler import UpdateHandler

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.aggregation.aggregator import Aggregator

class CFLUpdateHandler(UpdateHandler):
    def __init__(
        self,
        aggregator,
        addr
    ):
        pass
    
    async def round_expected_updates(self, federation_nodes: set):
        raise NotImplementedError
    
    async def storage_update(self, model, weight, source, round, local=False):
        raise NotImplementedError
    
    async def get_round_updates(self) -> dict[str, tuple[object, float]]:
        raise NotImplementedError

    async def notify_federation_update(self, source, remove=False):
        raise NotImplementedError
    
    async def get_round_missing_nodes(self) -> set[str]:
        raise NotImplementedError
    
    async def notify_if_all_updates_received(self):
        raise NotImplementedError
        
    async def stop_notifying_updates(self):
        raise NotImplementedError
    
    
# def get_nodes_pending_models_to_aggregate(self):
    #     return {node for key in self._pending_models_to_aggregate.keys() for node in key.split()}

    # async def _handle_global_update(self, model, source):
    #     logging.info(f"🔄  _handle_global_update | source={source}")
    #     logging.info(
    #         f"🔄  _handle_global_update | Received a model from {source}. Overwriting __models with the aggregated model."
    #     )
    #     self._pending_models_to_aggregate.clear()
    #     self._pending_models_to_aggregate = {source: (model, 1)}
    #     self._waiting_global_update = False
    #     await self._add_model_lock.release_async()
    #     await self._aggregation_done_lock.release_async()

    # async def _add_pending_model(self, model, weight, source):
    #     if len(self._federation_nodes) <= len(self.get_nodes_pending_models_to_aggregate()):
    #         logging.info("🔄  _add_pending_model | Ignoring model...")
    #         await self._add_model_lock.release_async()
    #         return None

    #     if source not in self._federation_nodes:
    #         logging.info(f"🔄  _add_pending_model | Can't add a model from ({source}), which is not in the federation.")
    #         await self._add_model_lock.release_async()
    #         return None

    #     elif source not in self.get_nodes_pending_models_to_aggregate():
    #         logging.info(
    #             "🔄  _add_pending_model | Node is not in the aggregation buffer --> Include model in the aggregation buffer."
    #         )
    #         self._pending_models_to_aggregate.update({source: (model, weight)})

    #     logging.info(
    #         f"🔄  _add_pending_model | Model added in aggregation buffer ({len(self.get_nodes_pending_models_to_aggregate())!s}/{len(self._federation_nodes)!s}) | Pending nodes: {self._federation_nodes - self.get_nodes_pending_models_to_aggregate()}"
    #     )

    #     # Check if _future_models_to_aggregate has models in the current round to include in the aggregation buffer
    #     if self.engine.get_round() in self._future_models_to_aggregate:
    #         logging.info(
    #             f"🔄  _add_pending_model | Including next models in the aggregation buffer for round {self.engine.get_round()}"
    #         )
    #         for future_model in self._future_models_to_aggregate[self.engine.get_round()]:
    #             if future_model is None:
    #                 continue
    #             future_model, future_weight, future_source = future_model
    #             if (
    #                 future_source in self._federation_nodes
    #                 and future_source not in self.get_nodes_pending_models_to_aggregate()
    #             ):
    #                 self._pending_models_to_aggregate.update({future_source: (future_model, future_weight)})
    #                 logging.info(
    #                     f"🔄  _add_pending_model | Next model added in aggregation buffer ({len(self.get_nodes_pending_models_to_aggregate())!s}/{len(self._federation_nodes)!s}) | Pending nodes: {self._federation_nodes - self.get_nodes_pending_models_to_aggregate()}"
    #                 )
    #         del self._future_models_to_aggregate[self.engine.get_round()]

    #         for future_round in list(self._future_models_to_aggregate.keys()):
    #             if future_round < self.engine.get_round():
    #                 del self._future_models_to_aggregate[future_round]

    #     if len(self.get_nodes_pending_models_to_aggregate()) >= len(self._federation_nodes):
    #         logging.info("🔄  _add_pending_model | All models were added in the aggregation buffer. Run aggregation...")
    #         await self._aggregation_done_lock.release_async()

    #     await self._add_model_lock.release_async()
    #     return self.get_nodes_pending_models_to_aggregate()

    # async def include_model_in_buffer(self, model, weight, source=None, round=None, local=False):
    #     await self._add_model_lock.acquire_async()
    #     logging.info(
    #         f"🔄  include_model_in_buffer | source={source} | round={round} | weight={weight} |--| __models={self._pending_models_to_aggregate.keys()} | federation_nodes={self._federation_nodes} | pending_models_to_aggregate={self.get_nodes_pending_models_to_aggregate()}"
    #     )
    #     if model is None:
    #         logging.info("🔄  include_model_in_buffer | Ignoring model bad formed...")
    #         await self._add_model_lock.release_async()
    #         return

    #     if round == -1:
    #         # Be sure that the model message is not from the initialization round (round = -1)
    #         logging.info("🔄  include_model_in_buffer | Ignoring model with round -1")
    #         await self._add_model_lock.release_async()
    #         return

    #     if self._waiting_global_update and not local:
    #         await self._handle_global_update(model, source)
    #         return

    #     await self._add_pending_model(model, weight, source)

    #     if len(self.get_nodes_pending_models_to_aggregate()) >= len(self._federation_nodes):
    #         logging.info(
    #             f"🔄  include_model_in_buffer | Broadcasting MODELS_INCLUDED for round {self.engine.get_round()}"
    #         )
    #         message = self.cm.create_message(
    #             "federation", "federation_models_included", [str(arg) for arg in [self.engine.get_round()]]
    #         )
    #         await self.cm.send_message_to_neighbors(message)

    #     return

    # async def get_aggregation(self):
    #     try:
    #         timeout = self.config.participant["aggregator_args"]["aggregation_timeout"]
    #         logging.info(f"Aggregation timeout: {timeout} starts...")
    #         await self.us.notify_if_all_updates_received()
    #         lock_task = asyncio.create_task(self._aggregation_done_lock.acquire_async(timeout=timeout))
    #         skip_task = asyncio.create_task(self._aggregation_waiting_skip.wait())
    #         done, pending = await asyncio.wait(
    #             [lock_task, skip_task],
    #             return_when=asyncio.FIRST_COMPLETED,
    #         )
    #         lock_acquired = lock_task in done
    #         if skip_task in done:
    #             logging.info("Skipping aggregation timeout, updates received before grace time")
    #             self._aggregation_waiting_skip.clear()
    #             if not lock_acquired:
    #                 lock_task.cancel()
    #             try:
    #                 await lock_task  # Clean cancel
    #             except asyncio.CancelledError:
    #                 pass

    #     except TimeoutError:
    #         logging.exception("🔄  get_aggregation | Timeout reached for aggregation")
    #     except asyncio.CancelledError:
    #         logging.exception("🔄  get_aggregation | Lock acquisition was cancelled")
    #     except Exception as e:
    #         logging.exception(f"🔄  get_aggregation | Error acquiring lock: {e}")
    #     finally:
    #         if lock_acquired:
    #             await self._aggregation_done_lock.release_async()

    #     await self.us.stop_notifying_updates()
    #     updates = await self.us.get_round_updates()
        
    #     missing_nodes = await self.us.get_round_missing_nodes()
        
    #     if missing_nodes:
    #         logging.info(f"🔄  get_aggregation | Aggregation incomplete, missing models from: {missing_nodes}")
    #     else:
    #         logging.info("🔄  get_aggregation | All models accounted for, proceeding with aggregation.")
        
    #     logging.info(
    #             f"🔄  Broadcasting MODELS_INCLUDED for round {self.engine.get_round()}"
    #         )    
    #     message = self.cm.create_message(
    #             "federation", "federation_models_included", [str(arg) for arg in [self.engine.get_round()]]
    #         )
    #     await self.cm.send_message_to_neighbors(message)

        # if self._waiting_global_update and len(self._pending_models_to_aggregate) == 1:
        #     logging.info(
        #         "🔄  get_aggregation | Received an global model. Overwriting my model with the aggregated model."
        #     )
        #     aggregated_model = next(iter(self._pending_models_to_aggregate.values()))[0]
        #     self._pending_models_to_aggregate.clear()
        #     return aggregated_model

        # unique_nodes_involved = set(node for key in self._pending_models_to_aggregate for node in key.split())

        # if len(unique_nodes_involved) != len(self._federation_nodes):
        #     missing_nodes = self._federation_nodes - unique_nodes_involved
        #     logging.info(f"🔄  get_aggregation | Aggregation incomplete, missing models from: {missing_nodes}")
        # else:
        #     logging.info("🔄  get_aggregation | All models accounted for, proceeding with aggregation.")

        # self._pending_models_to_aggregate = await self.engine.apply_weight_strategy(self._pending_models_to_aggregate)
        # aggregated_result = self.run_aggregation(self._pending_models_to_aggregate)
        # self._pending_models_to_aggregate.clear()
        
        # updates = await self.engine.apply_weight_strategy(updates)
        # aggregated_result = self.run_aggregation(updates)
        # return aggregated_result

    # async def include_next_model_in_buffer(self, model, weight, source=None, round=None):
    #     logging.info(f"🔄  include_next_model_in_buffer | source={source} | round={round} | weight={weight}")
    #     if round not in self._future_models_to_aggregate:
    #         self._future_models_to_aggregate[round] = []
    #     decoded_model = self.engine.trainer.deserialize_model(model)
    #     await self._add_next_model_lock.acquire_async()
    #     self._future_models_to_aggregate[round].append((decoded_model, weight, source))
    #     await self._add_next_model_lock.release_async()

    #     # Verify if we are waiting an update that maybe we wont received
    #     if self._aggregation_done_lock.locked():
    #         pending_nodes: set = self._federation_nodes - self.get_nodes_pending_models_to_aggregate()
    #         if pending_nodes:
    #             for f_round, future_updates in self._future_models_to_aggregate.items():
    #                 for _, _, source in future_updates:
    #                     if source in pending_nodes:
    #                         # logging.info(f"Waiting update from source: {source}, but future update storaged for round: {f_round}")
    #                         pending_nodes.discard(source)

    #             if not pending_nodes:
    #                 logging.info("Received advanced updates for all sources missing this round")
    #                 await self._aggregation_done_lock.release_async()


    # def verify_push_done(self, current_round):
    #     current_round = self.engine.get_round()
    #     if self.engine.get_synchronizing_rounds():
    #         logging.info("Verifying if round push is done")
    #         if self._end_round_push <= current_round:
    #             logging.info("Push done...")
    #             self.engine.set_synchronizing_rounds(False)
    #             self._end_round_push = 0
    #             if len(self._future_models_to_aggregate.items()) < 2:
    #                 logging.info("Device is sinchronized")
    #                 self.engine.update_sinchronized_status(True)
    #             else:
    #                 logging.info("Device is not sinchronized yet | more actions required...")

    # async def aggregation_push_available(self):
    #     """
    #     If the node is not sinchronized with the federation, it may be possible to make a push
    #     and try to catch the federation asap.
    #     """
    #     # TODO verify if an already sinchronized node gets desinchronized
    #     current_round = self.engine.get_round()
    #     self.verify_push_done(current_round)

    #     await self._push_strategy_lock.acquire_async()

    #     logging.info(
    #         f"❗️ synchronized status: {self.engine.get_sinchronized_status()} | Analizing if an aggregation push is available..."
    #     )
    #     if (
    #         not self.engine.get_sinchronized_status()
    #         and not self.engine.get_trainning_in_progress_lock().locked()
    #         and not self.engine.get_synchronizing_rounds()
    #     ):
    #         n_fed_nodes = len(self._federation_nodes)
    #         further_round = current_round
    #         logging.info(
    #             f" Pending models: {len(self.get_nodes_pending_models_to_aggregate())} | federation: {n_fed_nodes}"
    #         )
    #         if len(self.get_nodes_pending_models_to_aggregate()) < n_fed_nodes:
    #             n_fed_nodes -= 1
    #             for f_round, fm in self._future_models_to_aggregate.items():
    #                 # future_models dont count self node
    #                 if (f_round - current_round) > 1 or len(fm) == n_fed_nodes:
    #                     further_round = f_round
    #                     push = self.engine.get_push_acceleration()
    #                     if push == "slow":
    #                         logging.info("❗️ SLOW push selected")
    #                         logging.info(
    #                             f"❗️ Federation is at least {(f_round - current_round)} rounds ahead, Pushing slow..."
    #                         )
    #                         await self.engine.set_pushed_done(further_round - current_round)
    #                         self.engine.update_sinchronized_status(False)
    #                         self.engine.set_synchronizing_rounds(True)
    #                         self._end_round_push = further_round
    #                         self._aggregation_waiting_skip.set()
    #                         await self._push_strategy_lock.release_async()
    #                         return

    #             if further_round != current_round and push == "fast":
    #                 logging.info("❗️ FAST push selected")
    #                 logging.info(f"❗️ FUTURE round: {further_round} is available, Pushing fast...")

    #                 if further_round == (current_round + 1):
    #                     logging.info(f"🔄 Rounds jumped: {1}...")
    #                     await self.engine.set_pushed_done(further_round - current_round)
    #                     self.engine.update_sinchronized_status(False)
    #                     self.engine.set_synchronizing_rounds(True)
    #                     self._end_round_push = further_round
    #                     self._aggregation_waiting_skip.set()
    #                     await self._push_strategy_lock.release_async()
    #                     return

    #                 logging.info(f"🔄 Number of rounds jumped: {further_round - current_round}...")
    #                 own_update = self._pending_models_to_aggregate.get(self.engine.get_addr())
    #                 while own_update == None:
    #                     own_update = self._pending_models_to_aggregate.get(self.engine.get_addr())
    #                     asyncio.sleep(1)
    #                 (model, weight) = own_update

    #                 # Getting locks to avoid concurrency issues
    #                 await self._add_model_lock.acquire_async()
    #                 await self._add_next_model_lock.acquire_async()

    #                 # Remove all pendings updates and add own_update
    #                 self._pending_models_to_aggregate.clear()
    #                 self._pending_models_to_aggregate.update({self.engine.get_addr(): (model, weight)})

    #                 # Add to pendings the future round updates
    #                 for future_update in self._future_models_to_aggregate[further_round]:
    #                     (decoded_model, weight, source) = future_update
    #                     self._pending_models_to_aggregate.update({source: (decoded_model, weight)})

    #                 # Clear all rounds that are going to be jumped
    #                 self._future_models_to_aggregate = {
    #                     key: value for key, value in self._future_models_to_aggregate.items() if key > further_round
    #                 }

    #                 self.engine.update_sinchronized_status(False)
    #                 self.engine.set_synchronizing_rounds(True)
    #                 await self.engine.set_pushed_done(further_round - current_round)
    #                 self._end_round_push = further_round
    #                 self.engine.set_round(further_round)
    #                 await self._add_model_lock.release_async()
    #                 await self._add_next_model_lock.release_async()
    #                 await self._push_strategy_lock.release_async()
    #                 self._aggregation_waiting_skip.set()
    #                 return

    #             else:
    #                 if len(self._future_models_to_aggregate.items()) < 2:
    #                     logging.info("Info | No future rounds available, device is up to date...")
    #                     self.engine.update_sinchronized_status(True)
    #                     self.engine.set_synchronizing_rounds(False)
    #                 else:
    #                     logging.info("No rounds can be pushed...")
    #                 await self._push_strategy_lock.release_async()
    #         else:
    #             logging.info(
    #                 f"All models updates are received | models number: {len(self.get_nodes_pending_models_to_aggregate())}"
    #             )
    #             await self._push_strategy_lock.release_async()
    #     else:
    #         if not self.engine.get_sinchronized_status():
    #             if self.engine.get_trainning_in_progress_lock().locked():
    #                 logging.info("❗️ Cannot analize push | Trainning in progress")
    #             elif self.engine.get_synchronizing_rounds():
    #                 logging.info("❗️ Cannot analize push | Already pushing rounds")
    #         await self._push_strategy_lock.release_async()
