from typing import Annotated

from fastapi import FastAPI, File, UploadFile, status
from fastapi.responses import FileResponse

app = FastAPI()


# Config
@app.get("/config/", tags=["config"])
def get_config():
    return FileResponse("config.json")


@app.put("/config/", status_code=status.HTTP_201_CREATED, tags=["config"])
def set_config(
    config: Annotated[UploadFile, File()],
):
    return {"filename": config.filename}


@app.delete("/config/", tags=["config"])
def delete_config():
    return None


# Dataset
@app.get("/dataset/", tags=["dataset"])
def get_dataset():
    return FileResponse("dataset.h5")


@app.put("/dataset/", status_code=status.HTTP_201_CREATED, tags=["dataset"])
def set_dataset(
    dataset: Annotated[UploadFile, File()],
):
    return {
        "dataset_content_type": dataset.content_type,
    }


@app.delete("/dataset/", tags=["dataset"])
def delete_dataset():
    return None


# certs
@app.get("/certs/", tags=["certs"])
def get_certs():
    return FileResponse("cert.pem")


@app.put("/certs/", status_code=status.HTTP_201_CREATED, tags=["certs"])
def set_certs(
    certs: Annotated[UploadFile, File()],
):
    return {
        "certs_content_type": certs.content_type,
    }


@app.delete("/certs/", tags=["certs"])
def delete_certs():
    return None


# logs
@app.get("/get_logs/", tags=["logs"])
def run_node():
    return None


@app.delete("/get_logs/", tags=["logs"])
def delete_node():
    return None
