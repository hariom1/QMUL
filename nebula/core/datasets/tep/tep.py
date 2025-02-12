# 
# This file is part of the fedstellar framework (see https://github.com/enriquetomasmb/fedstellar).
# Copyright (c) 2022 Enrique Tomás Martínez Beltrán.
#
import logging
import os
# import sys
# from math import floor
# from torch.utils.data import DataLoader, Subset, random_split
# from torchvision.datasets import MNIST, utils
# torch.multiprocessing.set_sharing_strategy("file_system")
import numpy as np
import torch
from torch.utils.data import Dataset
import urllib.request

from nebula.config.config import TRAINING_LOGGER
from nebula.core.datasets.nebuladataset import NebulaDataset

logging_training = logging.getLogger(TRAINING_LOGGER)

class TEP(Dataset):
    def __init__(self, is_train=False, time_series=False):
        self.is_train = is_train
        self.time_series = time_series

        self.download_link = 'http://perception.inf.um.es/tep/'
        # Path to data is "data" folder in the same directory as this file
        self.path_to_data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        self.files = ["X_train_ts.npy","y_train_ts.npy","X_val_ts.npy","y_val_ts.npy","X_test_ts.npy","y_test_ts.npy"]

        if not self.time_series:
            logging.info("We have chosen the option without time series")
            self.files = [x.replace("_ts", "") for x in self.files]

        os.makedirs(self.path_to_data, exist_ok=True)

        for file in self.files:
            logging.info(f"Verifying the file {file} has been downloaded")
            file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", file)
            if not os.path.exists(file_path):
                logging.info(f"{file} Does not exist")
                self.dataset_download()
                break

        self.data = []
        self.targets = []
        self.serial_numbers = []

        if is_train:
            aux = np.load(os.path.join(self.path_to_data, self.files[1]))
            logging.info(len(np.where(aux == 1)[0]))
            self.data, self.targets = torch.from_numpy(np.load(os.path.join(self.path_to_data, self.files[0]))), torch.from_numpy(np.load(os.path.join(self.path_to_data, self.files[1])))
            self.data = self.data.to(torch.float32)
            self.targets = self.targets.to(torch.float32)
            logging.info(f"Training {self.data.size()}")
        else:
            aux = np.load(os.path.join(self.path_to_data, self.files[5]))
            logging.info(len(np.where(aux == 1)[0]))
            self.data, self.targets = torch.from_numpy(np.load(os.path.join(self.path_to_data, self.files[4]))), torch.from_numpy(np.load(os.path.join(self.path_to_data, self.files[5])))
            self.data = self.data.to(torch.float32)
            self.targets = self.targets.to(torch.float32)
            logging.info(f"Dataset {self.data.size()}")

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, index):
        img, target = self.data[index], int(self.targets[index])
        return img, target

    def dataset_download(self):
        # download files
        for file in self.files:
            url = urllib.parse.urljoin(self.download_link, file)
            local_file = os.path.join(self.path_to_data, file)
            try:
                logging.info("Downloading %s a %s", url, local_file)
                urllib.request.urlretrieve(url, local_file)
                logging.info("File %s downloaded", file)
            except Exception as e:
                logging.error("Error downloading %s: %s", file, e)

