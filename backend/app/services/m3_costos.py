"""
M3 — Costo por Hora Real.

Calcula el costo operativo real de cada máquina en el mes actual,
comparándolo contra el costo presupuestado.

Fórmula:
    costo_real = (horas_operando * tasa_horaria) + (horas_parada * costo_paro)

Donde costo_paro se define como 0.3 * tasa_horaria por defecto
(mantenimiento, amortización, overhead).

/ M3 — Real Cost per Hour.
/ M3 — עלות שעתית אמיתית.
"""

from datetime import datetime, timezone
from typing import Any


# Costo de hora parada como fracción de tasa_horaria (overhead / amortización)
FACTOR_COSTO_PARO = 0.30


# ---------------------------------------------------------------------------
# Cálculo de horas por estado
# ---------------------------------------------------------------------------

def _calcular_horas_por_estado(lecturas: list[dict]) -> dict[str, float]:
    """
    Estima horas en cada estado a partir de lecturas de sensor_data.
    Asume que cada lectura representa un intervalo de 5 segundos (simulador).
    Con datos reales, usar la diferencia real entre timestamps.

    / Estimates hours per state from sensor_data readings.
    / מעריך שעות לפי מצב מקריאות sensor_data.
    """
    conteo = {"operando": 0, "parado": 0, "falla": 0, "urgente": 0}
    for r in lecturas:
        estado = r.get("estado", "operando")
        conteo[estado] = conteo.get(estado, 0) + 1

    total = sum(conteo.values()) or 1
    # Cada lectura = 5 seg → total * 5 / 3600 = horas
    segundos_por_lectura = 5.0
    return {
        estado: round(n * segundos_por_lectura / 3600.0, 3)
        for estado, n in conteo.items()
    }


# ---------------------------------------------------------------------------
# Cálculo de costo — in-memory
# ---------------------------------------------------------------------------

def calcular_costo_maquina(
    maquina: dict[str, Any],
    lecturas: list[dict[str, Any]],
    presupuesto_mensual: float = 0.0,
) -> dict[str, Any]:
    """
    Calcula el costo real del mes actual para una máquina.

    Parámetros:
        maquina: dict con al menos 'maquina_id' y 'tasa_horaria'
        lecturas: lecturas de sensor_data del mes actual
        presupuesto_mensual: costo presupuestado en USD (0 = sin presupuesto)

    Retorna dict con desglose de costos.

    / Calculates the real cost for the current month for a machine.
    / מחסב את העלות האמיתית לחודש הנוכחי עבור מכונה.
    """
    maquina_id    = maquina.get("maquina_id", "desconocida")
    tasa_horaria  = float(maquina.get("tasa_horaria", 0.0))
    costo_paro_h  = tasa_horaria * FACTOR_COSTO_PARO

    horas = _calcular_horas_por_estado(lecturas)
    horas_operando = horas.get("operando", 0.0) + horas.get("urgente", 0.0)
    horas_parada   = horas.get("parado", 0.0) + horas.get("falla", 0.0)
    horas_totales  = horas_operando + horas_parada

    costo_operacion = round(horas_operando * tasa_horaria, 2)
    costo_paro      = round(horas_parada   * costo_paro_h, 2)
    costo_real      = round(costo_operacion + costo_paro, 2)

    eficiencia_pct = round(
        horas_operando / horas_totales * 100 if horas_totales > 0 else 0.0, 1
    )

    variacion_vs_presupuesto = None
    variacion_pct = None
    if presupuesto_mensual > 0:
        variacion_vs_presupuesto = round(costo_real - presupuesto_mensual, 2)
        variacion_pct = round(variacion_vs_presupuesto / presupuesto_mensual * 100, 1)

    return {
        "maquina_id":       maquina_id,
        "tasa_horaria_usd": tasa_horaria,
        "periodo":          _periodo_actual(),
        "horas": {
            "operando": horas_operando,
            "parada":   horas_parada,
            "total":    horas_totales,
        },
        "costos": {
            "operacion_usd": costo_operacion,
            "paro_usd":      costo_paro,
            "total_usd":     costo_real,
        },
        "eficiencia_pct":              eficiencia_pct,
        "presupuesto_usd":             presupuesto_mensual,
        "variacion_vs_presupuesto_usd": variacion_vs_presupuesto,
        "variacion_pct":               variacion_pct,
        "lecturas_analizadas":         len(lecturas),
    }


def resumen_costos(resultados: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Agrega los costos de todas las máquinas en un resumen del tenant.

    / Aggregates costs from all machines into a tenant summary.
    / מאגד עלויות מכל המכונות לסיכום ה-tenant.
    """
    total_operacion = sum(r["costos"]["operacion_usd"] for r in resultados)
    total_paro      = sum(r["costos"]["paro_usd"]      for r in resultados)
    total_real      = sum(r["costos"]["total_usd"]     for r in resultados)
    total_presupuesto = sum(r.get("presupuesto_usd", 0) or 0 for r in resultados)

    eficiencia_promedio = (
        sum(r["eficiencia_pct"] for r in resultados) / len(resultados)
        if resultados else 0.0
    )

    ranking = sorted(resultados, key=lambda r: r["costos"]["total_usd"], reverse=True)

    return {
        "periodo":               _periodo_actual(),
        "maquinas_analizadas":   len(resultados),
        "totales_usd": {
            "operacion":   round(total_operacion, 2),
            "paro":        round(total_paro, 2),
            "costo_real":  round(total_real, 2),
            "presupuesto": round(total_presupuesto, 2),
        },
        "eficiencia_promedio_pct": round(eficiencia_promedio, 1),
        "ranking_por_costo": [
            {"maquina_id": r["maquina_id"], "total_usd": r["costos"]["total_usd"]}
            for r in ranking
        ],
        "detalle": resultados,
    }


# ---------------------------------------------------------------------------
# Consulta async MongoDB
# ---------------------------------------------------------------------------

async def calcular_costo_mongo(
    db,
    maquina_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Lee sensor_data del mes actual y datos de la máquina de MongoDB.

    / Reads current month's sensor_data and machine data from MongoDB.
    / קורא sensor_data של החודש הנוכחי ונתוני מכונה ממונגו.
    """
    ahora  = datetime.now(timezone.utc)
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    maquina = await db["machines"].find_one({"maquina_id": maquina_id, "tenant_id": tenant_id})
    if not maquina:
        maquina = {"maquina_id": maquina_id, "tasa_horaria": 0.0}

    cursor = db["sensor_data"].find({
        "maquina_id": maquina_id,
        "tenant_id":  tenant_id,
        "timestamp":  {"$gte": inicio_mes.isoformat()},
    })
    lecturas = await cursor.to_list(length=None)

    config = await db["config_cliente"].find_one({
        "maquina_id": maquina_id, "tenant_id": tenant_id
    })
    presupuesto = config.get("presupuesto_mensual_usd", 0.0) if config else 0.0

    return calcular_costo_maquina(dict(maquina), lecturas, presupuesto)


def _periodo_actual() -> str:
    ahora = datetime.now(timezone.utc)
    return ahora.strftime("%Y-%m")
