#!/bin/sh
apt-get update
apt-get install -y tzdata
ln -fs /usr/share/zoneinfo/Europe/Madrid /etc/localtime
dpkg-reconfigure -f noninteractive tzdata

# Install curl and network tools
apt-get install -y curl net-tools iproute2 iputils-ping

# Update alternatives to make Python 3.11 the default
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 2
update-alternatives --install /usr/bin/python python /usr/bin/python3 1

# Install gcc and git
apt-get update
apt-get install -y build-essential gcc g++ clang git make cmake

curl -fsSL https://astral.sh/uv/install.sh | sh

uv python install 3.11.7

uv python pin 3.11.7

uv sync --group core

