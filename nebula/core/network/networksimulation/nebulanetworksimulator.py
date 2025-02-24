import asyncio
import subprocess
import logging
from nebula.core.network.networksimulation.networksimulator import NetworkSimulator
from nebula.core.utils.locker import Locker
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.network.communications import CommunicationsManager

class NebulaNS(NetworkSimulator):
    NETWORK_CONDITIONS = {
        100: {"bandwidth": "5Gbps", "delay": "5ms"},
        200: {"bandwidth": "2Gbps", "delay": "50ms"},
        300: {"bandwidth": "100Mbps", "delay": "200ms"},
        float("inf"): {"bandwidth": "10Mbps", "delay": "100000ms"},
    }
    IP_MULTICAST = "239.255.255.250"
    
    def __init__(self, communication_manager: "CommunicationsManager", changing_interval, interface, verbose=False):
        self._cm = communication_manager
        self._refresh_interval = changing_interval
        self._node_interface = interface
        self._verbose = verbose
        self._network_conditions = self.NETWORK_CONDITIONS.copy()
        self._network_conditions_lock = Locker("network_conditions_lock", async_lock=True)
        self._current_network_conditions = {}
        self._running = False
        
    async def start(self):
        logging.info("🌐  Nebula Network Simulator starting...")
        self._running = True
        asyncio.create_task(self._change_network_conditions_based_on_distances()) 
    
    async def stop(self):
        self._running = False
        
    async def _change_network_conditions_based_on_distances(self):
        grace_time = self._cm.config.participant["mobility_args"]["grace_time_mobility"]
        if self._verbose: logging.info(f"Waiting {grace_time}s to start applying network conditions based on distances between devices")
        await asyncio.sleep(grace_time)
        
        while self._running:
            await asyncio.sleep(self._refresh_interval)
            if self._verbose: logging.info("Refresh | conditions based on distances...")
            current_connections = await self._cm.get_addrs_current_connections()
            try:
                for addr in current_connections:
                    distance = self._cm.connections[addr].get_neighbor_distance()
                    if distance is None:
                        # If the distance is not found, we skip the node
                        continue
                    conditions = await self._calculate_network_conditions(distance)
                    # Only update the network conditions if they have changed
                    if (addr not in self._current_network_conditions or self._current_network_conditions[addr] != conditions):
                        addr_ip = addr.split(":")[0]
                        self._set_network_condition_for_addr(self._node_interface, addr_ip, conditions["bandwidth"], conditions["delay"])
                        self._set_network_condition_for_multicast(self._node_interface, addr_ip, self.IP_MULTICAST, conditions["bandwidth"], conditions["delay"])
                        self._current_network_conditions[addr] = conditions
                    else:
                        logging.info("network conditions havent changed since last time")
            except KeyError:
                logging.exception(f"📍  Connection {addr} not found")
            except Exception:
                logging.exception("📍  Error changing connections based on distance")
        
    async def set_thresholds(self, thresholds : dict):
        async with self._network_conditions_lock:
            self._network_conditions = thresholds

    async def set_network_conditions(self, dest_addr, distance):
        conditions = await self._calculate_network_conditions(distance)
        self._set_network_condition_for_addr(self,
                                            interface=self._node_interface,
                                            network=dest_addr,
                                            bandwidth=conditions["bandwidth"],
                                            delay=conditions["delay"]
                                            )
        
        self._set_network_condition_for_multicast(self,
                                                  interface=self._node_interface,
                                                  src_network=dest_addr,
                                                  dst_network=self.IP_MULTICAST,
                                                  bandwidth=conditions["bandwidth"],
                                                  delay=conditions["delay"]
                                                  )
    
    def _set_network_condition_for_addr(
        self,
        interface="eth0",
        network="192.168.50.2",
        bandwidth="5Gbps",
        delay="0ms",
        delay_distro="10ms",
        delay_distribution="normal",
        loss="0%",
        duplicate="0%",
        corrupt="0%",
        reordering="0%",
    ):
        
        if self._verbose: 
            logging.info(f"🌐  Changing network conditions | Interface: {interface} | Network: {network} | Bandwidth: {bandwidth} | Delay: {delay} | Delay Distro: {delay_distro} | Delay Distribution: {delay_distribution} | Loss: {loss} | Duplicate: {duplicate} | Corrupt: {corrupt} | Reordering: {reordering}")   
        try:
            results = subprocess.run(
                [
                    "tcset",
                    str(interface),
                    "--network",
                    str(network) if network is not None else "",
                    "--rate",
                    str(bandwidth),
                    "--delay",
                    str(delay),
                    "--delay-distro",
                    str(delay_distro),
                    "--delay-distribution",
                    str(delay_distribution),
                    "--loss",
                    str(loss),
                    "--duplicate",
                    str(duplicate),
                    "--corrupt",
                    str(corrupt),
                    "--reordering",
                    str(reordering),
                    "--change",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            logging.exception(f"❗️  Network simulation error: {e}")
            return
    
    def _set_network_condition_for_multicast(
        self,
        interface="eth0",
        src_network="",
        dst_network="",
        bandwidth="5Gbps",
        delay="0ms",
        delay_distro="10ms",
        delay_distribution="normal",
        loss="0%",
        duplicate="0%",
        corrupt="0%",
        reordering="0%",
    ):
        if self._verbose: 
            logging.info(f"🌐  Changing multicast conditions | Interface: {interface} | Src Network: {src_network} | Bandwidth: {bandwidth} | Delay: {delay} | Delay Distro: {delay_distro} | Delay Distribution: {delay_distribution} | Loss: {loss} | Duplicate: {duplicate} | Corrupt: {corrupt} | Reordering: {reordering}")

        try:
            results = subprocess.run(
                [
                    "tcset",
                    str(interface),
                    "--src-network",
                    str(src_network),
                    "--dst-network",
                    str(dst_network),
                    "--rate",
                    str(bandwidth),
                    "--delay",
                    str(delay),
                    "--delay-distro",
                    str(delay_distro),
                    "--delay-distribution",
                    str(delay_distribution),
                    "--loss",
                    str(loss),
                    "--duplicate",
                    str(duplicate),
                    "--corrupt",
                    str(corrupt),
                    "--reordering",
                    str(reordering),
                    "--direction",
                    "incoming",
                    "--change",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            logging.exception(f"❗️  Network simulation error: {e}")
            return
    
    async def _calculate_network_conditions(self, distance):
        def extract_number(value):
            import re
            match = re.match(r"([\d.]+)", value)
            if not match:
                raise ValueError(f"Formato inválido: {value}")
            return float(match.group(1))
        
        if self._verbose: logging.info(f"Calculating conditions for distance: {distance}m")
        conditions = None
        async with self._network_conditions_lock:
            th = self._network_conditions.copy()
        
        thresholds = sorted(th.keys())

        # Si la distancia es menor que el primer umbral, devolver la mejor condición
        if distance < thresholds[0]:
            conditions = {
                "bandwidth": th[thresholds[0]]["bandwidth"],
                "delay": th[thresholds[0]]["delay"]
            }

        # Encontrar el tramo en el que se encuentra la distancia
        for i in range(len(thresholds) - 1):
            lower_bound = thresholds[i]
            upper_bound = thresholds[i + 1]

            if upper_bound == float("inf"):
                break

            if lower_bound <= distance < upper_bound:
                #logging.info(f"Bounds | lower: {lower_bound} | upper: {upper_bound}")
                lower_cond = th[lower_bound]
                upper_cond = th[upper_bound]

                # Extraer valores numéricos y unidades
                lower_bandwidth_value = extract_number(lower_cond["bandwidth"])
                upper_bandwidth_value = extract_number(upper_cond["bandwidth"])
                lower_bandwidth_unit = lower_cond["bandwidth"].replace(str(lower_bandwidth_value), "")
                upper_bandwidth_unit = upper_cond["bandwidth"].replace(str(upper_bandwidth_value), "")

                lower_delay_value = extract_number(lower_cond["delay"])
                upper_delay_value = extract_number(upper_cond["delay"])
                delay_unit = lower_cond["delay"].replace(str(lower_delay_value), "")

                # Calcular el progreso en el tramo (0 a 1)
                progress = (distance - lower_bound) / (upper_bound - lower_bound)
                if self._verbose: logging.info(f"Progress between the bounds: {progress}")

                # Interpolación lineal de valores
                bandwidth_value = lower_bandwidth_value - progress * (lower_bandwidth_value - upper_bandwidth_value)
                delay_value = lower_delay_value + progress * (upper_delay_value - lower_delay_value)

                # Reconstruir valores con unidades originales
                bandwidth = f"{round(bandwidth_value, 2)}{lower_bandwidth_unit}"
                delay = f"{round(delay_value, 2)}{delay_unit}"

                conditions = {"bandwidth": bandwidth, "delay": delay}

        # Si la distancia es infinita, devolver el último valor
        if not conditions:
            conditions = {
                "bandwidth": th[float("inf")]["bandwidth"],
                "delay": th[float("inf")]["delay"]
            }
        if self._verbose: logging.info(f"Network conditions: {conditions}")
        return conditions
    
    def clear_network_conditions(self, interface):
        if self._verbose: logging.info("🌐  Resetting network conditions")
        try:
            results = subprocess.run(
                ["tcdel", str(interface), "--all"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            logging.exception(f"❗️  Network simulation error: {e}")
            return   