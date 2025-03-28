import os
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

app = FastAPI()

CERTS_FOLDER = "./app/certs/"
CONFIG_FOLDER = "./app/config/"
LOGS_FOLDER = "./app/logs/"
METRICS_FOLDER = "./app/logs/metrics/"

CONFIG_FILE_COUNT = 1
DATASET_FILE_COUNT = 2


def _find_x_files(folder: str, extension: str = ".json"):
    """
    Find all json files in a folder

    Args:
        folder (str): Path to the folder to be checked
    """
    archivos_json = []
    for file_name in os.listdir(folder):
        if file_name.endswith(extension):
            archivos_json.append(os.path.join(folder, file_name))
    return archivos_json


def _LFI_sentry(path: str):
    """
    Basic anti path traversal sentry. TODO: improve, it shouldn't be necessary to check for all these characters manually
    It also checks if the folder exists

    Args:
        path (str): Path to be checked

    Returns:
        bool: True if the path is malicious, False if it's safe and exists
    """
    return (
        not os.path.exists(CONFIG_FOLDER + path)
        or path == ""
        or ".." in path
        or "/" in path
        or "\\" in path
        or "~" in path
        or "*" in path
        or "?" in path
        or ":" in path
        or "<" in path
        or ">" in path
        or "|" in path
        or '"' in path
        or "'" in path
        or "`" in path
        or "$" in path
        or "%" in path
        or "&" in path
        or "!" in path
        or "{" in path
        or "}" in path
        or "[" in path
        or "]" in path
        or "@" in path
        or "#" in path
        or "+" in path
        or "=" in path
        or ";" in path
        or "," in path
        or " " in path
        or "\t" in path
        or "\n" in path
        or "\r" in path
        or "\f" in path
        or "\v" in path
    )


# Config
@app.get("/config/", tags=["config"])
def get_config(
    path: str,
):
    """
    Get the config file

    Args:
        path (str): Name of the folder (nebula+DFL+timestamp) where the config file is located

    Returns:
        FileResponse: The config file"""
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        json_files = _find_x_files(CONFIG_FOLDER + path + "/")
        if len(json_files) != CONFIG_FILE_COUNT:
            # raise Exception("There should be only one json file in the folder")
            raise HTTPException(status_code=404, detail="Item not found")
        else:
            file_name = json_files.pop()
            with open(file_name) as file:
                return FileResponse(file)


@app.put("/config/", status_code=status.HTTP_201_CREATED, tags=["config"], response_model=dict)
def set_config(
    config: Annotated[UploadFile, File()],
    path: str,
) -> dict:
    """
    Set the config file

    Args:
        config (UploadFile): File to be written
        path (str): Name of the folder where the config file is located. Path should be $scenraio_args.name

    Returns:
        dict: Name of the written file

    """
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")

    else:
        os.makedirs(CONFIG_FOLDER + path, exist_ok=True)
        with open(CONFIG_FOLDER + path + "/" + config.filename, "wb") as file:
            file.write(config.file.read())
            return {"filename": config.filename}


@app.delete("/config/", tags=["config"], response_model=dict)
def delete_config(
    path: str,
) -> dict:
    """
    Delete the config file

    Args:
        path (str): Name of the folder (nebula+DFL+timestamp) where the config file is located

    Returns:
        dict: Name of the deleted file
    """
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")

    # check if there is a json file in the folder
    json_files = _find_x_files(CONFIG_FOLDER + path + "/")
    if len(json_files) != CONFIG_FILE_COUNT:
        # raise Exception("There should be only one json file in the folder")
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        file_name = json_files.pop()
        os.remove(file_name)
        return {"filename": file_name}


# Dataset
@app.get("/dataset/", tags=["dataset"], response_model=list)
def get_dataset(
    path: str,
) -> list:
    """
    Get the dataset file

    Args:
        path (str): Name of the folder (nebula+DFL+timestamp) where the dataset file is located

    Returns:
        list[FileResponse]: List of the two dataset files in the folder
    """

    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")

    h5_files = _find_x_files(CONFIG_FOLDER + path + "/", ".h5")
    if len(h5_files) != DATASET_FILE_COUNT:
        # raise Exception("There should be only two h5 file in the folder")
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        file_response = []
        for file_name in h5_files:
            with open(file_name) as file:
                file_response.append(FileResponse(file))
            return file_response


@app.put("/dataset/", status_code=status.HTTP_201_CREATED, tags=["dataset"])
def set_dataset(
    dataset: Annotated[UploadFile, File()],
    dataset_p: Annotated[UploadFile, File()],
    path: str,
) -> list:
    """
    Set the dataset file

    Args:
        dataset (UploadFile): File to be written
        path (str): Name of the folder (nebula+DFL+timestamp) where the dataset file is located

    Returns:
        dict: Name of the written file
    """
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")

    else:
        try:
            os.makedirs(CONFIG_FOLDER + path, exist_ok=True)
            return_files = []
            with open(CONFIG_FOLDER + path + "/" + dataset.filename, "wb") as file:
                file.write(dataset.file.read())
                return_files.append(dataset.filename)
            with open(CONFIG_FOLDER + path + "/" + dataset_p.filename, "wb") as file:
                file.write(dataset_p.file.read())
                return_files.append(dataset_p.filename)
        except OSError:
            pass
        return return_files


