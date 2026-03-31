"""
FabriSense — Worker de sensores (consumer.py)

Lee mensajes de Redis Streams, valida con el modelo SensorData,
persiste en MongoDB (Time Series) y genera alertas por umbral.

Corre como proceso independiente — NO dentro de FastAPI.

Uso:
    python consumer.py

Variables de entorno:
    REDIS_URL       (default: redis://localhost:6379)
    MONGODB_URI     (default: mongodb://localhost:27017)

/ FabriSense sensor worker.
/ עובד חיישנים של FabriSense.
"""

import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timezone

import redis
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Agregar el directorio raíz al path para importar desde app/
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

REDIS_URL         = os.getenv("REDIS_URL", "redis://localhost:6379")
MONGODB_URI       = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
STREAM_KEY        = "sensor_stream"
CONSUMER_GROUP    = "fabrisense_consumers"
CONSUMER_NAME     = f"worker-{os.getpid()}"
POLL_TIMEOUT_MS   = 1_000          # 1 segundo de bloqueo en XREADGROUP
BATCH_SIZE        = 10             # Mensajes por poll

# Umbrales de alerta
UMBRAL_TEMPERATURA = 90.0          # °C
UMBRAL_VIBRACION   = 15.0          # mm/s RMS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CONSUMER] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("consumer")

# ---------------------------------------------------------------------------
# Señal de apagado limpio
# ---------------------------------------------------------------------------

_running = True


def _handle_sigint(signum, frame):
    global _running
    log.info("SIGINT recibido — apagando worker…")
    _running = False


signal.signal(signal.SIGINT, _handle_sigint)
signal.signal(signal.SIGTERM, _handle_sigint)

# ---------------------------------------------------------------------------
# Conexiones
# ---------------------------------------------------------------------------


def _connect_redis() -> redis.Redis:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    log.info("Redis conectado: %s", REDIS_URL)
    return r


def _connect_mongo() -> MongoClient:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5_000)
    client.admin.command("ping")
    log.info("MongoDB conectado: %s", MONGODB_URI)
    return client


def _ensure_consumer_group(r: redis.Redis):
    """Crea el consumer group si no existe."""
    try:
        r.xgroup_create(STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True)
        log.info("Consumer group '%s' creado", CONSUMER_GROUP)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            log.info("Consumer group '%s' ya existe", CONSUMER_GROUP)
        else:
            raise


# ---------------------------------------------------------------------------
# Lógica de procesamiento
# ---------------------------------------------------------------------------


def _parse_sensor_data(raw: dict) -> dict | None:
    """
    Valida y normaliza un mensaje de sensor.
    Retorna None si el mensaje no tiene los campos mínimos.

    / Validates and normalizes a sensor message.
    / מאמת ומנרמל הודעת חיישן.
    """
    required = {"maquina_id", "temperatura", "vibracion", "rpm"}
    if not required.issubset(raw.keys()):
        log.warning("Mensaje incompleto, campos faltantes: %s", required - raw.keys())
        return None

    try:
        return {
            "maquina_id":  str(raw["maquina_id"]),
            "temperatura": float(raw["temperatura"]),
            "vibracion":   float(raw["vibracion"]),
            "rpm":         int(raw["rpm"]),
            "estado":      str(raw.get("estado", "operando")),
            "timestamp":   raw.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "tenant_id":   str(raw.get("tenant_id", "default")),
            "orden_id":    raw.get("orden_urgente"),
        }
    except (ValueError, TypeError) as e:
        log.warning("Error al parsear campos numéricos: %s", e)
        return None


def _save_sensor_data(db, sensor: dict):
    """
    Guarda la lectura en la colección Time Series 'sensor_data'.

    / Saves the reading to the 'sensor_data' Time Series collection.
    / שומר את הקריאה באוסף 'sensor_data' Time Series.
    """
    try:
        db["sensor_data"].insert_one({**sensor, "inserted_at": datetime.now(timezone.utc)})
    except PyMongoError as e:
        log.error("Error MongoDB al guardar sensor_data: %s", e)


