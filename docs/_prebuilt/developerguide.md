# Developer Guide

This guide is designed to help developers understand and contribute to the project. It provides detailed instructions on navigating the codebase, and implementing new features. Whether you're looking to fix bugs, add enhancements, or better understand the architecture, this guide will walk you through the essential processes and best practices for development.


## NEBULA Frontend

This section explains the structure of the frontend and provides instructions on how to add new parameters or sections.

### Frontend Structure  

- **/nebula/**
  - pycache/
  - addons/
  - config/
  - core/
  - **frontend/**
    - __pycache__/
    - **config/**
      - `__init__.py`
      - `nebula`
      - `participant.json.example`
    - **databases/**
      - `participants.db`
      - `notes.db`
      - `scenarios.db`
      - `scenarios.db-shm`
      - `scenarios.db-wal`
      - `users.db`
    - **static/**
    - **templates/**
      - `401.html`
      - `403.html`
      - `404.html`
      - `405.html`
      - `413.html`
      - `admin.html`
      - `dashboard.html`
      - `deployment.html`
      - `index.html`
      - `layout.html`
      - `monitor.html`
      - `private.html`
      - `statistics.html`
    - `__init__.py`
    - `app.py`
    - `database.py`
    - `Dockerfile`
    - `start_services.sh`

The frontend is organized within the `frontend/` directory. Key files and folders include:  

- `config/` → Contains the **participant.json.example**, the default structure for the paramteres passed to each participant.
- `databases/` → Contains the different databases for NEBULA   
- `static/` → Holds static assets (CSS, images, JS, etc.).  
- `templates/` → Contains HTML templates. Focus on **deployment.html** 

### Adding a New Parameter  

Define the new parameter in the **participant.json.example** file. Only create a new field if necessary

```json
{
    "scenario_args": {
      "name": "",
      "start_time": "",
      "federation": "DFL",
      "rounds": 10,
      "deployment": "process",
      "controller": "127.0.0.1:5000",
      "random_seed": 42,
      "n_participants": 0,
      /* New parameter in each setting */
      "new_parameter_key" : "new_parameter_value",
      "config_version": "development"
    },
    /* Add a new_field if necessary */
    "new_field": {
        "new_parameter_key" : "new_parameter_value"
    }
}
```

### Define the parameter on the **deployment.html**
For example, let's assume you want to implement a new attack type. Search for the section where attacks are defined and add the new attack option, as well as the new parameter for the attack. Below is an example of how to add the attack and its associated parameter.

```html
<div class="form-group row container-shadow tiny grey">
    <h5 class="step-number">Robustness <i class="fa fa-shield"></i>
        <input type="checkbox" tyle="display: none;">
        <label for="robustness-lock" class="icon-container" style="float: right;">
            <i class="fa fa-lock"></i>
        </label>
    </h5>
    <h5 class="step-title">Attack Type</h5>
    <div class="form-check form-check-inline">
        <select class="form-control" id="poisoning-attack-select" name="poisoning-attack">
            <option selected>No Attack</option>
            <option>New Attack</option> <!-- Add this -->
        </select>
        <h5 id="poisoned-participant-title" class="step-title">
            % Malicious participants
        </h5>
        <div class="form-check form-check-inline" style="display: none;" id="poisoned-participant-percent-container">
            <input type="number" class="form-control" id="poisoned-participant-percent"
                placeholder="% malicious participants" min="0" value="0">
                <select class="form-control" id="malicious-participants-select" name="malicious-participants-select">
                <option selected>Percentage</option>
                <option>Manual</option>
            </select>
        </div>
        <h5 id="poisoned-participant-title" class="step-title">
            % Malicious participants
        </h5>
        <div class="form-check form-check-inline" style="display: none;" id="poisoned-participant-percent-container">
            <input type="number" class="form-control" id="poisoned-participant-percent"
                placeholder="% malicious participants" min="0" value="0">
        </div>
        <h5 id="new-parameter-title" class="step-title"> <!-- Add this -->
            New parameter
        </h5>
        <div class="form-check form-check-inline" style="display: none;" id="new-parameter-container">
            <input type="number" class="form-control" id="new-parameter-value"
                placeholder="new parameter value" min="0" value="0"> 
        </div>
    </div>
</div>
```

To receive the parameter in nebula/scenarios.py. You need to modify the Scenario class to accept the new parameter.

```python
class Scenario:
    def __init__(
        self,
        scenario_title,
        scenario_description,
        new_paramater, # <--- Add this
    ):
        self.scenario_title = scenario_title
        self.scenario_description = scenario_description
        self.new_parameter = new_parameter # <--- Add this
