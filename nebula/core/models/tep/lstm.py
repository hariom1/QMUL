# import lightning as pl
import torch

from nebula.core.models.nebulamodel import NebulaModel
from torch.nn import functional as F
# from torchmetrics.classification import BinaryConfusionMatrix, BinaryAccuracy, BinaryF1Score, BinaryPrecision, BinaryRecall


###############################
#    Multilayer Perceptron    #
###############################
class TEPLSTM(NebulaModel):
    def __init__(self, input_channels=1, num_classes=2, learning_rate=0.001, metrics=None, confusion_matrix=None, seed=None):
        super().__init__(input_channels, num_classes, learning_rate, metrics, confusion_matrix, seed)

        self.example_input_array = torch.zeros(1, 5, 52)
        self.learning_rate = learning_rate
        self.hidden_layers1 = 64
        self.hidden_layers2 = 32
        # lstm1, lstm2, linear are all layers in the network
        self.lstm1 = torch.nn.LSTM(52, self.hidden_layers1, batch_first=True)
        self.lstm2 = torch.nn.LSTM(self.hidden_layers1, self.hidden_layers2, batch_first=True)
        self.linear = torch.nn.Linear(self.hidden_layers2, 1)
        self.criterion = torch.nn.BCEWithLogitsLoss()
        
        self.epoch_num_steps = {"Train": 0, "Validation": 0, "Test": 0}
        self.epoch_loss_sum = {"Train": 0.0, "Validation": 0.0, "Test": 0.0}

        self.epoch_output = {"Train": [], "Validation": [], "Test": []}
        self.epoch_real = {"Train": [], "Validation": [], "Test": []}
    
    def forward(self, x):
        """ """
        outputs, num_samples = [], x.size(0)
        h_t = torch.zeros(1, num_samples, self.hidden_layers1, dtype=torch.float32)
        c_t = torch.zeros(1, num_samples, self.hidden_layers1, dtype=torch.float32)
        h_t2 = torch.zeros(1, num_samples, self.hidden_layers2, dtype=torch.float32)
        c_t2 = torch.zeros(1, num_samples, self.hidden_layers2, dtype=torch.float32)
        h_t, c_t = self.lstm1(x, (h_t, c_t)) # initial hidden and cell states
        h_t2, c_t2 = self.lstm2(h_t, (h_t2, c_t2)) # new hidden and cell states
        outputs = self.linear(h_t2) # output from the last FC layer
        outputs = torch.sigmoid(outputs)
        return outputs[:,-1,:]

    def configure_optimizers(self):
        """ """
        optimizer = torch.optim.Adam(self.parameters(), lr=self.learning_rate)
        return optimizer
    
    def step(self, batch, batch_idx, phase):
        x, y = batch
        
        # logging.info(f"{phase}/x shape: {x.shape}")
        # logging.info(f"{phase}/y shape: {y.shape}")
        
        y_pred = self(x)
        y_one_hot = torch.nn.functional.one_hot(y, num_classes=2).float()
        
        # logging.info(f"{phase}/y_pred shape: {y_pred.shape}")
        # logging.info(f"{phase}/y_one_hot shape: {y_one_hot.shape}")
        
        loss = self.criterion(y_pred, y_one_hot)
        
        # self.process_metrics(phase, y_pred, y_one_hot, loss)

        return loss

    def training_step(self, batch, batch_idx):
        """
        Training step for the model.
        Args:
            batch:
            batch_idx:
        Returns:
        """
        return self.step(batch, batch_idx=batch_idx, phase="Train")
    
    def validation_step(self, batch, batch_idx):
        """
        Validation step for the model.
        Args:
            batch:
            batch_idx:

        Returns:
        """
        return self.step(batch, batch_idx=batch_idx, phase="Validation")
    
    def test_step(self, batch, batch_idx, dataloader_idx=None):
        """
        Test step for the model.
        Args:
            batch:
            batch_idx:

        Returns:
        """
        return self.step(batch, batch_idx=batch_idx, phase="Test")
    
    # def step(self, batch, phase):
    #     x, y = batch
    #     logits = self(x)
    #     y_pred = self.forward(x)
    #     loss = F.binary_cross_entropy(logits, y.unsqueeze(1).float())

    #     # Get metrics for each batch and log them
    #     self.process_metrics(phase, y_pred, y, loss)

    #     # Avoid memory leak when logging loss values
    #     self.epoch_loss_sum[phase] += loss
    #     self.epoch_num_steps[phase] += 1

    #     return loss
    
    # def training_step(self, batch, batch_id):
    #     """
    #     Training step for the model.
    #     Args:
    #         batch:
    #         batch_id:

    #     Returns:
    #     """
    #     return self.step(batch, "Train")
    
    # def validation_step(self, batch, batch_idx):
    #     """
    #     Validation step for the model.
    #     Args:
    #         batch:
    #         batch_idx:

    #     Returns:
    #     """
    #     return self.step(batch, "Validation")
    
    # def test_step(self, batch, batch_idx):