class TEPDataset(NebulaDataset):
    def __init__(self,
        num_classes=10,
        partition_id=0, 
        partitions_number=1, 
        batch_size=32, 
        num_workers=4, 
        iid=True, 
        partition="dirichlet", 
        partition_parameter=0.5, 
        seed=42, 
        config=None,
        time_series =False
    ):
        self.time_series = time_series
        super().__init__(
            num_classes = num_classes, 
            partition_id = partition_id, 
            partitions_number = partitions_number, 
            batch_size = batch_size, 
            num_workers = num_workers, 
            iid = iid, 
            partition = partition, 
            partition_parameter = partition_parameter, 
            seed = seed, 
            config = config)

    def initialize_dataset(self):
        if self.train_set is None:
            self.train_set = self.load_tep_dataset(train=True)
        if self.test_set is None:
            self.test_set = self.load_tep_dataset(train=False)

        self.test_indices_map = list(range(len(self.test_set)))

        # Depending on the iid flag, generate a non-iid or iid map of the train set
        if self.iid:
            self.train_indices_map = self.generate_iid_map(self.train_set, self.partition, self.partition_parameter)
            self.local_test_indices_map = self.generate_iid_map(self.test_set, self.partition, self.partition_parameter)
        else:
            self.train_indices_map = self.generate_non_iid_map(self.train_set, self.partition, self.partition_parameter)
            self.local_test_indices_map = self.generate_non_iid_map(
                self.test_set, self.partition, self.partition_parameter
            )
        
    def load_tep_dataset(self, train=True):
        return TEP(train, self.time_series)
    
    def generate_non_iid_map(self, dataset, partition="dirichlet", partition_parameter=0.5):
        if partition == "dirichlet":
            partitions_map = self.dirichlet_partition(dataset, alpha=partition_parameter)
        elif partition == "percent":
            partitions_map = self.percentage_partition(dataset, percentage=partition_parameter)
        else:
            raise ValueError(f"Partition {partition} is not supported for Non-IID map")

        if self.partition_id == 0:
            self.plot_data_distribution(dataset, partitions_map)
            self.plot_all_data_distribution(dataset, partitions_map)

        return partitions_map[self.partition_id]

    def generate_iid_map(self, dataset, partition="balancediid", partition_parameter=2):
        if partition == "balancediid":
            partitions_map = self.balanced_iid_partition(dataset)
        elif partition == "unbalancediid":
            partitions_map = self.unbalanced_iid_partition(dataset, imbalance_factor=partition_parameter)
        else:
            raise ValueError(f"Partition {partition} is not supported for IID map")

        if self.partition_id == 0:
            self.plot_data_distribution(dataset, partitions_map)
            self.plot_all_data_distribution(dataset, partitions_map)
            
        return partitions_map[self.partition_id]
    
# class TEP(MNIST):
#     def __init__(self, sub_id, number_sub, root_dir, train=0, time_series=False):
#         super(MNIST, self).__init__(root_dir, transform=None, target_transform=None)
#         self.sub_id = sub_id
#         self.number_sub = number_sub
#         self.download_link = 'http://perception.inf.um.es/tep/'
#         self.files = ["X_train_ts.npy","y_train_ts.npy","X_val_ts.npy","y_val_ts.npy","X_test_ts.npy","y_test_ts.npy"]
#         self.train = train
#         self.root = root_dir
#         self.time_series = time_series
        
#         if not self.time_series:
#             logging.info("Hemos elegido la opción sin time series")
#             self.files = [x.replace("_ts", "") for x in self.files]

#         for file in self.files:
#             logging.info("Comprobando la existencia de: ", file)
#             if not os.path.exists(f'{self.root}/TEP/'+file):
#                 logging.info("*{} no existe".format(file))
#                 self.dataset_download()
#                 break

#         if self.train==0:
#             #logging.info(self.training_file)
#             data_file = self.training_file
#             aux = np.load(f'{self.root}/TEP/'+self.files[1])
#             logging.info(len(np.where(aux == 1)[0]))
#             self.data, self.targets = torch.from_numpy(np.load(f'{self.root}/TEP/'+self.files[0])), torch.from_numpy(np.load(f'{self.root}/TEP/'+self.files[1]))
#             self.data = self.data.to(torch.float32)
#             self.targets = self.targets.to(torch.float32)
#             logging.info("Entrenamiento", self.data.size())
#         elif self.train==1:
#             #data_file = self.training_file
#             aux = np.load(f'{self.root}/TEP/'+self.files[3])
#             logging.info(len(np.where(aux == 1)[0]))
#             self.data, self.targets = torch.from_numpy(np.load(f'{self.root}/TEP/'+self.files[2])), torch.from_numpy(np.load(f'{self.root}/TEP/'+self.files[3]))
#             self.data = self.data.to(torch.float32)
#             self.targets = self.targets.to(torch.float32)
#             logging.info("Entrenamiento", self.data.size())
#         else:
#             #data_file = self.test_file
#             aux = np.load(f'{self.root}/TEP/'+self.files[5])
#             logging.info(len(np.where(aux == 1)[0]))
#             self.data, self.targets = torch.from_numpy(np.load(f'{self.root}/TEP/'+self.files[4])), torch.from_numpy(np.load(f'{self.root}/TEP/'+self.files[5]))
#             self.data = self.data.to(torch.float32)
#             self.targets = self.targets.to(torch.float32)
#             logging.info("Entrenamiento", self.data.size())

