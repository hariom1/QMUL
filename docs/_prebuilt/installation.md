# Installation

In this section, we will explain how to install the NEBULA platform.

## Prerequisites

-   For using NVIDIA GPUs, NVIDIA driver version >=525.60.13, and CUDA 12.1 (mandatory). https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html

## Obtaining NEBULA platform


You can obtain the source code from https://github.com/CyberDataLab/nebula

Or, if you happen to have git configured, you can clone the repository:

    git clone https://github.com/CyberDataLab/nebula.git

Now, you can move to the source directory:

    cd nebula

### Installing NEBULA platform

This command will install the required dependencies and set up the Docker containers if they haven't been installed yet.

    make install


To open a shell, use the following command:

    user:~$ source .venv/bin/activate

If you forget this command, you can simply type:

    make shell

### Checking the installation

Once the installation is finished, you can check by listing the version
of the NEBULA with the following command line:

    python app/main.py --version

## Running NEBULA

To run NEBULA, you can use the following command line:

    python app/main.py [PARAMS]

The first time you run the platform, the nebula-frontend docker image
will be built. This process can take a few minutes.

You can show the PARAMS using:

    python app/main.py --help

The frontend will be available at http://127.0.0.1:6060 by default, provided the port is available. If not, another port will be assigned automatically.

To change the default port of the frontend, you can use the following
command line:

    python app/main.py --webport [PORT]

To change the default port of the statistics endpoint, you can use the
following command line:

    python app/main.py --statsport [PORT]

## NEBULA Frontend

You can login with the following credentials:

    - User: admin
    - Password: admin

If not working the default credentials, send an email to [Enrique Tomás
Martínez Beltrán](mailto:enriquetomas@um.es) to get the credentials.

## Stop NEBULA

To stop NEBULA, you can use the following command line:

    python app/main.py --stop

Be careful, this command will stop all the containers related to NEBULA:
frontend, controller, and nodes.

## Possible issues during the installation or execution

If frontend is not working, check the logs in app/logs/frontend.log

If any of the following errors appear, take a look at the docker logs of
the nebula-frontend container:

docker logs nebula-frontend

------------------------------------------------------------------------

Network nebula_X Error failed to create network nebula_X: Error response
from daemon: Pool overlaps with other one on this address space

Solution: Delete the docker network nebula_X

> docker network rm nebula_X

------------------------------------------------------------------------

Error: Cannot connect to the Docker daemon at
unix:///var/run/docker.sock. Is the docker daemon running?

Solution: Start the docker daemon

> sudo dockerd

Solution: Enable the following option in Docker Desktop

Settings -> Advanced -> Allow the default Docker socket to be used

> ![Docker required options](static/docker-required-options.png)

------------------------------------------------------------------------

Error: Cannot connect to the Docker daemon at tcp://X.X.X.X:2375. Is the
docker daemon running?

Solution: Start the docker daemon

> sudo dockerd -H tcp://X.X.X.X:2375

------------------------------------------------------------------------

If frontend is not working, restart docker daemon

> sudo systemctl restart docker

------------------------------------------------------------------------

Error: Too many open files

Solution: Increase the number of open files

> ulimit -n 65536

Also, you can add the following lines to the file
/etc/security/limits.conf

> -   soft nofile 65536
> -   hard nofile 65536