def _check_thresholds(db, sensor: dict):
    """
    Verifica umbrales y crea alertas si se superan.

    Umbrales:
      temperatura > 90°C  → alerta critical
      vibracion   > 15 mm/s → alerta warning

    / Checks thresholds and creates alerts if exceeded.
    / בודק סף ויוצר התראות אם חורגים.
    """
    alertas = []

    if sensor["temperatura"] > UMBRAL_TEMPERATURA:
        alertas.append({
            "alerta_id":  str(uuid.uuid4()),
            "maquina_id": sensor["maquina_id"],
            "tipo":       "temperatura_alta",
            "severidad":  "critical",
            "mensaje":    (
                f"Temperatura crítica: {sensor['temperatura']:.1f}°C "
                f"(umbral: {UMBRAL_TEMPERATURA}°C)"
            ),
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "atendida":   False,
            "tenant_id":  sensor["tenant_id"],
        })

    if sensor["vibracion"] > UMBRAL_VIBRACION:
        alertas.append({
            "alerta_id":  str(uuid.uuid4()),
            "maquina_id": sensor["maquina_id"],
            "tipo":       "vibracion_alta",
            "severidad":  "warning",
            "mensaje":    (
                f"Vibración elevada: {sensor['vibracion']:.3f} mm/s "
                f"(umbral: {UMBRAL_VIBRACION} mm/s)"
            ),
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "atendida":   False,
            "tenant_id":  sensor["tenant_id"],
        })

    if alertas:
        try:
            db["alertas"].insert_many(alertas)
            for a in alertas:
                log.warning(
                    "🚨 ALERTA [%s] %s — %s",
                    a["severidad"].upper(),
                    a["maquina_id"],
                    a["mensaje"],
                )
        except PyMongoError as e:
            log.error("Error MongoDB al guardar alertas: %s", e)


def _process_message(db, msg_id: str, fields: dict):
    """Procesa un mensaje individual del stream."""
    try:
        raw = json.loads(fields.get("data", "{}"))
    except json.JSONDecodeError as e:
        log.warning("JSON inválido en msg_id=%s: %s", msg_id, e)
        return

    sensor = _parse_sensor_data(raw)
    if sensor is None:
        return

    _save_sensor_data(db, sensor)
    _check_thresholds(db, sensor)

    log.info(
        "✓ %s | maq=%s temp=%.1f°C vib=%.3f rpm=%d",
        sensor["tenant_id"],
        sensor["maquina_id"],
        sensor["temperatura"],
        sensor["vibracion"],
        sensor["rpm"],
    )


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------


def run():
    """
    Loop principal del worker. Bloqueante hasta recibir SIGINT/SIGTERM.

    / Main worker loop. Blocking until SIGINT/SIGTERM.
    / לולאה ראשית של ה-worker. חוסם עד לקבלת SIGINT/SIGTERM.
    """
    # Conectar servicios
    try:
        r = _connect_redis()
    except Exception as e:
        log.critical("No se pudo conectar a Redis: %s", e)
        sys.exit(1)

    try:
        mongo = _connect_mongo()
        db = mongo["fabrisense"]
    except Exception as e:
        log.critical("No se pudo conectar a MongoDB: %s", e)
        sys.exit(1)

    _ensure_consumer_group(r)

    log.info(
        "Worker iniciado | stream=%s group=%s consumer=%s",
        STREAM_KEY, CONSUMER_GROUP, CONSUMER_NAME,
    )

    # Procesar mensajes pendientes de runs anteriores primero
    pending_id = "0"
    recovering = True

    while _running:
        read_id = pending_id if recovering else ">"

        try:
            results = r.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: read_id},
                count=BATCH_SIZE,
                block=POLL_TIMEOUT_MS,
            )
        except redis.RedisError as e:
            log.error("Error leyendo Redis Stream: %s", e)
            time.sleep(1)
            continue

        if not results:
            if recovering:
                # No quedan pendientes — pasar al modo normal
                recovering = False
                pending_id = ">"
                log.info("Recuperación de pendientes completada. Modo normal activo.")
            continue

        for _stream, messages in results:
            if not messages and recovering:
                recovering = False
                continue

            for msg_id, fields in messages:
                _process_message(db, msg_id, fields)

                # ACK del mensaje
                try:
                    r.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
                except redis.RedisError as e:
                    log.error("Error en XACK para msg_id=%s: %s", msg_id, e)

    # Apagado limpio
    log.info("Worker detenido.")
    mongo.close()


if __name__ == "__main__":
    run()
