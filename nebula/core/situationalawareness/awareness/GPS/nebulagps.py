import asyncio
import logging
from nebula.core.situationalawareness.awareness.GPS.gpsmodule import GPSModule
import socket
from nebula.core.utils.locker import Locker

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nebula.core.situationalawareness.awareness.samodule import SAModule

class NebulaGPS(GPSModule):
    BROADCAST_IP = "255.255.255.255"    # Broadcast IP
    BROADCAST_PORT = 50001              # Poort used for GPS
    INTERFACE = "eth2"                  # Interface to avoid network conditions

    def __init__(self, sam: "SAModule", update_interval: float = 5.0):
        self._situational_awareness_module = sam
        self.update_interval = update_interval  # Frecuencia de emisión
        self.running = False
        self._node_locations = {}  # Diccionario para almacenar ubicaciones de nodos
        self._broadcast_socket = None
        self._nodes_location_lock = Locker("nodes_location_lock", async_lock=True)

    @property
    def sam(self):
        return self._situational_awareness_module
       
    async def start(self):
        """Inicia el servicio de GPS, enviando y recibiendo ubicaciones."""
        logging.info("Starting NebulaGPS service...")
        self.running = True

        # Crear socket de broadcast
        self._broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Enlazar socket en eth2 para recibir también datos
        self._broadcast_socket.bind(("", self.BROADCAST_PORT))

        # Iniciar tareas de envío y recepción
        asyncio.create_task(self._send_location_loop())
        asyncio.create_task(self._receive_location_loop())
        asyncio.create_task(self._notify_geolocs())

    async def stop(self):
        """Detiene el servicio de GPS."""
        #logging.info("Stopping NebulaGPS service...")
        self.running = False
        if self._broadcast_socket:
            self._broadcast_socket.close()
            self._broadcast_socket = None

    async def _send_location_loop(self):
        """Envia la geolocalización periódicamente por broadcast."""
        while self.running:
            latitude, longitude = await self.sam.get_geoloc()  # Obtener ubicación actual
            message = f"GPS-UPDATE {latitude} {longitude}"
            self._broadcast_socket.sendto(message.encode(), (self.BROADCAST_IP, self.BROADCAST_PORT))
            #logging.info(f"Sent GPS location: ({latitude}, {longitude})")
            await asyncio.sleep(self.update_interval)

    async def _receive_location_loop(self):
        """Escucha y almacena geolocalizaciones de otros nodos."""
        while self.running:
            try:
                data, addr = await asyncio.get_running_loop().run_in_executor(
                    None, self._broadcast_socket.recvfrom, 1024
                )
                message = data.decode().strip()
                if message.startswith("GPS-UPDATE"):
                    _, lat, lon = message.split()
                    self._nodes_location_lock.acquire_async()
                    self._node_locations[addr[0]] = (float(lat), float(lon))
                    self._nodes_location_lock.release_async()
                    #logging.info(f"Received GPS from {addr[0]}: {lat}, {lon}")
            except Exception as e:
                logging.error(f"Error receiving GPS update: {e}")

    async def _notify_geolocs(self):
        while True:
            await asyncio.sleep(self.update_interval)
            self._nodes_location_lock.acquire_async()
            geolocs = self._node_locations.copy()
            self._nodes_location_lock.release_async()
            if geolocs:
                await self.sam.cm.update_geolocalization(geolocs)
        