#     def __getitem__(self, index):
#         img, target = self.data[index], int(self.targets[index])
#         return img, target

#     def dataset_download(self):
#         paths = [f'{self.root}/TEP/']
#         for path in paths:
#             if not os.path.exists(path):
#                 os.makedirs(path)

#         # download files
#         for file in self.files:
#             urllib.request.urlretrieve(
#                 os.path.join(f'{self.download_link}', file),
#                 os.path.join(f'{self.root}/TEP/', file))


# #######################################
# #    FederatedDataModule for WADI     #
# #######################################


# class TEPDataModule(LightningDataModule):
#     """
#     LightningDataModule of partitioned WADI.

#     Args:
#         sub_id: Subset id of partition. (0 <= sub_id < number_sub)
#         number_sub: Number of subsets.
#         batch_size: The batch size of the data.
#         num_workers: The number of workers of the data.
#         val_percent: The percentage of the validation set.
#     """

#     def __init__(
#             self,
#             sub_id=0,
#             number_sub=1,
#             batch_size=1024,
#             num_workers=4,
#             val_percent=0.1,
#             root_dir=None,
#             time_series = False
#     ):
#         super().__init__()
#         self.sub_id = sub_id
#         self.number_sub = number_sub
#         self.batch_size = batch_size
#         self.num_workers = num_workers
#         self.val_percent = val_percent
#         self.root_dir = root_dir
#         self.time_series = time_series
#         logging.info("Inicializando datos...")


#         self.train = TEP(sub_id=self.sub_id, number_sub=self.number_sub, root_dir=root_dir, train=0, time_series=self.time_series)
#         self.val = TEP(sub_id=self.sub_id, number_sub=self.number_sub, root_dir=root_dir, train=1, time_series=self.time_series)
#         self.test = TEP(sub_id=self.sub_id, number_sub=self.number_sub, root_dir=root_dir, train=2, time_series=self.time_series)
#         no_simulations = 10
#         #The total number of simulations in the dataset is 100
#         if self.number_sub > 100:
#             raise ("Too much partitions")
#         # 1 training simulation are 6840 samples: 380 * 18 classes (17 anomalies + normal class)
#         rows_train = no_simulations*380*18
#         # 1 training simulation are 1440 samples: 80 * 18 classes (17 anomalies + normal class)
#         rows_val = no_simulations*80*18
#         # 1 training simulation are 1800 samples: 100 * 18 classes (17 anomalies + normal class)
#         rows_test = no_simulations*100*18
#         # train set
#         trainset = self.train
#         tr_subset = Subset(
#             trainset, range(self.sub_id * rows_train, (self.sub_id + 1) * rows_train)
#         )
        
#         # val set
#         valset = self.val
#         rows_by_sub = floor(len(valset) / self.number_sub)
#         val_subset = Subset(
#             valset, range(self.sub_id * rows_val, (self.sub_id + 1) * rows_val)
#         )

#         # Test set
#         testset = self.test
#         rows_by_sub = floor(len(testset) / self.number_sub)
#         te_subset = Subset(
#             testset, range(self.sub_id * rows_test, (self.sub_id + 1) * rows_test)
#         )

#         # DataLoaders
#         self.train_loader = DataLoader(
#             tr_subset,
#             batch_size=self.batch_size,
#             shuffle=True,
#             num_workers=self.num_workers,
#         )
#         self.val_loader = DataLoader(
#             val_subset,
#             batch_size=self.batch_size,
#             shuffle=False,
#             num_workers=self.num_workers,
#         )
#         self.test_loader = DataLoader(
#             te_subset,
#             batch_size=self.batch_size,
#             shuffle=False,
#             num_workers=self.num_workers,
#         )
#         logging.info(
#             "Train: {} Val:{} Test:{}".format(
#                 len(tr_subset), len(val_subset), len(te_subset)
#             )
#         )

#     def train_dataloader(self):
#         """ """
#         return self.train_loader

#     def val_dataloader(self):
#         """ """
#         return self.val_loader

#     def test_dataloader(self):
#         """ """
#         return self.test_loader