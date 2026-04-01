"""
Router APS - Planificacion Automatica de Produccion (Fase F4).

Endpoints:
  GET  /api/aps/plan-hoy      -> Plan actual del dia
  POST /api/aps/generar        -> Forzar generacion de nuevo plan (manual)
  GET  /api/aps/historial      -> Versiones del plan de hoy
  POST /api/aps/trigger/paro   -> Simular paro de maquina (dev)
  POST /api/aps/trigger/urgente -> Simular orden urgente (dev)
  POST /api/aps/trigger/recuperacion -> Simular maquina recuperada (dev)

/ APS Router - Automatic Production Scheduling (Phase F4).
/ נתב APS - תכנון ייצור אוטומטי (שלב F4).
"""

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel

from app.services.auth import verify_access_token
from app.services.aps_scheduler import generar_plan_8am
from app.services.aps_triggers import (
    trigger_paro_maquina,
    trigger_orden_urgente,
    trigger_maquina_recuperada,
)

router = APIRouter(prefix="/api/aps", tags=["aps"])
bearer_scheme = HTTPBearer()


# ---------------------------------------------------------------------------
# Auth helper (mismo patron que inteligencia.py)
# ---------------------------------------------------------------------------

def _current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    try:
        return verify_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalido o expirado")


# ---------------------------------------------------------------------------
# Modelos de request
# ---------------------------------------------------------------------------

class TriggerParoRequest(BaseModel):
    """
    Payload para simular un paro de maquina.
    / Payload to simulate a machine stop.
    / מטען לדמיית עצירת מכונה.
    """
    maquina_id: str


class TriggerUrgenteRequest(BaseModel):
    """
    Payload para simular una orden urgente.
    / Payload to simulate an urgent order.
    / מטען לדמיית הזמנה דחופה.
    """
    orden_id: str
    cliente: str = "Cliente Urgente"
    producto: str = "Pieza Urgente"
    cantidad: int = 100
    fecha_entrega: Optional[date] = None


class TriggerRecuperacionRequest(BaseModel):
    """
    Payload para simular maquina recuperada.
    / Payload to simulate a machine recovery.
    / מטען לדמיית החזרת מכונה לפעולה.
    """
    maquina_id: str


# ---------------------------------------------------------------------------
# Store in-memory para planes demo (hasta MongoDB)
# ---------------------------------------------------------------------------

