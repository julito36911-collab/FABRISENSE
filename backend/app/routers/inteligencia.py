"""
Router de Inteligencia Operacional — Fase F3.

Módulos:
  M1 — Detección de anomalías (score de salud)
  M2 — Predicción de degradación (tendencia de vibración)
  M3 — Costo por hora real vs presupuesto
  M4 — Costo de oportunidad y ranking

/ Operational Intelligence Router — Phase F3.
/ נתב אינטליגנציה תפעולית — שלב F3.
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.services.auth import verify_access_token
from app.services.m1_anomalias import calcular_salud
from app.services.m2_prediccion import analizar_tendencia
from app.services.m3_costos import calcular_costo_maquina, resumen_costos
from app.services.m4_oportunidad import calcular_oportunidad_maquina, ranking_oportunidad

router = APIRouter(prefix="/api", tags=["inteligencia"])
bearer_scheme = HTTPBearer()


def _current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    try:
        return verify_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


# ---------------------------------------------------------------------------
# Datos demo — se reemplazan con MongoDB cuando esté conectado
# ---------------------------------------------------------------------------

MAQUINAS_DEMO = [
    {"maquina_id": f"CNC-0{i}", "tasa_horaria": 45.0 + i * 5, "nombre": f"Centro CNC-0{i}"}
    for i in range(1, 9)
]


def _lecturas_demo(maquina_id: str, minutos: int = 30) -> list[dict]:
    """Genera lecturas simuladas para demo sin MongoDB."""
    import random
    ahora = datetime.now(timezone.utc)
    lecturas = []
    estados = ["operando", "operando", "operando", "operando", "falla", "parado"]
    for i in range(minutos * 12):   # 5 seg por lectura → 12 lecturas/min
        ts = ahora - timedelta(seconds=i * 5)
        estado = random.choice(estados)
        lecturas.append({
            "maquina_id":  maquina_id,
            "temperatura": random.uniform(45, 95) if estado != "parado" else 30.0,
            "vibracion":   random.uniform(0.5, 12) if estado != "parado" else 0.0,
            "rpm":         random.randint(800, 3200) if estado == "operando" else 0,
            "estado":      estado,
            "timestamp":   ts.isoformat(),
        })
    return lecturas


def _lecturas_tendencia_demo(maquina_id: str, dias: int = 7) -> list[dict]:
    """Genera lecturas con tendencia ascendente de vibración para demo."""
    ahora = datetime.now(timezone.utc)
    lecturas = []
    base_vib = 3.0
    slope_diario = 0.8   # mm/s por día — tendencia clara
    intervalos = dias * 24 * 6   # lecturas cada 10 min
    for i in range(intervalos):
        ts = ahora - timedelta(minutes=(intervalos - i) * 10)
        dias_transcurridos = i * 10 / 1440.0
        vib = base_vib + slope_diario * dias_transcurridos + random.uniform(-0.3, 0.3)
        lecturas.append({
            "maquina_id": maquina_id,
            "vibracion":  max(0.1, round(vib, 3)),
            "timestamp":  ts.isoformat(),
        })
    return lecturas


def _ordenes_demo(maquina_id: str) -> list[dict]:
    from datetime import date, timedelta
    hoy = date.today()
    return [
        {
            "orden_id":      f"ORD-{maquina_id}-001",
            "producto":      "Pieza A-320",
            "fecha_entrega": (hoy - timedelta(days=1)).isoformat(),  # vencida
            "estado":        "pendiente",
        },
        {
            "orden_id":      f"ORD-{maquina_id}-002",
            "producto":      "Pieza B-100",
            "fecha_entrega": (hoy + timedelta(days=2)).isoformat(),
            "estado":        "en_proceso",
        },
    ]


# ---------------------------------------------------------------------------
# M1 — Salud de máquinas
# ---------------------------------------------------------------------------

@router.get("/maquina/{maquina_id}/salud")
async def salud_maquina(
    maquina_id: str,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Score de salud actual (0-100) de una máquina con detalle por variable.
    100 = perfectamente normal, 0 = crítico.

    / Current health score (0-100) of a machine with per-variable detail.
    / ציון בריאות נוכחי (0-100) של מכונה עם פירוט לפי משתנה.
    """
    lecturas = _lecturas_demo(maquina_id)
    resultado = calcular_salud(lecturas)
    resultado["maquina_id"] = maquina_id
    resultado["timestamp"] = datetime.now(timezone.utc).isoformat()
    return resultado


