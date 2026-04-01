"""
Conexion a MongoDB con motor (async driver) — Fase F5.

Provee:
  - Cliente global AsyncIOMotorClient
  - Funcion get_database() para dependency injection en routers
  - Inicializacion de colecciones al arrancar la app

/ MongoDB connection with motor (async driver) — Phase F5.
/ חיבור למונגו עם motor (נהג אסינכרוני) — שלב F5.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import CollectionInvalid

from app.config import settings

# ---------------------------------------------------------------------------
# Cliente global — se inicializa en lifespan de FastAPI
# ---------------------------------------------------------------------------

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

# Nombre de la base de datos
DB_NAME = "fabrisense"

# Colecciones regulares
COLECCIONES_REGULARES = [
    "tenants",
    "users",
    "maquinas",
    "operadores",
    "ordenes",
    "asistencia",
    "historial_paros",
    "plan_diario",
    "alertas",
    "leads_configurador",
    "config_cliente",
]


# ---------------------------------------------------------------------------
# Conectar / Desconectar
# ---------------------------------------------------------------------------

async def conectar_mongo() -> None:
    """
    Conecta a MongoDB y crea las colecciones necesarias.
    Se llama en el evento startup de FastAPI.

    / Connects to MongoDB and creates required collections.
    / מתחבר למונגו ויוצר את האוספים הנדרשים.
    """
    global _client, _db

    _client = AsyncIOMotorClient(settings.MONGODB_URI)
    _db = _client[DB_NAME]

    await _crear_colecciones(_db)
    print(f"[DB] Conectado a MongoDB: {DB_NAME}")


async def desconectar_mongo() -> None:
    """
    Cierra la conexion a MongoDB.
    Se llama en el evento shutdown de FastAPI.

    / Closes the MongoDB connection.
    / סוגר את החיבור למונגו.
    """
    global _client
    if _client:
        _client.close()
        print("[DB] Conexion MongoDB cerrada")


# ---------------------------------------------------------------------------
# Crear colecciones
# ---------------------------------------------------------------------------

async def _crear_colecciones(db: AsyncIOMotorDatabase) -> None:
    """
    Crea colecciones si no existen.
    sensor_data se crea como Time Series collection.

    / Creates collections if they don't exist.
    / יוצר אוספים אם לא קיימים.
    """
    colecciones_existentes = await db.list_collection_names()

    # Colecciones regulares
    for nombre in COLECCIONES_REGULARES:
        if nombre not in colecciones_existentes:
            try:
                await db.create_collection(nombre)
                print(f"[DB] Coleccion creada: {nombre}")
            except CollectionInvalid:
                pass  # Ya existe (race condition)

    # sensor_data como Time Series (MongoDB 5.0+)
    if "sensor_data" not in colecciones_existentes:
        try:
            await db.create_collection(
                "sensor_data",
                timeseries={
                    "timeField": "timestamp",
                    "metaField": "maquina_id",
                    "granularity": "seconds",
                },
            )
            print("[DB] Coleccion Time Series creada: sensor_data")
        except Exception as e:
            # Si Time Series no soportado (version antigua), crear como regular
            print(f"[DB] Time Series no disponible ({e}), creando sensor_data regular")
            try:
                await db.create_collection("sensor_data")
            except CollectionInvalid:
                pass


# ---------------------------------------------------------------------------
# Dependency para FastAPI routers
# ---------------------------------------------------------------------------

def get_database() -> AsyncIOMotorDatabase:
    """
    Retorna la instancia de base de datos para uso como dependencia en FastAPI.

    Uso en router:
        from app.database import get_database
        from fastapi import Depends

        @router.get("/endpoint")
        async def endpoint(db = Depends(get_database)):
            data = await db["coleccion"].find_one(...)

    / Returns the database instance for use as a FastAPI dependency.
    / מחזיר את מופע מסד הנתונים לשימוש כתלות ב-FastAPI.
    """
    if _db is None:
        raise RuntimeError("Base de datos no inicializada. Verifica que MongoDB esta conectado.")
    return _db