#         """
#         Test step for the model.
#         Args:
#             batch:
#             batch_idx:

#         Returns:
#         """
#         return self.step(batch, "Test")


# class TEPLSTM(pl.LightningModule):
#     """
#     Multilayer Perceptron (MLP) to solve WADI with PyTorch Lightning.
#     """

#     def __init__(
#             self,
#             metrics=None,
#             out_channels=1, 
#             lr_rate=0.001, 
#             seed=1000
#     ):  # low lr to avoid overfitting

#         if metrics is None:
#             metrics = [BinaryAccuracy, BinaryPrecision, BinaryRecall, BinaryF1Score, BinaryConfusionMatrix]

#         self.metrics = []
#         if type(metrics) is list:
#             try:
#                 for m in metrics:
#                     self.metrics.append(m(num_classes=2))
#             except TypeError:
#                 raise TypeError("metrics must be a list of torchmetrics.Metric")

#         # Set seed for reproducibility initialization
#         if seed is not None:
#             torch.manual_seed(seed)
#             torch.cuda.manual_seed_all(seed)

#         super().__init__()
#         self.example_input_array = torch.zeros(1, 5, 52)
#         self.lr_rate = lr_rate

#         self.hidden_layers1 = 64
#         self.hidden_layers2 = 32
#         # lstm1, lstm2, linear are all layers in the network
#         self.lstm1 = torch.nn.LSTM(52, self.hidden_layers1, batch_first=True)
#         self.lstm2 = torch.nn.LSTM(self.hidden_layers1, self.hidden_layers2, batch_first=True)
#         self.linear = torch.nn.Linear(self.hidden_layers2, 1)

#         self.epoch_global_number = {"Train": 0, "Validation": 0, "Test": 0}

#         self.epoch_num_steps = {"Train": 0, "Validation": 0, "Test": 0}
#         self.epoch_loss_sum = {"Train": 0.0, "Validation": 0.0, "Test": 0.0}

#         self.epoch_output = {"Train": [], "Validation": [], "Test": []}
#         self.epoch_real = {"Train": [], "Validation": [], "Test": []}

#     def forward(self, x):
#         """ """
#         outputs, num_samples = [], x.size(0)
#         h_t = torch.zeros(1, num_samples, self.hidden_layers1, dtype=torch.float32)
#         c_t = torch.zeros(1, num_samples, self.hidden_layers1, dtype=torch.float32)
#         h_t2 = torch.zeros(1, num_samples, self.hidden_layers2, dtype=torch.float32)
#         c_t2 = torch.zeros(1, num_samples, self.hidden_layers2, dtype=torch.float32)
#         h_t, c_t = self.lstm1(x, (h_t, c_t)) # initial hidden and cell states
#         h_t2, c_t2 = self.lstm2(h_t, (h_t2, c_t2)) # new hidden and cell states
#         outputs = self.linear(h_t2) # output from the last FC layer
#         outputs = torch.sigmoid(outputs)
#         return outputs[:,-1,:]

#     def configure_optimizers(self):
#         """ """
#         return torch.optim.Adam(self.parameters(), lr=self.lr_rate)

