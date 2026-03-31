# FabriSense — Backend

Stack: FastAPI · MongoDB · Mosquitto MQTT · Redis

## Requisitos previos

- Docker + Docker Compose
- Python 3.11+
- (Opcional) entorno virtual: `python -m venv venv && venv\Scripts\activate`

## Instalación de dependencias

```bash
pip install -r requirements.txt
```

## Variables de entorno

Copia `.env.example` a `.env` y ajusta los valores:

```bash
cp ../.env.example .env
```

---

## Cómo correr el stack completo

### 1. Infraestructura (MongoDB + Mosquitto + Redis)

```bash
# Desde la raíz del proyecto
docker-compose up -d
```

Servicios disponibles:
| Servicio   | Puerto | Descripción                     |
|------------|--------|---------------------------------|
| MongoDB    | 27017  | Base de datos principal         |
| Mosquitto  | 1883   | Broker MQTT (dev sin TLS)       |
| Redis      | 6379   | Cola de mensajes (Streams)      |

---

### 2. API REST (FastAPI)

```bash
# Desde /backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Documentación interactiva:
- Swagger UI: http://localhost:8000/docs
- ReDoc:       http://localhost:8000/redoc
- Health:      http://localhost:8000/health

---

### 3. Worker de sensores (consumer.py)

Lee de Redis Streams, valida con Pydantic, guarda en MongoDB y genera alertas.

```bash
# Desde /backend — proceso separado
python consumer.py
```

---

### 4. Receptor MQTT → Redis (mqtt_receiver.py)

Escucha todos los topics de sensores y los encola en Redis Streams.

```bash
# Desde /backend — proceso separado
python -m app.services.mqtt_receiver
```

---

### 5. Simulador CNC (simulador_cnc.py)

Simula 8 máquinas CNC enviando datos por MQTT.

```bash
# Desde /backend — proceso separado
python simulator/simulador_cnc.py

# Con broker remoto y tenant personalizado:
python simulator/simulador_cnc.py --broker 192.168.1.x --tenant mi-fabrica
```

Controles de teclado:
| Tecla | Acción                                 |
|-------|----------------------------------------|
| `F`   | Inyectar falla en máquina aleatoria    |
| `R`   | Recuperar máquina en falla             |
| `U`   | Marcar orden urgente                   |
| `P`   | Provocar paro de máquina               |
| `Q`   | Salir del simulador                    |

---

## Flujo de datos

```
[Simulador CNC]
      │ MQTT publish
      ▼
[Mosquitto :1883]
      │ suscripción wildcard
      ▼
[mqtt_receiver.py]
      │ XADD → Redis Stream "sensor_stream"
      ▼
[Redis :6379]
      │ XREADGROUP
      ▼
[consumer.py]
      ├── MongoDB "sensor_data"   (Time Series)
      └── MongoDB "alertas"       (si umbral superado)
```

---

## Umbrales de alerta

| Parámetro   | Umbral   | Severidad  |
|-------------|----------|------------|
| Temperatura | > 90 °C  | critical   |
| Vibración   | > 15 mm/s| warning    |

---

## Estructura de directorios

```
backend/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings desde variables de entorno
│   ├── models/              # Modelos Pydantic
│   ├── routers/             # Endpoints REST
│   └── services/            # Lógica de negocio
│       ├── auth.py
│       ├── mqtt_receiver.py
│       ├── fabricontrol_connector.py
│       ├── csv_importer.py
│       └── asistencia_service.py
├── simulator/
│   └── simulador_cnc.py     # Simulador de 8 máquinas CNC
├── consumer.py              # Worker Redis Streams → MongoDB
└── README.md
```