```

Now you must save the parameter in the **participant configuration**.

The participant configuration files are located in the **/app/config/ directory**. You'll need to ensure the new parameter is added to the participant's JSON file.

???+ info "Code example"
    ```python
        class ScenarioManagement:
        def __init__(self, scenario, user=None):
            # Save participant settings
            for participant in self.scenario.participants:
                participant_config = self.scenario.participants[participant]
                participant_file = os.path.join(self.config_dir, f"participant_{participant_config['id']}.json")
                os.makedirs(os.path.dirname(participant_file), exist_ok=True)
                shutil.copy(
                    os.path.join(
                        os.path.dirname(__file__),
                        "./frontend/config/participant.json.example",
                    ),
                    participant_file,
                )
                os.chmod(participant_file, 0o777)
                with open(participant_file) as f:
                    participant_config = json.load(f)

                participant_config["network_args"]["ip"] = participant_config["ip"]
                participant_config["network_args"]["port"] = int(participant_config["port"])
                # In case you are adding a parameter to a previously defined functionality
                participant_config["data_args"]["new_parameter"] = self.scenario.new_parameter
                # In case you are creating a new functionality
                participant_config["new_field"]["new_parameter"] = self.scenario.new_parameter
    ```

## NEBULA Backend

To view the documentation of functions in more detail you must go to the **NEBULA API Reference**

### Backend Structure

This guide explains the structure of the **Backend**, outlining its components and their functionalities. 

- **/nebula/**
  - **addons/**
    - **attacks/**
    - **blockchain/**
    - **trustworthiness/**
    - **waf/**
  - **core/**
    - **aggregation/**
    - **datasets/**
    - **models/**
    - **network/**
    - **pb/**
    - **training/**
    - **utils/**
    - `engine.py`
    - `eventmanager.py`
    - `role.py`
  - `controller.py`
  - `participant.py`
  - `scenarios.py`
  - `utils.py`

## Addons

The **addons/** directory contains extended functionalities that can be integrated into the core participant operations.

### **`attacks/`**
- A module to simulate attacks.
- Primarily used for security purposes, such as adversarial attacks in machine learning or penetration testing.

### **`blockchain/`**
- Integrates blockchain technology into the participant.
- Could be used for decentralized storage, transactions, or security.

### **`trustworthiness/`**
- Focuses on evaluating the trustworthiness and reliability of the participant.
- Assess the performance, security, or ethical reliability of participants.

### **`waf/`**
- Stands for **Web Application Firewall**.
- Protects the web applications by filtering and monitoring HTTP traffic for potential threats.

## Core

The **core/** directory contains the essential components for the participant's operation.

### **`aggregation/`**
- Manages the aggregation of data from the different nodes

### **`datasets/`**
- Contains functionalities for managing datasets, including loading and preprocessing data.

### **`models/`**
- Defines the architecture and functionality of machine learning models.
- Handles model-related logic such as training, evaluation, and saving.

### **`network/`**
- Manages network-related operations within the participant.
- Responsible for communication between participants.

### **`pb/`**
- **Protocol Buffers**, a method for serializing structured data.
- Used for efficient communication or storing model data in a compact format.

### **`training/`**
- Contains the logic for training models, including optimization, evaluation, and tuning.
- Facilitates the machine learning lifecycle.

### **`utils/`**
- Contains utility functions or helper methods used across the participant.
- Include file handling, logging, or other repetitive tasks that simplify the main codebase.

## Files

### **`engine.py`**
- Is the main engine, the one that orchestrates the participant communications, trining, behaviour, etc.

### **`eventmanager.py`**
- Handles events or notifications within the participant.
- Used for managing triggers, logging, or participant alerts.

### **`role.py`**
- Defines the participant roles of the platform

## Standalone Scripts

These scripts may serve as the entry points or high-level controllers for specific tasks.

### **`controller.py`**
- Manages the flow of operations within the participant.
- Likely used for coordinating tasks, controlling user interactions, or managing subprocesses.

### **`participant.py`**
- Represents a participant in a distributed or decentralized network.
- Likely manages tasks such as computations, data handling, or communication with other participants.

### **`scenarios.py`**
- Defines different use cases or simulation scenarios.
- Could be used for testing, training, or running the participant under different conditions.

### **`utils.py`**
- Contains utility functions or helper methods used throughout the participant.
- Includes common operations that simplify development and maintenance.

### Adding new Datasets

If you want to add a new Dataset you can implement this in 2 ways on the folder **/nebula/core/datasets/** ***new_dataset/new_dataset.py***

#### 1. Import the Dataset from Torchvision

```python
class CIFAR10Dataset(NebulaDataset):
    def __init__(
        self,
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
    ):
        super().__init__(
            num_classes=num_classes,
            partition_id=partition_id,
            partitions_number=partitions_number,
            batch_size=batch_size,
            num_workers=num_workers,
            iid=iid,
            partition=partition,
            partition_parameter=partition_parameter,
            seed=seed,
            config=config,
        )

    def initialize_dataset(self):
        # Load CIFAR10 train dataset
        if self.train_set is None:
            self.train_set = self.load_cifar10_dataset(train=True)
        if self.test_set is None:
            self.test_set = self.load_cifar10_dataset(train=False)

        # All nodes have the same test set (indices are the same for all nodes)
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

        print(f"Length of train indices map: {len(self.train_indices_map)}")
        print(f"Lenght of test indices map (global): {len(self.test_indices_map)}")
        print(f"Length of test indices map (local): {len(self.local_test_indices_map)}")

    def load_cifar10_dataset(self, train=True):
        mean = (0.4914, 0.4822, 0.4465)
        std = (0.2471, 0.2435, 0.2616)
        apply_transforms = transforms.Compose([
            transforms.RandomCrop(32, padding=4),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize(mean, std, inplace=True),
        ])
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        return CIFAR10(
            data_dir,
            train=train,
            download=True,
            transform=apply_transforms,
        )
```

#### 2. Import the Dataset from your own

