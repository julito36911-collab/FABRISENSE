"""
Router de conectores de datos de entrada (Fase F2).

Cubre:
  2.1 - Conector FabriControl (lectura directa MongoDB)
  2.2 - Importador CSV genérico de órdenes
  2.3 - Entrada manual de órdenes

/ Data input connectors router (Phase F2).
/ נתב מחברי נתוני קלט (שלב F2).
"""

import uuid
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.orden import Orden, OrdenCreate
from app.services.auth import verify_access_token
from app.services.csv_importer import importar_csv, preview_csv
from app.services.fabricontrol_connector import (
    estado_sync,
    sincronizar_ordenes,
)
from jose import JWTError

router = APIRouter(tags=["connectors & orders"])
bearer_scheme = HTTPBearer()

# ---------------------------------------------------------------------------
# In-memory store (hasta que se conecte MongoDB)
# ---------------------------------------------------------------------------
_ordenes: dict[str, dict] = {}
_sync_log: list[dict] = []


# ---------------------------------------------------------------------------
# Dependency: usuario autenticado
# ---------------------------------------------------------------------------

def _current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    try:
        return verify_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


# ---------------------------------------------------------------------------
# 2.1 - FabriControl sync
# ---------------------------------------------------------------------------

@router.post("/api/connect/fabricontrol/sync")
async def sync_fabricontrol(current: dict = Depends(_current_user)) -> dict:
    """
    Ejecuta sincronización manual de FabriControl → FabriSense.
    Solo importa órdenes nuevas (comparación por orden_id).

    / Runs a manual FabriControl → FabriSense synchronization.
    / מריץ סנכרון ידני FabriControl ← FabriSense.
    """
    # Sin MongoDB conectado, devuelve respuesta simulada
    result = {
        "total_fabricontrol": 0,
        "ya_existentes": len(_ordenes),
        "nuevas_importadas": 0,
        "mensaje": "MongoDB no conectado — conecta la BD para sincronización real",
        "timestamp": date.today().isoformat(),
    }
    _sync_log.append(result)
    return result


@router.get("/api/connect/fabricontrol/status")
async def fabricontrol_status(current: dict = Depends(_current_user)) -> dict:
    """
    Devuelve el estado de la última sincronización con FabriControl
    y la cantidad de órdenes importadas.

    / Returns the status of the last FabriControl sync and imported orders count.
    / מחזיר את מצב הסנכרון האחרון עם FabriControl ומספר ההזמנות המיובאות.
    """
    ordenes_fc = sum(1 for o in _ordenes.values() if o.get("fuente") == "fabricontrol")
    ultima = _sync_log[-1] if _sync_log else None
    return {
        "ordenes_importadas_fabricontrol": ordenes_fc,
        "ultima_sync": ultima,
        "total_ordenes_sistema": len(_ordenes),
    }


# ---------------------------------------------------------------------------
# 2.2 - Importador CSV
# ---------------------------------------------------------------------------

@router.post("/api/import/ordenes-csv")
async def preview_ordenes_csv(
    archivo: UploadFile = File(...),
    current: dict = Depends(_current_user),
) -> dict:
    """
    Sube un CSV de órdenes y devuelve un preview del mapeo detectado
    junto con las primeras filas para que el usuario confirme el mapeo.

    / Uploads an orders CSV and returns a mapping preview for confirmation.
    / מעלה CSV הזמנות ומחזיר תצוגה מקדימה של המיפוי לאישור.
    """
    contenido = await archivo.read()
    return preview_csv(contenido)


@router.post("/api/import/ordenes-csv/confirm")
async def confirmar_import_csv(
    archivo: UploadFile = File(...),
    column_map: str = Form(default="{}"),
    current: dict = Depends(_current_user),
) -> dict:
    """
    Confirma e importa las órdenes desde el CSV usando el mapeo proporcionado.
    El campo column_map es un JSON string: {"orden_id": "ID", "producto": "Part"}.

    / Confirms and imports orders from CSV using the provided column mapping.
    / מאשר ומייבא הזמנות מ-CSV באמצעות מיפוי העמודות שסופק.
    """
    import json

    contenido = await archivo.read()
    tenant_id = current.get("tenant_id", "default")

    try:
        mapa = json.loads(column_map)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="column_map debe ser JSON válido")

    resultado = importar_csv(contenido, mapa, tenant_id)

    if "error" in resultado:
        raise HTTPException(status_code=400, detail=resultado["error"])

    # Almacenar órdenes válidas en el store temporal
    for orden in resultado["ordenes"]:
        _ordenes[orden["orden_id"]] = orden

    return {
        "importadas": resultado["validas"],
        "errores": resultado["con_error"],
        "detalle_errores": resultado["errores"],
    }


# ---------------------------------------------------------------------------
# 2.3 - Entrada manual de órdenes
# ---------------------------------------------------------------------------

@router.post("/api/ordenes/nueva", status_code=status.HTTP_201_CREATED)
async def crear_orden(
    body: OrdenCreate,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Crea una orden de producción manualmente.
    Roles permitidos: admin, supervisor.

    / Creates a production order manually. Allowed roles: admin, supervisor.
    / יוצר הזמנת ייצור ידנית. תפקידים מותרים: מנהל, מפקח.
    """
    if current.get("rol") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Se requiere rol admin o supervisor")

    orden_id = f"ORD-{str(uuid.uuid4())[:8].upper()}"
    tenant_id = current.get("tenant_id", "default")

    orden = {
        "orden_id":      orden_id,
        "cliente":       body.cliente,
        "producto":      body.producto,
        "cantidad":      body.cantidad,
        "prioridad":     body.prioridad,
        "fecha_entrega": body.fecha_entrega.isoformat(),
        "estado":        "pendiente",
        "fuente":        "manual",
        "maquina_id":    body.maquina_id,
        "operador_id":   body.operador_id,
        "notas":         body.notas,
        "tenant_id":     tenant_id,
    }
    _ordenes[orden_id] = orden
    return orden


@router.get("/api/ordenes")
async def listar_ordenes(
    estado: Optional[str] = None,
    prioridad: Optional[str] = None,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Lista todas las órdenes del tenant. Filtros opcionales: estado, prioridad.

    / Lists all orders for the tenant. Optional filters: estado, prioridad.
    / מפרט את כל ההזמנות של ה-tenant. פילטרים אופציונליים: estado, prioridad.
    """
    tenant_id = current.get("tenant_id", "default")
    ordenes = [o for o in _ordenes.values() if o.get("tenant_id") == tenant_id]

    if estado:
        ordenes = [o for o in ordenes if o.get("estado") == estado]
    if prioridad:
        ordenes = [o for o in ordenes if o.get("prioridad") == prioridad]

    return {"total": len(ordenes), "ordenes": ordenes}


@router.get("/api/ordenes/{orden_id}")
async def detalle_orden(
    orden_id: str,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Devuelve el detalle completo de una orden.

    / Returns the full detail of a production order.
    / מחזיר את הפרטים המלאים של הזמנה.
    """
    tenant_id = current.get("tenant_id", "default")
    orden = _ordenes.get(orden_id)
    if not orden or orden.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return orden
