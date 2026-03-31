"""
Conector FabriControl → FabriSense.

FabriControl y FabriSense comparten la misma base de datos MongoDB.
Este módulo lee directamente las colecciones de FabriControl y mapea
los documentos al formato interno de FabriSense.

/ FabriControl → FabriSense connector.
/ מחבר FabriControl ← FabriSense.
"""

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

# ---------------------------------------------------------------------------
# Mapeo de campos FabriControl → FabriSense
# ---------------------------------------------------------------------------

def _map_orden(doc: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    """
    Convierte un documento de 'orders' de FabriControl al formato FabriSense.
    / Converts a FabriControl 'orders' document to FabriSense format.
    / ממיר מסמך 'orders' של FabriControl לפורמט FabriSense.
    """
    return {
        "orden_id":      str(doc.get("_id", doc.get("order_id", ""))),
        "cliente":       doc.get("customer", doc.get("cliente", "Desconocido")),
        "producto":      doc.get("product",  doc.get("producto", "Desconocido")),
        "cantidad":      int(doc.get("quantity", doc.get("cantidad", 0))),
        "prioridad":     _map_prioridad(doc.get("priority", doc.get("prioridad", "normal"))),
        "fecha_entrega": doc.get("due_date", doc.get("fecha_entrega")),
        "estado":        _map_estado_orden(doc.get("status", doc.get("estado", "pendiente"))),
        "fuente":        "fabricontrol",
        "maquina_id":    doc.get("machine_id", doc.get("maquina_id")),
        "operador_id":   doc.get("operator_id", doc.get("operador_id")),
        "notas":         doc.get("notes", doc.get("notas")),
        "tenant_id":     tenant_id,
    }


def _map_maquina(doc: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    """
    Convierte un documento de 'machines' de FabriControl al formato FabriSense.
    / Converts a FabriControl 'machines' document to FabriSense format.
    / ממיר מסמך 'machines' של FabriControl לפורמט FabriSense.
    """
    return {
        "maquina_id":    str(doc.get("_id", doc.get("machine_id", ""))),
        "nombre":        doc.get("name", doc.get("nombre", "Sin nombre")),
        "tipo":          doc.get("type", doc.get("tipo", "desconocido")),
        "marca_cnc":     doc.get("brand", doc.get("marca", "Desconocida")),
        "nivel":         doc.get("level", doc.get("nivel", "basico")),
        "tasa_horaria":  float(doc.get("hourly_rate", doc.get("tasa_horaria", 0.0))),
        "tenant_id":     tenant_id,
        "activa":        doc.get("active", doc.get("activa", True)),
    }


def _map_prioridad(valor: str) -> str:
    mapping = {
        "low": "baja", "medium": "normal", "high": "alta", "urgent": "urgente",
        "baja": "baja", "normal": "normal", "alta": "alta", "urgente": "urgente",
    }
    return mapping.get(str(valor).lower(), "normal")


def _map_estado_orden(valor: str) -> str:
    mapping = {
        "pending": "pendiente", "in_progress": "en_proceso",
        "completed": "completada", "cancelled": "cancelada", "delayed": "retrasada",
        "pendiente": "pendiente", "en_proceso": "en_proceso",
        "completada": "completada", "cancelada": "cancelada", "retrasada": "retrasada",
    }
    return mapping.get(str(valor).lower(), "pendiente")


# ---------------------------------------------------------------------------
# Funciones de lectura async
# ---------------------------------------------------------------------------

async def leer_ordenes_fabricontrol(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """
    Lee la colección 'orders' de FabriControl y retorna órdenes mapeadas.
    / Reads FabriControl 'orders' collection and returns mapped orders.
    / קורא את אוסף 'orders' של FabriControl ומחזיר הזמנות ממופות.
    """
    cursor = db["orders"].find({}).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_map_orden(doc, tenant_id) for doc in docs]


async def leer_maquinas_fabricontrol(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
) -> list[dict[str, Any]]:
    """
    Lee la colección 'machines' de FabriControl y retorna máquinas mapeadas.
    / Reads FabriControl 'machines' collection and returns mapped machines.
    / קורא את אוסף 'machines' של FabriControl ומחזיר מכונות ממופות.
    """
    cursor = db["machines"].find({})
    docs = await cursor.to_list(length=None)
    return [_map_maquina(doc, tenant_id) for doc in docs]


# ---------------------------------------------------------------------------
# Sincronización incremental
# ---------------------------------------------------------------------------

async def sincronizar_ordenes(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Compara las órdenes de FabriControl con las ya importadas en FabriSense
    e importa solo las nuevas (por orden_id).
    / Compares FabriControl orders with already-imported ones and imports only new ones.
    / משווה הזמנות FabriControl עם הקיימות ומייבא רק חדשות.
    """
    ordenes_fc = await leer_ordenes_fabricontrol(db, tenant_id)

    ids_fc = {o["orden_id"] for o in ordenes_fc}
    cursor = db["fabrisense_ordenes"].find(
        {"fuente": "fabricontrol", "tenant_id": tenant_id},
        {"orden_id": 1},
    )
    existentes = await cursor.to_list(length=None)
    ids_existentes = {doc["orden_id"] for doc in existentes}

    nuevas = [o for o in ordenes_fc if o["orden_id"] not in ids_existentes]

    importadas = 0
    if nuevas:
        await db["fabrisense_ordenes"].insert_many(nuevas)
        importadas = len(nuevas)

    return {
        "total_fabricontrol": len(ordenes_fc),
        "ya_existentes": len(ids_existentes),
        "nuevas_importadas": importadas,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def estado_sync(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Devuelve estadísticas de la última sincronización.
    / Returns statistics from the last synchronization.
    / מחזיר סטטיסטיקות מהסנכרון האחרון.
    """
    total = await db["fabrisense_ordenes"].count_documents(
        {"fuente": "fabricontrol", "tenant_id": tenant_id}
    )
    ultimo = await db["fabrisense_ordenes"].find_one(
        {"fuente": "fabricontrol", "tenant_id": tenant_id},
        sort=[("_id", -1)],
    )
    return {
        "ordenes_importadas": total,
        "ultima_importada": str(ultimo.get("_id", "")) if ultimo else None,
        "tenant_id": tenant_id,
    }
