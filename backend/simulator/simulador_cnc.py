"""
FabriSense - Simulador CNC
Simula 8 máquinas CNC enviando telemetría por MQTT.

Controles de teclado (en la terminal donde corre el script):
  F  → Inyectar falla en máquina aleatoria (sube temp + vibración)
  R  → Recuperar máquina en falla (vuelve a valores normales)
  U  → Marcar orden urgente en máquina aleatoria
  P  → Provocar paro en máquina aleatoria
  Q  → Salir

Requisitos:
  pip install paho-mqtt

Uso:
  python simulador_cnc.py
  python simulador_cnc.py --broker 192.168.1.x --tenant mi-fabrica
"""

import argparse
import json
import msvcrt
import random
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("ERROR: Instala paho-mqtt → pip install paho-mqtt")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

TENANT_ID = "demo-fabrica"
BROKER_HOST = "localhost"
BROKER_PORT = 1883
INTERVALO_SEGUNDOS = 5

MAQUINAS = [
    "CNC-01", "CNC-02", "CNC-03", "CNC-04",
    "CNC-05", "CNC-06", "CNC-07", "CNC-08",
]

# Rangos normales por parámetro
NORMAL = {
    "temperatura": (45.0, 72.0),   # °C
    "vibracion":   (0.5,  3.5),    # mm/s RMS
    "rpm":         (800,  3200),    # RPM
}

# Rangos de falla
FALLA = {
    "temperatura": (95.0, 130.0),
    "vibracion":   (8.0,  18.0),
    "rpm":         (200,   500),
}


class Estado(str, Enum):
    OPERANDO = "operando"
    FALLA    = "falla"
    PARADO   = "parado"
    URGENTE  = "urgente"


# ---------------------------------------------------------------------------
# Modelo de máquina
# ---------------------------------------------------------------------------

@dataclass
class Maquina:
    id: str
    estado: Estado = Estado.OPERANDO
    orden_urgente: str | None = None
    _falla_activa: bool = field(default=False, repr=False)

    def lectura(self) -> dict:
        if self.estado == Estado.PARADO:
            return {
                "maquina_id": self.id,
                "timestamp": _ts(),
                "estado": self.estado,
                "temperatura": 0.0,
                "vibracion": 0.0,
                "rpm": 0,
                "orden_urgente": self.orden_urgente,
            }

        rangos = FALLA if self._falla_activa else NORMAL
        return {
            "maquina_id": self.id,
            "timestamp": _ts(),
            "estado": self.estado,
            "temperatura": round(random.uniform(*rangos["temperatura"]), 2),
            "vibracion":   round(random.uniform(*rangos["vibracion"]),   3),
            "rpm":         random.randint(*rangos["rpm"]),
            "orden_urgente": self.orden_urgente,
        }

    def inyectar_falla(self):
        self._falla_activa = True
        self.estado = Estado.FALLA
        self.orden_urgente = None

    def recuperar(self):
        self._falla_activa = False
        self.estado = Estado.OPERANDO

    def paro(self):
        self._falla_activa = False
        self.estado = Estado.PARADO

    def orden_urgente_set(self, orden_id: str):
        self.orden_urgente = orden_id
        if self.estado == Estado.OPERANDO:
            self.estado = Estado.URGENTE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _color(texto: str, codigo: int) -> str:
    return f"\033[{codigo}m{texto}\033[0m"


def _estado_color(estado: Estado) -> str:
    colores = {
        Estado.OPERANDO: 32,   # verde
        Estado.FALLA:    31,   # rojo
        Estado.PARADO:   33,   # amarillo
        Estado.URGENTE:  35,   # magenta
    }
    return _color(estado.value.upper(), colores[estado])


def _maquina_aleatoria(maquinas: dict[str, Maquina], filtro=None) -> Maquina | None:
    pool = [m for m in maquinas.values() if filtro is None or filtro(m)]
    return random.choice(pool) if pool else None


# ---------------------------------------------------------------------------
# Loop de publicación MQTT
# ---------------------------------------------------------------------------

