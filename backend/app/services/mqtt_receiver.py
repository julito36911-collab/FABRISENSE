"""
Receptor MQTT → Redis Streams.

Se suscribe al topic wildcard:
    fabrisense/+/maquina/+/datos

Por cada mensaje JSON recibido lo publica en el Redis Stream "sensor_stream"
para que el consumer.py lo procese de forma asíncrona.

Características:
  - Reconexión automática con back-off exponencial
  - Log estructurado de cada mensaje
  - Configurable por variables de entorno

/ MQTT receiver → Redis Streams.
/ מקלט MQTT → Redis Streams.

Variables de entorno:
    MQTT_BROKER_HOST  (default: localhost)
    MQTT_BROKER_PORT  (default: 1883)
    REDIS_URL         (default: redis://localhost:6379)
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import redis
import paho.mqtt.client as mqtt

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

MQTT_BROKER_HOST  = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT  = int(os.getenv("MQTT_BROKER_PORT", "1883"))
REDIS_URL         = os.getenv("REDIS_URL", "redis://localhost:6379")
MQTT_TOPIC        = "fabrisense/+/maquina/+/datos"
REDIS_STREAM_KEY  = "sensor_stream"
REDIS_MAXLEN      = 10_000          # Cap del stream para no crecer infinito
RECONNECT_DELAY   = 5               # segundos entre intentos de reconexión

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MQTT] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("mqtt_receiver")


# ---------------------------------------------------------------------------
# Cliente Redis (lazy — se conecta al primer uso)
# ---------------------------------------------------------------------------

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _publish_to_stream(payload: dict) -> str | None:
    """Publica el payload en Redis Stream. Retorna el message ID o None si falla."""
    try:
        r = _get_redis()
        # Serializar a string para almacenar en el stream (Redis no acepta dicts anidados)
        msg_id = r.xadd(
            REDIS_STREAM_KEY,
            {"data": json.dumps(payload)},
            maxlen=REDIS_MAXLEN,
            approximate=True,
        )
        return msg_id
    except redis.RedisError as e:
        log.error("Redis error al publicar: %s", e)
        return None


# ---------------------------------------------------------------------------
# Callbacks MQTT
# ---------------------------------------------------------------------------

def _on_connect(client: mqtt.Client, userdata, flags, rc, properties=None):
    if rc == 0:
        log.info("Conectado a MQTT broker %s:%s", MQTT_BROKER_HOST, MQTT_BROKER_PORT)
        client.subscribe(MQTT_TOPIC, qos=0)
        log.info("Suscrito al topic: %s", MQTT_TOPIC)
    else:
        log.warning("Conexión MQTT rechazada (rc=%s)", rc)


def _on_disconnect(client: mqtt.Client, userdata, rc, properties=None, reasoncode=None):
    if rc != 0:
        log.warning("Desconectado del broker (rc=%s). Reconectando en %ss…", rc, RECONNECT_DELAY)


def _on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
    """Procesa cada mensaje MQTT recibido y lo envía a Redis Streams."""
    try:
        raw = msg.payload.decode("utf-8")
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        log.warning("Mensaje inválido en topic %s: %s", msg.topic, e)
        return

    # Extraer tenant_id y maquina_id del topic:
    # fabrisense/{tenant_id}/maquina/{maquina_id}/datos
    parts = msg.topic.split("/")
    if len(parts) >= 5:
        data.setdefault("tenant_id", parts[1])
        data.setdefault("maquina_id", parts[3])

    data["received_at"] = datetime.now(timezone.utc).isoformat()
    data["topic"] = msg.topic

    msg_id = _publish_to_stream(data)
    if msg_id:
        log.info(
            "✓ [%s] maquina=%s temp=%.1f°C vib=%.3f rpm=%s → stream_id=%s",
            data.get("tenant_id", "?"),
            data.get("maquina_id", "?"),
            float(data.get("temperatura", 0)),
            float(data.get("vibracion", 0)),
            data.get("rpm", "?"),
            msg_id,
        )
    else:
        log.error("✗ No se pudo publicar en Redis el mensaje de %s", msg.topic)


def _on_log(client, userdata, level, buf):
    if level == mqtt.MQTT_LOG_ERR:
        log.debug("MQTT internal: %s", buf)


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def run_receiver():
    """
    Arranca el receptor MQTT. Bloqueante con reconexión automática.

    / Starts the MQTT receiver. Blocking with automatic reconnection.
    / מפעיל את המקלט MQTT. חוסם עם התחברות מחדש אוטומטית.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect    = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message    = _on_message
    client.on_log        = _on_log

    # Reconexión automática integrada en paho
    client.reconnect_delay_set(min_delay=1, max_delay=RECONNECT_DELAY * 4)

    while True:
        try:
            log.info("Conectando a %s:%s…", MQTT_BROKER_HOST, MQTT_BROKER_PORT)
            client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
            client.loop_forever()          # Bloquea; gestiona reconexión internamente
        except ConnectionRefusedError:
            log.error("Broker no disponible. Reintentando en %ss…", RECONNECT_DELAY)
            time.sleep(RECONNECT_DELAY)
        except KeyboardInterrupt:
            log.info("Deteniendo receptor MQTT…")
            client.disconnect()
            break
        except Exception as e:
            log.exception("Error inesperado: %s. Reintentando en %ss…", e, RECONNECT_DELAY)
            time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    run_receiver()
