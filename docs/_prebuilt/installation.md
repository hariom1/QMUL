# **Installation**

In this section, we will explain how to install the NEBULA platform.

## **Obtaining the NEBULA platform**

You can obtain the source code from https://github.com/CyberDataLab/nebula

Or, if you happen to have git configured, you can clone the repository:

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">git clone https://github.com/CyberDataLab/nebula.git</span></code></pre>

Now, you can move to the source directory:

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">cd nebula</span></code></pre> 

### **Installing the NEBULA platform**

This command will install the required dependencies and set up the Docker containers if they haven't been installed yet.

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">make install</span></code></pre> 

To open a shell, use the following command:

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">source .venv/bin/activate</span></code></pre> 

If you forget this command, you can simply type:

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">make shell</span></code></pre>

If you want to use **NVIDIA GPUs**, you must install the **NVIDIA driver version 525.60.13 or later** and **CUDA 12.1 (mandatory)**. You can find installation instructions here:

https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html

Additionally, you need to install the **NVIDIA Container Toolkit** by following the instructions at:

https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html

If the shell is correctly deployed it should look like this:

<pre><code><span style="color: grey;">(nebula-dfl)</span><span style="color: blue;">user@host</span>:~$ <span style="color: green;">make shell</span></code></pre>

### **Checking the installation**

Once the installation is finished, you can check by listing the version
of the NEBULA with the following command line:

<pre><code><span style="color: grey;">(nebula-dfl)</span><span style="color: blue;">user@host</span>:~$ <span style="color: green;">python app/main.py --version</span></code></pre>

## **Running NEBULA**

To run NEBULA, you can use the following command line:

<pre><code><span style="color: grey;">(nebula-dfl)</span><span style="color: blue;">user@host</span>:~$ <span style="color: green;">python app/main.py [PARAMS]</span></code></pre>

The first time you run the platform, the nebula-frontend docker image
will be built. This process can take a few minutes.

You can show the PARAMS using:

<pre><code><span style="color: grey;">(nebula-dfl)</span><span style="color: blue;">user@host</span>:~$ <span style="color: green;">python app/main.py --help</span></code></pre>

The frontend will be available at http://127.0.0.1:6060 by default, if the provided port is available. If not, another port will be assigned automatically.

To change the default port of the frontend, you can use the following
command line:

<pre><code><span style="color: grey;">(nebula-dfl)</span><span style="color: blue;">user@host</span>:~$ <span style="color: green;">python app/main.py --webport [PORT]</span></code></pre>

To change the default port of the statistics endpoint, you can use the
following command line:

<pre><code><span style="color: grey;">(nebula-dfl)</span><span style="color: blue;">user@host</span>:~$ <span style="color: green;">python app/main.py --statsport [PORT]</span></code></pre>

## **NEBULA Frontend**

You can login with the following credentials:

    - User: admin
    - Password: admin

If not working the default credentials, send an email to [Enrique Tomás
Martínez Beltrán](mailto:enriquetomas@um.es) to get the credentials.

## **Stop NEBULA**

To stop NEBULA, you can use the following command line:

<pre><code><span style="color: grey;">(nebula-dfl)</span><span style="color: blue;">user@host</span>:~$ <span style="color: green;">python app/main.py --stop</span></code></pre>

Be careful, this command will stop all the containers related to NEBULA:
frontend, controller, and nodes.

## **Possible issues during the installation or execution**

If frontend is not working, check the logs in app/logs/frontend.log

If any of the following errors appear, take a look at the docker logs of
the nebula-frontend container:

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">docker logs user_nebula-frontend</span></code></pre>

------------------------------------------------------------------------

Network nebula_X Error failed to create network nebula_X: Error response
from daemon: Pool overlaps with other one on this address space

Solution: Delete the docker network nebula_X

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">docker network rm nebula_X</span></code></pre>

------------------------------------------------------------------------

Error: Cannot connect to the Docker daemon at
unix:///var/run/docker.sock. Is the docker daemon running?

Solution: Start the docker daemon

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">sudo dockerdX</span></code></pre>

Solution: Enable the following option in Docker Desktop

Settings -> Advanced -> Allow the default Docker socket to be used

> ![Docker required options](static/docker-required-options.png)

------------------------------------------------------------------------

Error: Cannot connect to the Docker daemon at tcp://X.X.X.X:2375. Is the
docker daemon running?

Solution: Start the docker daemon

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">sudo dockerd -H tcp://X.X.X.X:2375</span></code></pre>

------------------------------------------------------------------------

If frontend is not working, restart docker daemon

<pre><code><span style="color: blue;">user@host</span>:~$ <span style="color: green;">sudo systemctl restart docker</span></code></pre>

------------------------------------------------------------------------

Error: Too many open files

Solution: Increase the number of open files

> ulimit -n 65536

Also, you can add the following lines to the file
/etc/security/limits.conf

> -   soft nofile 65536
> -   hard nofile 65536