def loop_publicacion(client: mqtt.Client, maquinas: dict[str, Maquina],
                     tenant: str, stop: threading.Event):
    while not stop.is_set():
        for maquina in maquinas.values():
            topic = f"fabrisense/{tenant}/maquina/{maquina.id}/datos"
            payload = maquina.lectura()
            client.publish(topic, json.dumps(payload), qos=0)
        _imprimir_estado(maquinas)
        stop.wait(INTERVALO_SEGUNDOS)


# ---------------------------------------------------------------------------
# Consola de estado
# ---------------------------------------------------------------------------

def _imprimir_estado(maquinas: dict[str, Maquina]):
    print("\033[2J\033[H", end="")  # limpiar pantalla
    print(_color("═" * 60, 36))
    print(_color("  FabriSense CNC Simulator  │  MQTT localhost:1883", 36))
    print(_color("═" * 60, 36))
    print(f"  {'Máquina':<10} {'Estado':<14} {'Temp°C':>7} {'Vib mm/s':>9} {'RPM':>6}")
    print("  " + "─" * 52)

    for m in maquinas.values():
        d = m.lectura()
        urgente = " ⚡ URGENTE" if m.orden_urgente else ""
        print(
            f"  {d['maquina_id']:<10} "
            f"{_estado_color(m.estado):<23} "
            f"{d['temperatura']:>7.1f} "
            f"{d['vibracion']:>9.3f} "
            f"{d['rpm']:>6}"
            f"{urgente}"
        )

    print()
    print(_color("  [F] Falla  [R] Recuperar  [U] Urgente  [P] Paro  [Q] Salir", 37))


# ---------------------------------------------------------------------------
# Loop de teclado (Windows: msvcrt)
# ---------------------------------------------------------------------------

def loop_teclado(maquinas: dict[str, Maquina], stop: threading.Event):
    while not stop.is_set():
        if msvcrt.kbhit():
            tecla = msvcrt.getwch().upper()

            if tecla == "F":
                m = _maquina_aleatoria(maquinas, lambda x: x.estado != Estado.FALLA)
                if m:
                    m.inyectar_falla()

            elif tecla == "R":
                m = _maquina_aleatoria(maquinas, lambda x: x.estado == Estado.FALLA)
                if m:
                    m.recuperar()

            elif tecla == "U":
                m = _maquina_aleatoria(maquinas, lambda x: x.estado == Estado.OPERANDO)
                if m:
                    orden_id = f"ORD-{random.randint(1000,9999)}"
                    m.orden_urgente_set(orden_id)

            elif tecla == "P":
                m = _maquina_aleatoria(maquinas, lambda x: x.estado != Estado.PARADO)
                if m:
                    m.paro()

            elif tecla == "Q":
                stop.set()

        time.sleep(0.05)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="FabriSense CNC Simulator")
    parser.add_argument("--broker", default=BROKER_HOST)
    parser.add_argument("--port",   default=BROKER_PORT, type=int)
    parser.add_argument("--tenant", default=TENANT_ID)
    args = parser.parse_args()

    # Inicializar máquinas
    maquinas = {mid: Maquina(id=mid) for mid in MAQUINAS}

    # Conectar MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = lambda c, u, f, rc, p: print(
        f"  MQTT conectado a {args.broker}:{args.port} (rc={rc})"
    )
    try:
        client.connect(args.broker, args.port, keepalive=60)
    except ConnectionRefusedError:
        print(f"ERROR: No se pudo conectar a MQTT en {args.broker}:{args.port}")
        print("       Inicia el broker: docker-compose up mqtt")
        sys.exit(1)
    client.loop_start()

    stop = threading.Event()

    t_publish  = threading.Thread(target=loop_publicacion,
                                  args=(client, maquinas, args.tenant, stop),
                                  daemon=True)
    t_keyboard = threading.Thread(target=loop_teclado,
                                  args=(maquinas, stop),
                                  daemon=True)

    t_publish.start()
    t_keyboard.start()

    try:
        while not stop.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        stop.set()
    finally:
        client.loop_stop()
        client.disconnect()
        print("\n  Simulador detenido.")


if __name__ == "__main__":
    main()