#     def log_epoch_metrics_and_loss(self, phase, print_cm=True, plot_cm=True):
#         # Log loss
#         epoch_loss = self.epoch_loss_sum[phase] / self.epoch_num_steps[phase]
#         self.log(f"{phase}Epoch/Loss", epoch_loss, prog_bar=True, logger=True)
#         self.epoch_loss_sum[phase] = 0.0

#         # Log metrics
#         for metric in self.metrics:
#             if isinstance(metric, BinaryConfusionMatrix):
#                 cm = metric(torch.cat(self.epoch_output[phase]), torch.cat(self.epoch_real[phase]))
#                 print(f"{phase}Epoch/CM\n", cm) if print_cm else None
#                 if plot_cm:
#                     import seaborn as sns
#                     import matplotlib.pyplot as plt
#                     plt.figure(figsize=(10, 7))
#                     ax = sns.heatmap(cm.numpy(), annot=True, fmt="d", cmap="Blues")
#                     ax.set_xlabel("Predicted labels")
#                     ax.set_ylabel("True labels")
#                     ax.set_title("Confusion Matrix")
#                     ax.set_xticks([0.5, 1.5])
#                     ax.set_yticks([0.5, 1.5])
#                     ax.xaxis.set_ticklabels(["Normal", "Attack"])
#                     ax.yaxis.set_ticklabels(["Normal", "Attack"])
#                     self.logger.experiment.add_figure(f"{phase}Epoch/CM", ax.get_figure(), global_step=self.epoch_global_number[phase])
#                     plt.close()
#             else:
#                 metric_name = metric.__class__.__name__.replace("Binary", "")
#                 metric_value = metric(torch.cat(self.epoch_output[phase]), torch.cat(self.epoch_real[phase])).detach()
#                 self.log(f"{phase}Epoch/{metric_name}", metric_value, prog_bar=True, logger=True)

#             metric.reset()

#         self.epoch_output[phase].clear()
#         self.epoch_real[phase].clear()

#         # Reset step count
#         self.epoch_num_steps[phase] = 0

#         # Increment epoch number
#         self.epoch_global_number[phase] += 1

#     def log_metrics(self, phase, y_pred, y, print_cm=False):
#         self.epoch_output[phase].append(y_pred.detach())
#         self.epoch_real[phase].append(y)

#         for metric in self.metrics:
#             if isinstance(metric, BinaryConfusionMatrix):
#                 print(f"{phase}/CM\n", metric(y_pred, y)) if print_cm else None
#             else:
#                 metric_name = metric.__class__.__name__.replace("Binary", "")
#                 metric_value = metric(y_pred, y)
#                 self.log(f"{phase}/{metric_name}", metric_value, prog_bar=True, logger=True)
    #TODO: puede ser necesario, sobreescribir el step de nebulamodel, meter binarycrossentropy
#     def step(self, batch, phase):
#         x, y = batch
#         logits = self(x)
#         loss = F.binary_cross_entropy(logits, y.unsqueeze(1).float())

#         # Get metrics for each batch and log them
#         self.log(f"{phase}/Loss", loss, prog_bar=True)
#         self.log_metrics(phase, logits.flatten().float(), y.flatten().float(), print_cm=False)

#         # Avoid memory leak when logging loss values
#         self.epoch_loss_sum[phase] += loss
#         self.epoch_num_steps[phase] += 1

#         return loss

#     def training_step(self, batch, batch_id):
#         """
#         Training step for the model.
#         Args:
#             batch:
#             batch_id:

#         Returns:
#         """
#         return self.step(batch, "Train")

#     def on_train_epoch_end(self):
#         self.log_epoch_metrics_and_loss("Train")

#     def validation_step(self, batch, batch_idx):
#         """
#         Validation step for the model.
#         Args:
#             batch:
#             batch_idx:

#         Returns:
#         """
#         return self.step(batch, "Validation")

#     def on_validation_epoch_end(self):
#         self.log_epoch_metrics_and_loss("Validation")

#     def test_step(self, batch, batch_idx):
#         """
#         Test step for the model.
#         Args:
#             batch:
#             batch_idx:

#         Returns:
#         """
#         return self.step(batch, "Test")

#     def on_test_epoch_end(self):
#         self.log_epoch_metrics_and_loss("Test")