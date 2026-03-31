"""
M1 — Detección de Anomalías (Módulo 1).

Calcula un "score de salud" de 0 a 100 por máquina a partir de los
últimos 30 minutos de datos de sensor. Sin ML — solo reglas de dominio.

Pesos:  temperatura 40% · vibración 40% · rpm 20%

Umbrales por defecto (configurables por máquina en colección config_cliente):
  Temperatura:  normal <60°C · advertencia 60-80°C · crítico ≥80°C
  Vibración:    normal <5 mm/s · advertencia 5-10 mm/s · crítico ≥10 mm/s
  RPM:          normal si dentro de ±15% del promedio histórico

/ M1 — Anomaly Detection.
/ M1 — זיהוי חריגות.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Umbrales por defecto
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "temperatura": {
        "normal_max":      60.0,
        "advertencia_max": 80.0,
    },
    "vibracion": {
        "normal_max":      5.0,
        "advertencia_max": 10.0,
    },
    "rpm_tolerance_pct": 15.0,   # ±%  respecto al promedio histórico
}


# ---------------------------------------------------------------------------
# Funciones de score por variable (0-100)
# ---------------------------------------------------------------------------

def _score_temperatura(valor: float, th: dict) -> tuple[float, str]:
    """
    Retorna (score 0-100, nivel).
    100 = perfectamente normal, 0 = crítico.

    / Returns (score 0-100, level).
    / מחזיר (ציון 0-100, רמה).
    """
    normal_max      = th.get("normal_max",      DEFAULT_THRESHOLDS["temperatura"]["normal_max"])
    advertencia_max = th.get("advertencia_max",  DEFAULT_THRESHOLDS["temperatura"]["advertencia_max"])

    if valor < 20:
        # Por debajo del mínimo operativo — sensor posiblemente apagado
        return 50.0, "advertencia"
    if valor <= normal_max:
        return 100.0, "normal"
    if valor <= advertencia_max:
        # Interpolación lineal: normal_max → 100, advertencia_max → 50
        ratio = (valor - normal_max) / (advertencia_max - normal_max)
        return round(100.0 - ratio * 50.0, 1), "advertencia"
    # Crítico: advertencia_max → 50, advertencia_max+20 → 0
    ratio = min((valor - advertencia_max) / 20.0, 1.0)
    return round(50.0 - ratio * 50.0, 1), "critico"


def _score_vibracion(valor: float, th: dict) -> tuple[float, str]:
    """
    / Returns (score 0-100, level).
    / מחזיר (ציון 0-100, רמה).
    """
    normal_max      = th.get("normal_max",      DEFAULT_THRESHOLDS["vibracion"]["normal_max"])
    advertencia_max = th.get("advertencia_max",  DEFAULT_THRESHOLDS["vibracion"]["advertencia_max"])

    if valor <= normal_max:
        return 100.0, "normal"
    if valor <= advertencia_max:
        ratio = (valor - normal_max) / (advertencia_max - normal_max)
        return round(100.0 - ratio * 50.0, 1), "advertencia"
    ratio = min((valor - advertencia_max) / 5.0, 1.0)
    return round(50.0 - ratio * 50.0, 1), "critico"


def _score_rpm(valor: int, promedio_historico: float, tolerancia_pct: float) -> tuple[float, str]:
    """
    Score de RPM basado en desviación porcentual respecto al promedio histórico.
    Si no hay promedio histórico, asume normal.

    / RPM score based on percentage deviation from historical average.
    / ציון RPM מבוסס על סטיית אחוזים מהממוצע ההיסטורי.
    """
    if promedio_historico <= 0:
        return 100.0, "normal"

    desviacion_pct = abs(valor - promedio_historico) / promedio_historico * 100.0
    if desviacion_pct <= tolerancia_pct:
        return 100.0, "normal"
    if desviacion_pct <= tolerancia_pct * 2:
        ratio = (desviacion_pct - tolerancia_pct) / tolerancia_pct
        return round(100.0 - ratio * 40.0, 1), "advertencia"
    return round(max(60.0 - (desviacion_pct - tolerancia_pct * 2) * 2, 0.0), 1), "critico"


# ---------------------------------------------------------------------------
# Función principal — in-memory (hasta MongoDB conectado)
# ---------------------------------------------------------------------------

def calcular_salud(
    lecturas: list[dict[str, Any]],
    thresholds: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Calcula el score de salud (0-100) a partir de una lista de lecturas recientes.

    Parámetros:
        lecturas: lista de dicts con campos temperatura, vibracion, rpm
        thresholds: umbrales configurables (usa DEFAULT_THRESHOLDS si None)

    Retorna:
        {
          score: float,
          nivel: "normal" | "advertencia" | "critico",
          detalle: { temperatura: {...}, vibracion: {...}, rpm: {...} },
          lecturas_analizadas: int,
          ventana_minutos: int,
        }

    / Calculates health score (0-100) from a list of recent readings.
    / מחסב ציון בריאות (0-100) מרשימת קריאות אחרונות.
    """
    th = thresholds or {}
    th_temp = th.get("temperatura", {})
    th_vib  = th.get("vibracion", {})
    tolerancia_rpm = th.get("rpm_tolerance_pct", DEFAULT_THRESHOLDS["rpm_tolerance_pct"])

    if not lecturas:
        return {
            "score": 0.0,
            "nivel": "sin_datos",
            "detalle": {},
            "lecturas_analizadas": 0,
            "ventana_minutos": 30,
        }

    # Promediar los últimos 30 min de lecturas
    temps  = [r["temperatura"] for r in lecturas if "temperatura" in r]
    vibs   = [r["vibracion"]   for r in lecturas if "vibracion" in r]
    rpms   = [r["rpm"]         for r in lecturas if "rpm" in r]

    avg_temp = sum(temps) / len(temps) if temps else 0.0
    avg_vib  = sum(vibs)  / len(vibs)  if vibs  else 0.0
    avg_rpm  = sum(rpms)  / len(rpms)  if rpms  else 0.0

    # Score y nivel por variable
    s_temp, n_temp = _score_temperatura(avg_temp, th_temp)
    s_vib,  n_vib  = _score_vibracion(avg_vib,   th_vib)
    s_rpm,  n_rpm  = _score_rpm(int(avg_rpm), avg_rpm, tolerancia_rpm)

    # Score ponderado: temp 40%, vib 40%, rpm 20%
    score = round(s_temp * 0.40 + s_vib * 0.40 + s_rpm * 0.20, 1)

    # Nivel global: el peor de los tres
    niveles_orden = ["normal", "advertencia", "critico"]
    niveles = [n_temp, n_vib, n_rpm]
    nivel_global = max(niveles, key=lambda n: niveles_orden.index(n) if n in niveles_orden else 0)

    return {
        "score": score,
        "nivel": nivel_global,
        "detalle": {
            "temperatura": {
                "promedio": round(avg_temp, 2),
                "score": s_temp,
                "nivel": n_temp,
                "unidad": "°C",
            },
            "vibracion": {
                "promedio": round(avg_vib, 3),
                "score": s_vib,
                "nivel": n_vib,
                "unidad": "mm/s",
            },
            "rpm": {
                "promedio": round(avg_rpm, 0),
                "score": s_rpm,
                "nivel": n_rpm,
                "unidad": "RPM",
            },
        },
        "lecturas_analizadas": len(lecturas),
        "ventana_minutos": 30,
    }


# ---------------------------------------------------------------------------
# Consulta async MongoDB (cuando esté conectado)
# ---------------------------------------------------------------------------

async def calcular_salud_mongo(
    db,
    maquina_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Lee los últimos 30 minutos de sensor_data de MongoDB y calcula la salud.
    Lee umbrales personalizados de la colección config_cliente.

    / Reads last 30 min of sensor_data from MongoDB and calculates health.
    / קורא 30 הדקות האחרונות של sensor_data ממונגו ומחסב בריאות.
    """
    desde = datetime.now(timezone.utc) - timedelta(minutes=30)

    # Leer lecturas
    cursor = db["sensor_data"].find({
        "maquina_id": maquina_id,
        "tenant_id":  tenant_id,
        "timestamp":  {"$gte": desde.isoformat()},
    }).sort("timestamp", -1).limit(200)
    lecturas = await cursor.to_list(length=200)

    # Leer umbrales personalizados (opcional)
    config = await db["config_cliente"].find_one({
        "maquina_id": maquina_id,
        "tenant_id":  tenant_id,
    })
    thresholds = config.get("thresholds", {}) if config else {}

    return calcular_salud(lecturas, thresholds)
