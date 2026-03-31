"""
M2 — Predicción de Degradación (Capa 1: Reglas).

Analiza la tendencia de vibración de los últimos 7 días mediante
regresión lineal simple (sin ML, sin Isolation Forest — eso es F9).

Si la pendiente es positiva y la proyección a 7 días supera el umbral
crítico, genera una alerta predictiva con estimado de días hasta falla.

/ M2 — Degradation Prediction (Layer 1: Rules).
/ M2 — חיזוי ירידת ביצועים (שכבה 1: כללים).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Regresión lineal simple (sin dependencias externas)
# ---------------------------------------------------------------------------

def _linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """
    Calcula pendiente (m) e intercepto (b) de la recta y = m*x + b.
    Retorna (0.0, promedio) si no hay suficientes puntos.

    / Calculates slope (m) and intercept (b) for y = m*x + b.
    / מחסב שיפוע (m) וחותכת (b) עבור y = m*x + b.
    """
    n = len(xs)
    if n < 2:
        promedio = sum(ys) / n if n == 1 else 0.0
        return 0.0, promedio

    sum_x   = sum(xs)
    sum_y   = sum(ys)
    sum_xy  = sum(x * y for x, y in zip(xs, ys))
    sum_x2  = sum(x * x for x in xs)

    denom = n * sum_x2 - sum_x ** 2
    if denom == 0:
        return 0.0, sum_y / n

    slope     = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def _dias_hasta_umbral(
    valor_actual: float,
    slope_por_dia: float,
    umbral: float,
) -> Optional[int]:
    """
    Estima cuántos días faltan para alcanzar el umbral con la tendencia actual.
    Retorna None si la tendencia no converge (slope ≤ 0 o ya superó umbral).

    / Estimates days until threshold is reached at current trend.
    / מעריך ימים עד להגעה לסף עם המגמה הנוכחית.
    """
    if slope_por_dia <= 0:
        return None
    if valor_actual >= umbral:
        return 0
    dias = (umbral - valor_actual) / slope_por_dia
    return max(1, round(dias))


# ---------------------------------------------------------------------------
# Análisis de tendencia — in-memory
# ---------------------------------------------------------------------------

def analizar_tendencia(
    lecturas: list[dict[str, Any]],
    maquina_id: str,
    umbral_critico_vibracion: float = 10.0,
    umbral_advertencia_vibracion: float = 5.0,
    ventana_proyeccion_dias: int = 7,
) -> dict[str, Any]:
    """
    Analiza la tendencia de vibración de una serie de lecturas.

    Parámetros:
        lecturas: lista de dicts con campos 'vibracion' y 'timestamp' (ISO str)
        maquina_id: identificador de la máquina
        umbral_critico_vibracion: mm/s que define falla inminente
        umbral_advertencia_vibracion: mm/s de advertencia
        ventana_proyeccion_dias: días hacia adelante para proyectar

    Retorna:
        {
          maquina_id, slope_por_dia, valor_actual, proyeccion_7d,
          tendencia: "estable" | "ascendente" | "descendente",
          alerta_predictiva: bool,
          dias_estimados_falla: int | None,
          mensaje: str,
          puntos_analizados: int,
        }

    / Analyzes vibration trend from a series of readings.
    / מנתח מגמת רטט מסדרת קריאות.
    """
    if not lecturas:
        return {
            "maquina_id": maquina_id,
            "slope_por_dia": 0.0,
            "valor_actual": 0.0,
            "proyeccion_7d": 0.0,
            "tendencia": "sin_datos",
            "alerta_predictiva": False,
            "dias_estimados_falla": None,
            "mensaje": "Sin datos suficientes para analizar tendencia",
            "puntos_analizados": 0,
        }

    # Ordenar por timestamp
    try:
        lecturas_ord = sorted(
            lecturas,
            key=lambda r: r.get("timestamp", ""),
        )
    except Exception:
        lecturas_ord = lecturas

    # Convertir timestamps a "días desde el primer registro" (eje X)
    try:
        t0_str = lecturas_ord[0].get("timestamp", "")
        t0 = datetime.fromisoformat(t0_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        t0 = datetime.now(timezone.utc) - timedelta(days=7)

    xs: list[float] = []
    ys: list[float] = []
    for r in lecturas_ord:
        try:
            ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
            dias = (ts - t0).total_seconds() / 86_400.0
            vib = float(r["vibracion"])
            xs.append(dias)
            ys.append(vib)
        except (KeyError, ValueError, TypeError):
            continue

    if len(xs) < 2:
        return {
            "maquina_id": maquina_id,
            "slope_por_dia": 0.0,
            "valor_actual": ys[0] if ys else 0.0,
            "proyeccion_7d": ys[0] if ys else 0.0,
            "tendencia": "sin_datos",
            "alerta_predictiva": False,
            "dias_estimados_falla": None,
            "mensaje": "Puntos insuficientes para regresión lineal (mínimo 2)",
            "puntos_analizados": len(xs),
        }

    slope, intercept = _linear_regression(xs, ys)

    # Valor actual (último punto de la regresión)
    x_actual = xs[-1]
    valor_actual = round(intercept + slope * x_actual, 3)

    # Proyección a N días
    x_futuro = x_actual + ventana_proyeccion_dias
    proyeccion = round(intercept + slope * x_futuro, 3)

    # Determinar tendencia
    SLOPE_THRESHOLD = 0.05   # mm/s por día — umbral mínimo para declarar tendencia
    if slope > SLOPE_THRESHOLD:
        tendencia = "ascendente"
    elif slope < -SLOPE_THRESHOLD:
        tendencia = "descendente"
    else:
        tendencia = "estable"

    # Alerta predictiva: tendencia ascendente Y proyección supera umbral crítico
    alerta = tendencia == "ascendente" and proyeccion >= umbral_critico_vibracion

    dias_falla = None
    mensaje = ""
    if alerta:
        dias_falla = _dias_hasta_umbral(valor_actual, slope, umbral_critico_vibracion)
        if dias_falla == 0:
            mensaje = (
                f"Máquina {maquina_id}: vibración ha superado el umbral crítico "
                f"({valor_actual:.2f} mm/s ≥ {umbral_critico_vibracion} mm/s). "
                f"Se recomienda parar para mantenimiento."
            )
        else:
            mensaje = (
                f"Máquina {maquina_id}: vibración en tendencia ascendente "
                f"(+{slope:.3f} mm/s/día). "
                f"Estimado de falla en {dias_falla} día{'s' if dias_falla != 1 else ''}."
            )
    elif tendencia == "ascendente":
        mensaje = (
            f"Máquina {maquina_id}: vibración en tendencia ascendente "
            f"(+{slope:.3f} mm/s/día). Proyección a {ventana_proyeccion_dias} días: "
            f"{proyeccion:.2f} mm/s — dentro del rango tolerable."
        )
    else:
        mensaje = (
            f"Máquina {maquina_id}: vibración estable "
            f"({valor_actual:.2f} mm/s, slope={slope:+.3f} mm/s/día)."
        )

    return {
        "maquina_id":           maquina_id,
        "slope_por_dia":        round(slope, 4),
        "valor_actual":         valor_actual,
        "proyeccion_7d":        proyeccion,
        "tendencia":            tendencia,
        "alerta_predictiva":    alerta,
        "dias_estimados_falla": dias_falla,
        "mensaje":              mensaje,
        "puntos_analizados":    len(xs),
        "umbral_critico":       umbral_critico_vibracion,
    }


# ---------------------------------------------------------------------------
# Consulta async MongoDB
# ---------------------------------------------------------------------------

async def analizar_tendencia_mongo(
    db,
    maquina_id: str,
    tenant_id: str,
    dias: int = 7,
) -> dict[str, Any]:
    """
    Lee los últimos N días de sensor_data de MongoDB y analiza la tendencia.

    / Reads last N days of sensor_data from MongoDB and analyzes the trend.
    / קורא N ימים אחרונים של sensor_data ממונגו ומנתח את המגמה.
    """
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    cursor = db["sensor_data"].find({
        "maquina_id": maquina_id,
        "tenant_id":  tenant_id,
        "timestamp":  {"$gte": desde.isoformat()},
    }).sort("timestamp", 1)
    lecturas = await cursor.to_list(length=None)
    return analizar_tendencia(lecturas, maquina_id)
