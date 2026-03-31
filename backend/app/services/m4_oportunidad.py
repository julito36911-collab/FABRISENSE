"""
M4 — Costo de Oportunidad.

Calcula cuánto dinero se pierde por cada hora de paro de cada máquina
y genera un ranking de mayor a menor impacto económico.

Fórmula:
    costo_oportunidad = horas_paro * tasa_horaria * factor_oportunidad

Factor de oportunidad:
    1.5 → hay órdenes pendientes con fecha_entrega vencida (ya atrasadas)
    1.2 → hay órdenes pendientes con fecha_entrega en los próximos 3 días (urgencia)
    1.0 → sin presión de entregas

/ M4 — Opportunity Cost.
/ M4 — עלות הזדמנות.
"""

from datetime import date, datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Factores de oportunidad
# ---------------------------------------------------------------------------

FACTOR_ATRASADO  = 1.5    # órdenes ya vencidas
FACTOR_URGENTE   = 1.2    # órdenes a vencer en ≤3 días
FACTOR_NORMAL    = 1.0    # sin presión


def _factor_oportunidad(
    ordenes_pendientes: list[dict[str, Any]],
    hoy: date,
) -> tuple[float, str]:
    """
    Determina el factor de oportunidad basado en el estado de las órdenes.

    / Determines the opportunity factor based on order status.
    / קובע את גורם ההזדמנות על בסיס מצב ההזמנות.
    """
    if not ordenes_pendientes:
        return FACTOR_NORMAL, "sin_ordenes_pendientes"

    for orden in ordenes_pendientes:
        fecha_raw = orden.get("fecha_entrega")
        if not fecha_raw:
            continue
        try:
            if isinstance(fecha_raw, str):
                fecha = date.fromisoformat(fecha_raw)
            elif isinstance(fecha_raw, date):
                fecha = fecha_raw
            else:
                continue
        except ValueError:
            continue

        if fecha < hoy:
            return FACTOR_ATRASADO, "ordenes_vencidas"

    # ¿Hay órdenes a vencer en ≤3 días?
    for orden in ordenes_pendientes:
        fecha_raw = orden.get("fecha_entrega")
        if not fecha_raw:
            continue
        try:
            fecha = date.fromisoformat(str(fecha_raw))
        except ValueError:
            continue
        dias_restantes = (fecha - hoy).days
        if 0 <= dias_restantes <= 3:
            return FACTOR_URGENTE, "entrega_proxima"

    return FACTOR_NORMAL, "entregas_a_tiempo"


# ---------------------------------------------------------------------------
# Cálculo de costo de oportunidad — in-memory
# ---------------------------------------------------------------------------

def calcular_oportunidad_maquina(
    maquina: dict[str, Any],
    horas_paro: float,
    ordenes_pendientes: list[dict[str, Any]],
    hoy: Optional[date] = None,
) -> dict[str, Any]:
    """
    Calcula el costo de oportunidad de una máquina parada.

    Parámetros:
        maquina: dict con 'maquina_id' y 'tasa_horaria'
        horas_paro: horas que estuvo parada en el período
        ordenes_pendientes: órdenes asignadas a esta máquina con estado pendiente
        hoy: fecha de referencia (default: hoy)

    / Calculates the opportunity cost for a stopped machine.
    / מחסב את עלות ההזדמנות עבור מכונה שעצרה.
    """
    hoy = hoy or date.today()
    maquina_id   = maquina.get("maquina_id", "desconocida")
    tasa_horaria = float(maquina.get("tasa_horaria", 0.0))

    factor, razon = _factor_oportunidad(ordenes_pendientes, hoy)
    costo_oportunidad = round(horas_paro * tasa_horaria * factor, 2)

    ordenes_afectadas = [
        {
            "orden_id":      o.get("orden_id"),
            "producto":      o.get("producto"),
            "fecha_entrega": str(o.get("fecha_entrega", "")),
        }
        for o in ordenes_pendientes
    ]

    return {
        "maquina_id":          maquina_id,
        "tasa_horaria_usd":    tasa_horaria,
        "horas_paro":          round(horas_paro, 2),
        "factor_oportunidad":  factor,
        "razon_factor":        razon,
        "costo_oportunidad_usd": costo_oportunidad,
        "ordenes_afectadas":   ordenes_afectadas,
        "ordenes_pendientes_count": len(ordenes_pendientes),
    }


def ranking_oportunidad(
    resultados: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Genera ranking de máquinas de mayor a menor costo de oportunidad.

    / Generates a ranking of machines from highest to lowest opportunity cost.
    / יוצר דירוג של מכונות מהעלות הגבוהה לנמוכה ביותר של הזדמנות.
    """
    ranking = sorted(
        resultados,
        key=lambda r: r["costo_oportunidad_usd"],
        reverse=True,
    )

    total_perdida = sum(r["costo_oportunidad_usd"] for r in resultados)
    total_horas_paro = sum(r["horas_paro"] for r in resultados)
    criticos = [r for r in ranking if r["factor_oportunidad"] >= FACTOR_ATRASADO]

    return {
        "fecha_calculo":       date.today().isoformat(),
        "maquinas_analizadas": len(resultados),
        "total_perdida_usd":   round(total_perdida, 2),
        "total_horas_paro":    round(total_horas_paro, 2),
        "maquinas_criticas":   len(criticos),
        "ranking": [
            {
                "posicion":               i + 1,
                "maquina_id":             r["maquina_id"],
                "costo_oportunidad_usd":  r["costo_oportunidad_usd"],
                "horas_paro":             r["horas_paro"],
                "factor":                 r["factor_oportunidad"],
                "razon":                  r["razon_factor"],
                "ordenes_afectadas":      r["ordenes_pendientes_count"],
            }
            for i, r in enumerate(ranking)
        ],
        "detalle": resultados,
    }


# ---------------------------------------------------------------------------
# Consulta async MongoDB
# ---------------------------------------------------------------------------

from typing import Optional


async def calcular_oportunidad_mongo(
    db,
    maquina_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Lee datos de MongoDB para calcular el costo de oportunidad.

    / Reads MongoDB data to calculate opportunity cost.
    / קורא נתוני MongoDB לחישוב עלות הזדמנות.
    """
    from datetime import timedelta
    ahora = datetime.now(timezone.utc)
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    maquina = await db["machines"].find_one({"maquina_id": maquina_id, "tenant_id": tenant_id})
    if not maquina:
        maquina = {"maquina_id": maquina_id, "tasa_horaria": 0.0}

    # Lecturas del mes para calcular horas de paro
    cursor = db["sensor_data"].find({
        "maquina_id": maquina_id,
        "tenant_id":  tenant_id,
        "timestamp":  {"$gte": inicio_mes.isoformat()},
    })
    lecturas = await cursor.to_list(length=None)

    paradas = [r for r in lecturas if r.get("estado") in ("parado", "falla")]
    horas_paro = len(paradas) * 5.0 / 3600.0   # 5 seg por lectura

    # Órdenes pendientes asignadas a esta máquina
    cursor_ord = db["fabrisense_ordenes"].find({
        "maquina_id": maquina_id,
        "tenant_id":  tenant_id,
        "estado":     {"$in": ["pendiente", "en_proceso", "retrasada"]},
    })
    ordenes = await cursor_ord.to_list(length=None)

    return calcular_oportunidad_maquina(dict(maquina), horas_paro, ordenes)
