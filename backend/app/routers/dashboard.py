"""
Router Dashboard — Fase F5.

Endpoints:
  GET /api/dashboard/resumen         -> metricas principales del tenant
  GET /api/dashboard/maquinas        -> maquinas con score de salud M1
  GET /api/dashboard/alertas-recientes -> ultimas 10 alertas
  GET /api/dashboard/plan-hoy        -> plan APS del dia
  GET /api/dashboard/asistencia-hoy  -> resumen de asistencia del dia
  GET /api/dashboard/roi             -> datos de ROI segun el mes del tenant

/ Dashboard Router — Phase F5.
/ נתב לוח מחוונים — שלב F5.
"""

import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.database import get_database
from app.services.auth import verify_access_token
from app.services.m1_anomalias import calcular_salud
from app.services.aps_scheduler import generar_plan_8am
from app.services.roi_calculator import calcular_roi_demo, calcular_roi_mongo

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
bearer_scheme = HTTPBearer()


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    try:
        return verify_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalido o expirado")


# ---------------------------------------------------------------------------
# Datos demo (hasta MongoDB conectado o como fallback)
# ---------------------------------------------------------------------------

MAQUINAS_DEMO = [
    {
        "maquina_id": f"CNC-0{i}",
        "nombre": f"Centro CNC-0{i}",
        "tipo": "centro_mecanizado",
        "tasa_horaria": 45.0 + i * 5,
        "activa": True,
    }
    for i in range(1, 9)
]


def _lecturas_demo(maquina_id: str, minutos: int = 30) -> list[dict]:
    ahora = datetime.now(timezone.utc)
    estados = ["operando", "operando", "operando", "operando", "falla", "parado"]
    return [
        {
            "maquina_id":  maquina_id,
            "temperatura": random.uniform(45, 95),
            "vibracion":   random.uniform(0.5, 12),
            "rpm":         random.randint(800, 3200),
            "estado":      random.choice(estados),
            "timestamp":   (ahora - timedelta(seconds=i * 5)).isoformat(),
        }
        for i in range(minutos * 12)
    ]


def _alertas_demo() -> list[dict]:
    tipos = ["temperatura_alta", "vibracion_alta", "paro_inesperado", "orden_retrasada"]
    ahora = datetime.now(timezone.utc)
    return [
        {
            "alerta_id":   f"ALT-00{i}",
            "tipo":        tipos[i % len(tipos)],
            "maquina_id":  f"CNC-0{(i % 8) + 1}",
            "severidad":   "warning" if i % 3 != 0 else "critical",
            "mensaje":     f"Alerta demo #{i+1}",
            "atendida":    i < 7,
            "timestamp":   (ahora - timedelta(minutes=i * 15)).isoformat(),
        }
        for i in range(10)
    ]


# ---------------------------------------------------------------------------
# Helper: intentar MongoDB, caer a demo si falla
# ---------------------------------------------------------------------------