_planes_hoy: list[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/plan-hoy")
async def plan_hoy(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Plan actual del dia con todas las asignaciones.
    Retorna la version mas reciente del plan.

    / Current daily plan with all assignments.
    / תוכנית יומית נוכחית עם כל ההקצאות.
    """
    tenant_id = current.get("tenant_id", "demo-pro")

    # Buscar plan mas reciente del dia
    hoy = date.today().isoformat()
    planes_del_dia = [p for p in _planes_hoy if p.get("fecha") == hoy and p.get("tenant_id") == tenant_id]

    if not planes_del_dia:
        # Generar plan automaticamente si no existe
        plan = generar_plan_8am(tenant_id=tenant_id)
        plan["version"] = 1
        _planes_hoy.append(plan)
        return plan

    # Retornar la version mas reciente
    return max(planes_del_dia, key=lambda p: p.get("version", 0))


@router.post("/generar")
async def generar_plan(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Forzar generacion de un nuevo plan (manual).
    Crea una nueva version del plan del dia.

    / Force generation of a new plan (manual).
    / אילוץ יצירת תוכנית חדשה (ידני).
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    hoy = date.today().isoformat()

    # Calcular version
    planes_del_dia = [p for p in _planes_hoy if p.get("fecha") == hoy and p.get("tenant_id") == tenant_id]
    nueva_version = max((p.get("version", 0) for p in planes_del_dia), default=0) + 1

    plan = generar_plan_8am(tenant_id=tenant_id)
    plan["version"] = nueva_version
    plan["motivo"] = "manual"
    plan["timestamp"] = datetime.now(timezone.utc).isoformat()

    _planes_hoy.append(plan)

    return {
        "mensaje": f"Plan v{nueva_version} generado exitosamente",
        "plan": plan,
    }


@router.get("/historial")
async def historial_planes(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Todas las versiones del plan de hoy (v1, v2, v3...).
    Permite ver la evolucion del plan durante el dia.

    / All versions of today's plan.
    / כל הגרסאות של תוכנית היום.
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    hoy = date.today().isoformat()

    planes_del_dia = [
        p for p in _planes_hoy
        if p.get("fecha") == hoy and p.get("tenant_id") == tenant_id
    ]
    planes_del_dia.sort(key=lambda p: p.get("version", 0))

    return {
        "fecha": hoy,
        "total_versiones": len(planes_del_dia),
        "versiones": planes_del_dia,
    }


# ---------------------------------------------------------------------------
# Triggers de re-planificacion (dev/simulacion)
# ---------------------------------------------------------------------------

@router.post("/trigger/paro")
async def trigger_paro_endpoint(
    body: TriggerParoRequest,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Simular evento de paro de maquina.
    Reasigna ordenes de la maquina parada a otras disponibles.

    / Simulate machine stop event.
    / דמיית אירוע עצירת מכונה.
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    resultado = trigger_paro_maquina(
        maquina_id=body.maquina_id,
        tenant_id=tenant_id,
    )

    if resultado.get("replanificado") and resultado.get("plan"):
        hoy = date.today().isoformat()
        planes_del_dia = [p for p in _planes_hoy if p.get("fecha") == hoy and p.get("tenant_id") == tenant_id]
        nueva_version = max((p.get("version", 0) for p in planes_del_dia), default=0) + 1
        resultado["plan"]["version"] = nueva_version
        _planes_hoy.append(resultado["plan"])

    return resultado


@router.post("/trigger/urgente")
async def trigger_urgente_endpoint(
    body: TriggerUrgenteRequest,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Simular entrada de orden urgente.
    Inserta la orden con maxima prioridad y re-genera el plan.

    / Simulate urgent order entry.
    / דמיית כניסת הזמנה דחופה.
    """
    tenant_id = current.get("tenant_id", "demo-pro")

    orden = {
        "orden_id": body.orden_id,
        "cliente": body.cliente,
        "producto": body.producto,
        "cantidad": body.cantidad,
        "prioridad": "urgente",
        "fecha_entrega": (body.fecha_entrega or date.today()).isoformat(),
        "estado": "pendiente",
        "fuente": "manual",
        "tenant_id": tenant_id,
    }

    resultado = trigger_orden_urgente(
        orden=orden,
        tenant_id=tenant_id,
    )

    if resultado.get("replanificado") and resultado.get("plan"):
        hoy = date.today().isoformat()
        planes_del_dia = [p for p in _planes_hoy if p.get("fecha") == hoy and p.get("tenant_id") == tenant_id]
        nueva_version = max((p.get("version", 0) for p in planes_del_dia), default=0) + 1
        resultado["plan"]["version"] = nueva_version
        _planes_hoy.append(resultado["plan"])

    return resultado


@router.post("/trigger/recuperacion")
async def trigger_recuperacion_endpoint(
    body: TriggerRecuperacionRequest,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Simular maquina recuperada.
    Redistribuye la carga para balancear entre todas las disponibles.

    / Simulate machine recovery.
    / דמיית החזרת מכונה לפעולה.
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    resultado = trigger_maquina_recuperada(
        maquina_id=body.maquina_id,
        tenant_id=tenant_id,
    )

    if resultado.get("replanificado") and resultado.get("plan"):
        hoy = date.today().isoformat()
        planes_del_dia = [p for p in _planes_hoy if p.get("fecha") == hoy and p.get("tenant_id") == tenant_id]
        nueva_version = max((p.get("version", 0) for p in planes_del_dia), default=0) + 1
        resultado["plan"]["version"] = nueva_version
        _planes_hoy.append(resultado["plan"])

    return resultado
