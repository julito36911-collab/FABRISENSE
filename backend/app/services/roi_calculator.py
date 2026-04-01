"""
ROI Calculator — Fase F5.

Calcula el retorno de inversion de FabriSense segun el mes del tenant.

Meses 1-3: SOLO datos reales medidos
  - Uptime % calculado de sensor_data
  - Alertas atendidas vs total
  - Cantidad de paros detectados

Mes 4+: Agrega predicciones verificadas
  - Dinero ahorrado por paros evitados
  - Horas productivas ganadas
  - ROI = ahorro / costo del sistema

/ ROI Calculator — Phase F5.
/ מחשבון ROI — שלב F5.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Parametros del sistema
# ---------------------------------------------------------------------------

COSTO_SISTEMA_MENSUAL_USD = 299.0        # Plan Pro mensual
AHORRO_POR_PARO_EVITADO_USD = 850.0      # Ahorro promedio por paro evitado (horas * tasa)
HORAS_POR_PARO_EVITADO = 4.0            # Horas productivas ganadas por paro evitado
TASA_PAROS_EVITADOS = 0.35              # 35% de paros potenciales evitados por alertas


# ---------------------------------------------------------------------------
# Funciones de calculo
# ---------------------------------------------------------------------------

def _calcular_uptime(lecturas: list[dict]) -> float:
    """
    Calcula uptime % de una lista de lecturas de sensor_data.

    / Calculates uptime % from sensor_data readings.
    / מחשב uptime % מקריאות sensor_data.
    """
    if not lecturas:
        return 0.0
    operando = sum(1 for r in lecturas if r.get("estado") == "operando")
    return round(operando / len(lecturas) * 100, 1)


def _mes_del_tenant(fecha_inicio_tenant: Optional[date]) -> int:
    """
    Calcula en que mes esta el tenant desde su inicio.
    Retorna 1 si no hay fecha de inicio.

    / Calculates which month the tenant is in since their start date.
    / מחשב באיזה חודש ה-tenant נמצא מאז תאריך התחלתו.
    """
    if not fecha_inicio_tenant:
        return 1
    hoy = date.today()
    meses = (hoy.year - fecha_inicio_tenant.year) * 12 + (hoy.month - fecha_inicio_tenant.month) + 1
    return max(1, meses)


# ---------------------------------------------------------------------------
# ROI in-memory (demo)
# ---------------------------------------------------------------------------

def calcular_roi_demo(tenant_id: str = "demo-pro") -> dict[str, Any]:
    """
    Calcula ROI con datos demo para tenants sin MongoDB conectado.

    / Calculates ROI with demo data for tenants without MongoDB.
    / מחשב ROI עם נתוני דמו עבור tenants ללא MongoDB.
    """
    # Simular datos del mes actual
    import random
    random.seed(42)  # seed fijo para demo consistente

    mes_actual = 3  # Demo en mes 3

    # Datos medidos (meses 1-3)
    uptime_pct = 87.4
    total_alertas = 42
    alertas_atendidas = 38
    paros_detectados = 7
    paros_en_tiempo = 6    # Paros detectados antes de falla mayor

    resultado = {
        "tenant_id":    tenant_id,
        "mes_en_sistema": mes_actual,
        "periodo":      date.today().strftime("%Y-%m"),
        "datos_reales": {
            "uptime_promedio_pct":     uptime_pct,
            "total_alertas":           total_alertas,
            "alertas_atendidas":       alertas_atendidas,
            "tasa_atencion_alertas_pct": round(alertas_atendidas / total_alertas * 100, 1) if total_alertas else 0,
            "paros_detectados":        paros_detectados,
            "paros_atendidos_a_tiempo": paros_en_tiempo,
        },
        "predicciones": None,
        "roi": None,
        "nota": "Meses 1-3: solo datos reales. ROI predictivo disponible desde mes 4.",
    }

    if mes_actual >= 4:
        paros_evitados = round(paros_detectados * TASA_PAROS_EVITADOS)
        ahorro_usd = round(paros_evitados * AHORRO_POR_PARO_EVITADO_USD, 2)
        horas_ganadas = round(paros_evitados * HORAS_POR_PARO_EVITADO, 1)
        costo_acumulado = COSTO_SISTEMA_MENSUAL_USD * mes_actual
        roi_pct = round((ahorro_usd - costo_acumulado) / costo_acumulado * 100, 1) if costo_acumulado > 0 else 0

        resultado["predicciones"] = {
            "paros_evitados_estimados": paros_evitados,
            "ahorro_por_paros_usd":     ahorro_usd,
            "horas_productivas_ganadas": horas_ganadas,
            "costo_sistema_acumulado_usd": costo_acumulado,
        }
        resultado["roi"] = {
            "roi_pct":           roi_pct,
            "ahorro_neto_usd":   round(ahorro_usd - costo_acumulado, 2),
            "payback_mes":       None if roi_pct <= 0 else round(costo_acumulado / (ahorro_usd / mes_actual), 1),
        }
        resultado["nota"] = f"Mes {mes_actual}: ROI calculado con datos reales + modelo predictivo."

    return resultado


# ---------------------------------------------------------------------------
# ROI con MongoDB (async)
# ---------------------------------------------------------------------------

async def calcular_roi_mongo(db, tenant_id: str) -> dict[str, Any]:
    """
    Calcula ROI leyendo datos reales de MongoDB.

    / Calculates ROI reading real data from MongoDB.
    / מחשב ROI עם קריאת נתונים אמיתיים ממונגו.
    """
    ahora = datetime.now(timezone.utc)
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Info del tenant para calcular mes en sistema
    tenant = await db["tenants"].find_one({"tenant_id": tenant_id})
    fecha_inicio_str = (tenant or {}).get("fecha_inicio")
    fecha_inicio = None
    if fecha_inicio_str:
        try:
            fecha_inicio = date.fromisoformat(str(fecha_inicio_str))
        except (ValueError, TypeError):
            pass
    mes_actual = _mes_del_tenant(fecha_inicio)

    # Lecturas del mes para uptime
    lecturas = await db["sensor_data"].find({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": inicio_mes.isoformat()},
    }).to_list(length=None)

    uptime_pct = _calcular_uptime(lecturas)

    # Alertas del mes
    total_alertas = await db["alertas"].count_documents({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": inicio_mes.isoformat()},
    })
    alertas_atendidas = await db["alertas"].count_documents({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": inicio_mes.isoformat()},
        "atendida": True,
    })

    # Paros del mes (desde historial_paros)
    paros_detectados = await db["historial_paros"].count_documents({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": inicio_mes.isoformat()},
    })
    paros_en_tiempo = await db["historial_paros"].count_documents({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": inicio_mes.isoformat()},
        "atendido_a_tiempo": True,
    })

    tasa_atencion = round(alertas_atendidas / total_alertas * 100, 1) if total_alertas else 0.0

    resultado: dict[str, Any] = {
        "tenant_id":      tenant_id,
        "mes_en_sistema": mes_actual,
        "periodo":        ahora.strftime("%Y-%m"),
        "datos_reales": {
            "uptime_promedio_pct":        uptime_pct,
            "total_alertas":              total_alertas,
            "alertas_atendidas":          alertas_atendidas,
            "tasa_atencion_alertas_pct":  tasa_atencion,
            "paros_detectados":           paros_detectados,
            "paros_atendidos_a_tiempo":   paros_en_tiempo,
        },
        "predicciones": None,
        "roi": None,
        "nota": "Meses 1-3: solo datos reales. ROI predictivo disponible desde mes 4.",
    }

    if mes_actual >= 4:
        paros_evitados = round(paros_detectados * TASA_PAROS_EVITADOS)
        ahorro_usd = round(paros_evitados * AHORRO_POR_PARO_EVITADO_USD, 2)
        horas_ganadas = round(paros_evitados * HORAS_POR_PARO_EVITADO, 1)
        costo_acumulado = COSTO_SISTEMA_MENSUAL_USD * mes_actual
        roi_pct = round((ahorro_usd - costo_acumulado) / costo_acumulado * 100, 1) if costo_acumulado > 0 else 0

        resultado["predicciones"] = {
            "paros_evitados_estimados":    paros_evitados,
            "ahorro_por_paros_usd":        ahorro_usd,
            "horas_productivas_ganadas":   horas_ganadas,
            "costo_sistema_acumulado_usd": costo_acumulado,
        }
        resultado["roi"] = {
            "roi_pct":         roi_pct,
            "ahorro_neto_usd": round(ahorro_usd - costo_acumulado, 2),
            "payback_mes":     None if roi_pct <= 0 else round(costo_acumulado / (ahorro_usd / mes_actual), 1),
        }
        resultado["nota"] = f"Mes {mes_actual}: ROI calculado con datos reales + modelo predictivo."

    return resultado