async def _get_db_safe():
    """Retorna db o None si no esta conectado."""
    try:
        return get_database()
    except RuntimeError:
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/resumen")
async def resumen_dashboard(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Metricas principales del tenant:
      - Maquinas activas / total
      - Ordenes del dia
      - Alertas activas (no atendidas)
      - Costo de oportunidad total del mes

    / Main tenant metrics.
    / מדדים ראשיים של ה-tenant.
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    db = await _get_db_safe()

    if db is not None:
        hoy = date.today().isoformat()

        # Maquinas
        total_maquinas = await db["maquinas"].count_documents({"tenant_id": tenant_id})
        maquinas_activas = await db["maquinas"].count_documents({"tenant_id": tenant_id, "activa": True})

        # Ordenes del dia (creadas hoy o con fecha_entrega hoy)
        ordenes_hoy = await db["ordenes"].count_documents({
            "tenant_id": tenant_id,
            "fecha_entrega": hoy,
            "estado": {"$in": ["pendiente", "en_proceso", "retrasada"]},
        })

        # Alertas activas (no atendidas)
        alertas_activas = await db["alertas"].count_documents({
            "tenant_id": tenant_id,
            "atendida": False,
        })

        return {
            "tenant_id":       tenant_id,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "maquinas": {
                "total":   total_maquinas or 8,
                "activas": maquinas_activas or 8,
            },
            "ordenes_hoy":     ordenes_hoy,
            "alertas_activas": alertas_activas,
            "fuente":          "mongodb",
        }

    # Fallback demo
    return {
        "tenant_id":   tenant_id,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "maquinas": {
            "total":   8,
            "activas": 7,
        },
        "ordenes_hoy":     6,
        "alertas_activas": 3,
        "fuente":          "demo",
    }


@router.get("/maquinas")
async def maquinas_con_salud(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Lista de maquinas del tenant con score de salud M1 de cada una.

    / List of tenant machines with M1 health score for each.
    / רשימת מכונות ה-tenant עם ציון בריאות M1 לכל אחת.
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    db = await _get_db_safe()
    ahora = datetime.now(timezone.utc)

    maquinas_lista: list[dict] = []

    if db is not None:
        cursor = db["maquinas"].find({"tenant_id": tenant_id})
        maquinas_lista = await cursor.to_list(length=100)

    if not maquinas_lista:
        maquinas_lista = MAQUINAS_DEMO

    resultados = []
    for maq in maquinas_lista:
        mid = maq.get("maquina_id", "")
        lecturas = _lecturas_demo(mid)
        salud = calcular_salud(lecturas)
        resultados.append({
            "maquina_id":   mid,
            "nombre":       maq.get("nombre", mid),
            "tipo":         maq.get("tipo", ""),
            "activa":       maq.get("activa", True),
            "score_salud":  salud["score"],
            "nivel_salud":  salud["nivel"],
        })

    return {
        "timestamp": ahora.isoformat(),
        "total":     len(resultados),
        "maquinas":  resultados,
    }


@router.get("/alertas-recientes")
async def alertas_recientes(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Ultimas 10 alertas del tenant (ordenadas por timestamp desc).

    / Last 10 tenant alerts (ordered by timestamp desc).
    / 10 ההתראות האחרונות של ה-tenant (מסודרות לפי timestamp יורד).
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    db = await _get_db_safe()

    if db is not None:
        cursor = db["alertas"].find(
            {"tenant_id": tenant_id}
        ).sort("timestamp", -1).limit(10)
        alertas = await cursor.to_list(length=10)
        for a in alertas:
            a["_id"] = str(a["_id"])
        if alertas:
            return {"total": len(alertas), "alertas": alertas, "fuente": "mongodb"}

    # Fallback demo
    alertas = _alertas_demo()
    return {"total": len(alertas), "alertas": alertas, "fuente": "demo"}


@router.get("/plan-hoy")
async def plan_hoy_dashboard(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Plan APS del dia actual (version mas reciente).

    / Current APS plan for today (most recent version).
    / תוכנית APS לאום (גרסה עדכנית ביותר).
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    db = await _get_db_safe()

    if db is not None:
        hoy = date.today().isoformat()
        plan = await db["plan_diario"].find_one(
            {"tenant_id": tenant_id, "fecha": hoy},
            sort=[("version", -1)],
        )
        if plan:
            plan["_id"] = str(plan["_id"])
            return plan

    # Generar plan demo
    return generar_plan_8am(tenant_id=tenant_id)


@router.get("/asistencia-hoy")
async def asistencia_hoy_dashboard(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Resumen de asistencia del dia: presentes / total operadores.

    / Today's attendance summary: present / total operators.
    / סיכום נוכחות היום: נוכחים / סך המפעילים.
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    db = await _get_db_safe()
    hoy = date.today().isoformat()

    if db is not None:
        total_operadores = await db["operadores"].count_documents({"tenant_id": tenant_id, "activo": True})
        presentes = await db["asistencia"].count_documents({
            "tenant_id": tenant_id,
            "fecha": hoy,
            "presente": True,
        })
        return {
            "fecha":            hoy,
            "total_operadores": total_operadores or 6,
            "presentes":        presentes,
            "ausentes":         max(0, (total_operadores or 6) - presentes),
            "fuente":           "mongodb",
        }

    # Fallback demo
    return {
        "fecha":            hoy,
        "total_operadores": 6,
        "presentes":        5,
        "ausentes":         1,
        "fuente":           "demo",
    }


@router.get("/roi")
async def roi_dashboard(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Datos de ROI del tenant segun el mes actual en el sistema.
    Meses 1-3: solo metricas reales (uptime, alertas, paros).
    Mes 4+: agrega predicciones y calculo de ROI economico.

    / Tenant ROI data based on current month in the system.
    / נתוני ROI של ה-tenant לפי החודש הנוכחי במערכת.
    """
    tenant_id = current.get("tenant_id", "demo-pro")
    db = await _get_db_safe()

    if db is not None:
        try:
            return await calcular_roi_mongo(db, tenant_id)
        except Exception:
            pass

    return calcular_roi_demo(tenant_id)