@router.get("/maquinas/salud")
async def salud_todas_maquinas(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Resumen de salud de todas las máquinas del tenant.
    Incluye score global y distribución por nivel.

    / Health summary of all tenant machines.
    / סיכום בריאות של כל מכונות ה-tenant.
    """
    resultados = []
    for maq in MAQUINAS_DEMO:
        mid = maq["maquina_id"]
        lecturas = _lecturas_demo(mid)
        r = calcular_salud(lecturas)
        r["maquina_id"] = mid
        resultados.append(r)

    niveles = {"normal": 0, "advertencia": 0, "critico": 0, "sin_datos": 0}
    for r in resultados:
        niveles[r.get("nivel", "sin_datos")] = niveles.get(r.get("nivel", "sin_datos"), 0) + 1

    score_promedio = round(sum(r["score"] for r in resultados) / len(resultados), 1) if resultados else 0.0

    return {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "total_maquinas": len(resultados),
        "score_promedio": score_promedio,
        "distribucion":   niveles,
        "maquinas":       resultados,
    }


# ---------------------------------------------------------------------------
# M2 — Predicción de degradación
# ---------------------------------------------------------------------------

@router.get("/maquina/{maquina_id}/prediccion")
async def prediccion_maquina(
    maquina_id: str,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Análisis de tendencia de vibración (últimos 7 días) y alerta predictiva.
    Si la proyección a 7 días supera el umbral crítico → alerta con días estimados.

    / Vibration trend analysis (last 7 days) and predictive alert.
    / ניתוח מגמת רטט (7 ימים אחרונים) והתראה חיזויית.
    """
    lecturas = _lecturas_tendencia_demo(maquina_id)
    resultado = analizar_tendencia(lecturas, maquina_id)
    resultado["timestamp"] = datetime.now(timezone.utc).isoformat()
    return resultado


# ---------------------------------------------------------------------------
# M3 — Costos
# ---------------------------------------------------------------------------

@router.get("/maquina/{maquina_id}/costo")
async def costo_maquina(
    maquina_id: str,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Costo real del mes actual para una máquina (operación + paro)
    comparado contra el presupuesto.

    / Real cost for the current month (operation + downtime) vs budget.
    / עלות אמיתית לחודש הנוכחי (תפעול + עצירה) מול תקציב.
    """
    maquina = next((m for m in MAQUINAS_DEMO if m["maquina_id"] == maquina_id), None)
    if not maquina:
        raise HTTPException(status_code=404, detail="Máquina no encontrada")

    lecturas = _lecturas_demo(maquina_id, minutos=43200 // 5)   # simula 30 días aprox
    presupuesto = maquina["tasa_horaria"] * 200   # 200h presupuestadas como demo
    return calcular_costo_maquina(maquina, lecturas, presupuesto)


@router.get("/costos/resumen")
async def costos_resumen(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Resumen de costos del mes actual de todas las máquinas del tenant.
    Incluye ranking por mayor costo y variación vs presupuesto.

    / Current month cost summary for all tenant machines.
    / סיכום עלויות החודש הנוכחי עבור כל מכונות ה-tenant.
    """
    resultados = []
    for maq in MAQUINAS_DEMO:
        lecturas = _lecturas_demo(maq["maquina_id"], minutos=43200 // 5)
        presupuesto = maq["tasa_horaria"] * 200
        r = calcular_costo_maquina(maq, lecturas, presupuesto)
        resultados.append(r)
    return resumen_costos(resultados)


# ---------------------------------------------------------------------------
# M4 — Costo de oportunidad
# ---------------------------------------------------------------------------

@router.get("/maquina/{maquina_id}/oportunidad")
async def oportunidad_maquina(
    maquina_id: str,
    current: dict = Depends(_current_user),
) -> dict:
    """
    Costo de oportunidad de los paros de una máquina en el mes actual.
    Factor 1.5 si hay órdenes vencidas, 1.2 si hay entregas próximas, 1.0 normal.

    / Opportunity cost for machine downtime this month.
    / עלות הזדמנות עבור זמן עצירה של מכונה בחודש הנוכחי.
    """
    maquina = next((m for m in MAQUINAS_DEMO if m["maquina_id"] == maquina_id), None)
    if not maquina:
        raise HTTPException(status_code=404, detail="Máquina no encontrada")

    lecturas = _lecturas_demo(maquina_id, minutos=43200 // 5)
    paradas = [r for r in lecturas if r.get("estado") in ("parado", "falla")]
    horas_paro = len(paradas) * 5.0 / 3600.0

    ordenes = _ordenes_demo(maquina_id)
    return calcular_oportunidad_maquina(maquina, horas_paro, ordenes)


@router.get("/oportunidad/ranking")
async def ranking_oportunidad_tenants(
    current: dict = Depends(_current_user),
) -> dict:
    """
    Ranking de máquinas de mayor a menor costo de oportunidad por paros.
    Permite priorizar qué máquinas recuperar primero.

    / Ranking of machines by opportunity cost (highest to lowest).
    / דירוג מכונות לפי עלות הזדמנות (גבוהה לנמוכה).
    """
    resultados = []
    for maq in MAQUINAS_DEMO:
        lecturas = _lecturas_demo(maq["maquina_id"], minutos=43200 // 5)
        paradas = [r for r in lecturas if r.get("estado") in ("parado", "falla")]
        horas_paro = len(paradas) * 5.0 / 3600.0
        ordenes = _ordenes_demo(maq["maquina_id"])
        r = calcular_oportunidad_maquina(maq, horas_paro, ordenes)
        resultados.append(r)

    return ranking_oportunidad(resultados)
