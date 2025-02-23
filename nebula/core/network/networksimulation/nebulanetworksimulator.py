import asyncio
import logging
from nebula.core.network.networksimulation.networksimulator import NetworkSimulator
from nebula.core.utils.locker import Locker

class NebulaNS(NetworkSimulator):
    NETWORK_CONDITIONS = {
        100: {"bandwidth": "5Gbps", "delay": "5ms"},
        200: {"bandwidth": "2Gbps", "delay": "50ms"},
        300: {"bandwidth": "100Mbps", "delay": "200ms"},
        float("inf"): {"bandwidth": "10Mbps", "delay": "1000ms"},
    }
    
    def __init__(self, verbose=False):
        self._verbose = verbose
        self._network_conditions = self.NETWORK_CONDITIONS.copy()
        self._network_conditions_lock = Locker("network_conditions_lock", async_lock=True)
        
    async def set_thresholds(self, threshold : dict):
        pass

    def set_network_conditions(self, dest_addr, distance):
        pass
    
    def _set_network_condition_for_addr(self):
        pass
    
    def _set_network_condition_for_multicast(self):
        pass
    
    async def calculate_network_conditions(self, distance):
        def extract_number(value):
            import re
            match = re.match(r"([\d.]+)", value)
            if not match:
                raise ValueError(f"Formato inválido: {value}")
            return float(match.group(1))
        
        if self._verbose: logging.info(f"Calculating conditions for distance: {distance}")
        conditions = {}
        #TODO hacer copia del diccionario dentro de locks
        thresholds = sorted(self.network_conditions.keys())

        # Si la distancia es menor que el primer umbral, devolver la mejor condición
        if distance < thresholds[0]:
            return {
                "bandwidth": self.network_conditions[thresholds[0]]["bandwidth"],
                "delay": self.network_conditions[thresholds[0]]["delay"]
            }

        # Encontrar el tramo en el que se encuentra la distancia
        for i in range(len(thresholds) - 1):
            lower_bound = thresholds[i]
            upper_bound = thresholds[i + 1]

            if upper_bound == float("inf"):
                break

            if lower_bound <= distance < upper_bound:
                #logging.info(f"Bounds | lower: {lower_bound} | upper: {upper_bound}")
                lower_cond = self.network_conditions[lower_bound]
                upper_cond = self.network_conditions[upper_bound]

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
                #logging.info(f"Progress between the bounds: {progress}")

                # Interpolación lineal de valores
                bandwidth_value = lower_bandwidth_value - progress * (lower_bandwidth_value - upper_bandwidth_value)
                delay_value = lower_delay_value + progress * (upper_delay_value - lower_delay_value)

                # Reconstruir valores con unidades originales
                bandwidth = f"{round(bandwidth_value, 2)}{lower_bandwidth_unit}"
                delay = f"{round(delay_value, 2)}{delay_unit}"

                return {"bandwidth": bandwidth, "delay": delay}

        # Si la distancia es infinita, devolver el último valor
        return {
            "bandwidth": self.network_conditions[float("inf")]["bandwidth"],
            "delay": self.network_conditions[float("inf")]["delay"]
        }
        return conditions
    
    def clear_network_conditions(self):
        pass    