@app.delete("/dataset/", tags=["dataset"])
def delete_dataset(
    path: str,
):
    """
    Delete the dataset file

    Args:
        path (str): Name of the folder (nebula+DFL+timestamp) where the dataset file is located

    Returns:
        dict: Name of the deleted file"""
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")

    # check if there is a json file in the folder
    json_files = _find_x_files(CONFIG_FOLDER + path + "/", ".h5")
    if len(json_files) != DATASET_FILE_COUNT:
        # raise Exception("There should be only one json file in the folder")
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        removed_files = {}
        for file_name in json_files:
            os.remove(file_name)
            removed_files[file_name] = "deleted"
        return removed_files


# certs
@app.get("/certs/", tags=["certs"])
def get_certs():
    """
    Get the certs file

    Returns:
        FileResponse: The certs file
    """
    json_files = _find_x_files(CERTS_FOLDER + "/", ".cert")
    return_files = []
    for file_name in json_files:
        with open(file_name) as file:
            return_files.append(FileResponse(file))
    return return_files


@app.put("/certs/", status_code=status.HTTP_201_CREATED, tags=["certs"])
def set_cert(
    cert: Annotated[UploadFile, File()],
) -> dict:
    """
    Set the certs file

    Args:
        cert (UploadFile): File to be written

    Returns:
        dict: Name of the written file"""
    with open(CERTS_FOLDER + cert.filename, "wb") as file:
        file.write(cert.file.read())
        return {"filename": cert.filename}


@app.delete("/certs/", tags=["certs"])
def delete_certs():
    """
    Delete the ALL certs file

    Returns:
        dict: Name of the deleted file
    """
    json_files = _find_x_files(CERTS_FOLDER + "/", ".cert")
    removed_files = {}
    for file_name in json_files:
        os.remove(file_name)
        removed_files[file_name] = "deleted"
    return removed_files


# Logs
@app.get("/get_logs/", tags=["logs"])
def get_logs(
    path: str,
):
    """
    Get the log file

    Args:
        path (str): Name of the folder (nebula+DFL+timestamp) where the log file is located

    Returns:
        FileResponse: The log file
    """
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        log_files = _find_x_files(LOGS_FOLDER + path + "/", ".log")
        if not log_files:
            raise HTTPException(status_code=404, detail="Log file not found")
        log_file = min(log_files, key=lambda x: len(os.path.basename(x)))
        with open(log_file) as file:
            return FileResponse(file)


@app.delete("/get_logs/", tags=["logs"])
def delete_logs(
    path: str,
) -> dict:
    """
    Delete the log file

    Args:
        path (str): Name of the folder (nebula+DFL+timestamp) where the log file is located

    Returns:
        dict: Name of the deleted file
    """
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        log_files = _find_x_files(LOGS_FOLDER + path + "/", ".log")
        if not log_files:
            raise HTTPException(status_code=404, detail="Log file not found")
        log_file = min(log_files, key=lambda x: len(os.path.basename(x)))
        os.remove(log_file)
        return {"filename": log_file}


@app.get("/get_logs/debug/", tags=["logs"])
def get_debug_logs(
    path: str,
):
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        log_files = _find_x_files(LOGS_FOLDER + path + "/", "debug.log")
        if not log_files:
            raise HTTPException(status_code=404, detail="Log file not found")
        with open(log_files.pop()) as file:
            return FileResponse(file)


@app.delete("/get_logs/debug/", tags=["logs"])
def delete_debug_logs(
    path: str,
) -> dict:
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        log_files = _find_x_files(LOGS_FOLDER + path + "/", "debug.log")
        if not log_files:
            raise HTTPException(status_code=404, detail="Log file not found")
        log_file = log_files.pop()
        os.remove(log_file)
        return {"filename": log_file}


@app.get("/get_logs/error/", tags=["logs"])
def get_error_logs(
    path: str,
):
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        log_files = _find_x_files(LOGS_FOLDER + path + "/", "error.log")
        if not log_files:
            raise HTTPException(status_code=404, detail="Log file not found")
        with open(log_files.pop()) as file:
            return FileResponse(file)


@app.delete("/get_logs/error/", tags=["logs"])
def delete_error_logs(
    path: str,
) -> dict:
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        log_files = _find_x_files(LOGS_FOLDER + path + "/", "error.log")
        if not log_files:
            raise HTTPException(status_code=404, detail="Log file not found")
        log_file = log_files.pop()
        os.remove(log_file)
        return {"filename": log_file}


@app.get("/get_logs/training/", tags=["logs"])
def get_train_logs(
    path: str,
):
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        log_files = _find_x_files(LOGS_FOLDER + path + "/", "training.log")
        if not log_files:
            raise HTTPException(status_code=404, detail="Log file not found")
        with open(log_files.pop()) as file:
            return FileResponse(file)


@app.delete("/get_logs/training/", tags=["logs"])
def delete_train_logs(
    path: str,
) -> dict:
    # check for path traversal
    if _LFI_sentry(path):
        raise HTTPException(status_code=404, detail="Item not found")
    else:
        log_files = _find_x_files(LOGS_FOLDER + path + "/", "training.log")
        if not log_files:
            raise HTTPException(status_code=404, detail="Log file not found")
        log_file = log_files.pop()
        os.remove(log_file)
        return {"filename": log_file}


# Metrics
@app.get("/metrics/", tags=["metrics"])
def get_metrics():
        # check for path traversal

    log_files = _find_x_files(METRICS_FOLDER, "")
    if not log_files:
        raise HTTPException(status_code=404, detail="Log file not found")
    return_files = []
    for file_name in log_files:
        with open(file_name) as file:
            return_files.append(FileResponse(file))

