"""
Triggers de Re-planificacion APS (Fase F4).

3 eventos que disparan re-planificacion automatica:
  Trigger 1: PARO DE MAQUINA  -> reasignar ordenes a otras maquinas
  Trigger 2: ORDEN URGENTE    -> insertar con maxima prioridad
  Trigger 3: MAQUINA RECUPERADA -> redistribuir carga para balancear

Anti-flood: maximo 1 re-planificacion por minuto.
Si llegan 5 eventos en 30 seg, solo procesa una vez.

/ APS Re-planning Triggers (Phase F4).
/ טריגרים לתכנון מחדש APS (שלב F4).
"""

import time
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.services.aps_engine import (
    generar_plan_diario,
    guardar_plan_mongo,
    obtener_plan_actual,
    siguiente_version,
)
from app.services.aps_scheduler import (
    ASISTENCIA_DEMO,
    MAQUINAS_DEMO,
    ORDENES_DEMO,
)


# ---------------------------------------------------------------------------
# Anti-flood: maximo 1 re-planificacion por minuto
# ---------------------------------------------------------------------------

_ultimo_replan: dict[str, float] = {}   # tenant_id -> timestamp ultima re-planificacion
ANTIFLOOD_SEGUNDOS = 60


def _puede_replanificar(tenant_id: str) -> bool:
    """
    Verifica si paso suficiente tiempo desde la ultima re-planificacion.
    Anti-flood: maximo 1 por minuto.

    / Checks if enough time has passed since the last re-planning.
    / בודק אם עבר מספיק זמן מאז התכנון מחדש האחרון.
    """
    ahora = time.time()
    ultimo = _ultimo_replan.get(tenant_id, 0)
    return (ahora - ultimo) >= ANTIFLOOD_SEGUNDOS


def _registrar_replanificacion(tenant_id: str) -> None:
    """Registra el timestamp de la re-planificacion."""
    _ultimo_replan[tenant_id] = time.time()


def _anti_flood_status(tenant_id: str) -> dict:
    """Retorna info del anti-flood para respuestas API."""
    ahora = time.time()
    ultimo = _ultimo_replan.get(tenant_id, 0)
    segundos_restantes = max(0, ANTIFLOOD_SEGUNDOS - (ahora - ultimo))
    return {
        "anti_flood_activo": segundos_restantes > 0,
        "segundos_restantes": round(segundos_restantes, 1),
        "limite_segundos": ANTIFLOOD_SEGUNDOS,
    }


# ---------------------------------------------------------------------------
# Trigger 1: PARO DE MAQUINA
# ---------------------------------------------------------------------------

def trigger_paro_maquina(
    maquina_id: str,
    tenant_id: str = "demo-pro",
    ordenes: Optional[list[dict]] = None,
    maquinas: Optional[list[dict]] = None,
    asistencia: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """
    Cuando una maquina se para, reasigna sus ordenes a otras maquinas.
    La maquina parada se excluye del pool disponible.

    / When a machine stops, reassigns its orders to other machines.
    / כשמכונה עוצרת, מקצה מחדש את ההזמנות שלה למכונות אחרות.
    """
    if not _puede_replanificar(tenant_id):
        return {
            "replanificado": False,
            "motivo": "anti_flood",
            "mensaje": f"Re-planificacion bloqueada: esperar {ANTIFLOOD_SEGUNDOS}s entre eventos",
            **_anti_flood_status(tenant_id),
        }

    ordenes = ordenes or ORDENES_DEMO
    maquinas = maquinas or MAQUINAS_DEMO
    asistencia = asistencia or ASISTENCIA_DEMO

    # Excluir la maquina parada
    maquinas_activas = [m for m in maquinas if m["maquina_id"] != maquina_id]

    plan = generar_plan_diario(
        ordenes=ordenes,
        maquinas=maquinas_activas,
        asistencia=asistencia,
        tenant_id=tenant_id,
        version=99,   # Se sobrescribe con version real en MongoDB
        motivo=f"paro_maquina:{maquina_id}",
    )

    _registrar_replanificacion(tenant_id)

    return {
        "replanificado": True,
        "trigger": "paro_maquina",
        "maquina_afectada": maquina_id,
        "plan": plan,
        **_anti_flood_status(tenant_id),
    }


# Trigger 1 async (MongoDB)
async def trigger_paro_maquina_mongo(
    db,
    maquina_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Trigger de paro con datos reales de MongoDB.

    / Machine stop trigger with real MongoDB data.
    / טריגר עצירת מכונה עם נתונים אמיתיים ממונגו.
    """
    if not _puede_replanificar(tenant_id):
        return {
            "replanificado": False,
            "motivo": "anti_flood",
            **_anti_flood_status(tenant_id),
        }

    hoy = date.today()

    # Leer ordenes pendientes
    ordenes = await db["fabrisense_ordenes"].find({
        "tenant_id": tenant_id,
        "estado": {"$in": ["pendiente", "retrasada", "en_proceso"]},
    }).to_list(500)

    # Maquinas activas EXCEPTO la parada
    maquinas = await db["machines"].find({
        "tenant_id": tenant_id,
        "activa": True,
        "maquina_id": {"$ne": maquina_id},
    }).to_list(100)

    asistencia = await db["asistencia"].find({
        "tenant_id": tenant_id,
        "fecha": hoy.isoformat(),
    }).to_list(200)

    version = await siguiente_version(db, tenant_id)

    plan = generar_plan_diario(
        ordenes=ordenes,
        maquinas=maquinas,
        asistencia=asistencia,
        tenant_id=tenant_id,
        version=version,
        motivo=f"paro_maquina:{maquina_id}",
    )

    await guardar_plan_mongo(db, plan)
    _registrar_replanificacion(tenant_id)

    return {"replanificado": True, "trigger": "paro_maquina", "plan": plan}


# ---------------------------------------------------------------------------
# Trigger 2: ORDEN URGENTE
# ---------------------------------------------------------------------------

def trigger_orden_urgente(
    orden: dict,
    tenant_id: str = "demo-pro",
    ordenes: Optional[list[dict]] = None,
    maquinas: Optional[list[dict]] = None,
    asistencia: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """
    Cuando entra una orden urgente, la inserta con maxima prioridad
    y re-genera el plan completo.

    / When an urgent order arrives, inserts it with max priority and regenerates the plan.
    / כשהזמנה דחופה מגיעה, מכניס אותה בעדיפות מקסימלית ומייצר מחדש את התוכנית.
    """
    if not _puede_replanificar(tenant_id):
        return {
            "replanificado": False,
            "motivo": "anti_flood",
            "mensaje": f"Re-planificacion bloqueada: esperar {ANTIFLOOD_SEGUNDOS}s entre eventos",
            **_anti_flood_status(tenant_id),
        }

    ordenes = ordenes or list(ORDENES_DEMO)
    maquinas = maquinas or MAQUINAS_DEMO
    asistencia = asistencia or ASISTENCIA_DEMO

    # Forzar prioridad urgente en la orden nueva
    orden["prioridad"] = "urgente"
    orden["estado"] = "pendiente"

    # Agregar la orden urgente al pool
    ordenes_con_urgente = [orden] + ordenes

    plan = generar_plan_diario(
        ordenes=ordenes_con_urgente,
        maquinas=maquinas,
        asistencia=asistencia,
        tenant_id=tenant_id,
        version=99,
        motivo=f"orden_urgente:{orden.get('orden_id', 'nueva')}",
    )

    _registrar_replanificacion(tenant_id)

    return {
        "replanificado": True,
        "trigger": "orden_urgente",
        "orden_insertada": orden.get("orden_id", "nueva"),
        "plan": plan,
        **_anti_flood_status(tenant_id),
    }


# Trigger 2 async (MongoDB)
async def trigger_orden_urgente_mongo(
    db,
    orden: dict,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Trigger de orden urgente con datos reales de MongoDB.

    / Urgent order trigger with real MongoDB data.
    / טריגר הזמנה דחופה עם נתונים אמיתיים ממונגו.
    """
    if not _puede_replanificar(tenant_id):
        return {
            "replanificado": False,
            "motivo": "anti_flood",
            **_anti_flood_status(tenant_id),
        }

    hoy = date.today()

    # Guardar la orden urgente
    orden["prioridad"] = "urgente"
    orden["estado"] = "pendiente"
    orden["tenant_id"] = tenant_id
    await db["fabrisense_ordenes"].insert_one(orden)

    # Leer todas las ordenes pendientes (incluyendo la nueva)
    ordenes = await db["fabrisense_ordenes"].find({
        "tenant_id": tenant_id,
        "estado": {"$in": ["pendiente", "retrasada", "en_proceso"]},
    }).to_list(500)

    maquinas = await db["machines"].find({
        "tenant_id": tenant_id, "activa": True,
    }).to_list(100)

    asistencia = await db["asistencia"].find({
        "tenant_id": tenant_id, "fecha": hoy.isoformat(),
    }).to_list(200)

    version = await siguiente_version(db, tenant_id)

    plan = generar_plan_diario(
        ordenes=ordenes,
        maquinas=maquinas,
        asistencia=asistencia,
        tenant_id=tenant_id,
        version=version,
        motivo=f"orden_urgente:{orden.get('orden_id', 'nueva')}",
    )

    await guardar_plan_mongo(db, plan)
    _registrar_replanificacion(tenant_id)

    return {"replanificado": True, "trigger": "orden_urgente", "plan": plan}


# ---------------------------------------------------------------------------
# Trigger 3: MAQUINA RECUPERADA
# ---------------------------------------------------------------------------

def trigger_maquina_recuperada(
    maquina_id: str,
    tenant_id: str = "demo-pro",
    ordenes: Optional[list[dict]] = None,
    maquinas: Optional[list[dict]] = None,
    asistencia: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """
    Cuando una maquina vuelve a operar, redistribuye la carga
    para balancear entre todas las maquinas disponibles.

    / When a machine recovers, redistributes load to balance across all machines.
    / כשמכונה חוזרת לפעולה, מחלקת מחדש את העומס לאיזון בין כל המכונות.
    """
    if not _puede_replanificar(tenant_id):
        return {
            "replanificado": False,
            "motivo": "anti_flood",
            "mensaje": f"Re-planificacion bloqueada: esperar {ANTIFLOOD_SEGUNDOS}s entre eventos",
            **_anti_flood_status(tenant_id),
        }

    ordenes = ordenes or ORDENES_DEMO
    maquinas = maquinas or MAQUINAS_DEMO
    asistencia = asistencia or ASISTENCIA_DEMO

    # Asegurar que la maquina recuperada este en el pool
    maquinas_con_recuperada = list(maquinas)
    if not any(m["maquina_id"] == maquina_id for m in maquinas_con_recuperada):
        maquinas_con_recuperada.append({
            "maquina_id": maquina_id,
            "nombre": maquina_id,
            "tipo": "centro_mecanizado",
            "nivel": "intermedio",
            "tasa_horaria": 50.0,
            "activa": True,
            "tenant_id": tenant_id,
        })

    plan = generar_plan_diario(
        ordenes=ordenes,
        maquinas=maquinas_con_recuperada,
        asistencia=asistencia,
        tenant_id=tenant_id,
        version=99,
        motivo=f"maquina_recuperada:{maquina_id}",
    )

    _registrar_replanificacion(tenant_id)

    return {
        "replanificado": True,
        "trigger": "maquina_recuperada",
        "maquina_recuperada": maquina_id,
        "plan": plan,
        **_anti_flood_status(tenant_id),
    }


# Trigger 3 async (MongoDB)
async def trigger_maquina_recuperada_mongo(
    db,
    maquina_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Trigger de maquina recuperada con datos reales de MongoDB.

    / Machine recovered trigger with real MongoDB data.
    / טריגר החזרת מכונה לפעולה עם נתונים אמיתיים ממונגו.
    """
    if not _puede_replanificar(tenant_id):
        return {
            "replanificado": False,
            "motivo": "anti_flood",
            **_anti_flood_status(tenant_id),
        }

    hoy = date.today()

    # Marcar maquina como activa
    await db["machines"].update_one(
        {"maquina_id": maquina_id, "tenant_id": tenant_id},
        {"$set": {"activa": True}},
    )

    ordenes = await db["fabrisense_ordenes"].find({
        "tenant_id": tenant_id,
        "estado": {"$in": ["pendiente", "retrasada", "en_proceso"]},
    }).to_list(500)

    maquinas = await db["machines"].find({
        "tenant_id": tenant_id, "activa": True,
    }).to_list(100)

    asistencia = await db["asistencia"].find({
        "tenant_id": tenant_id, "fecha": hoy.isoformat(),
    }).to_list(200)

    version = await siguiente_version(db, tenant_id)

    plan = generar_plan_diario(
        ordenes=ordenes,
        maquinas=maquinas,
        asistencia=asistencia,
        tenant_id=tenant_id,
        version=version,
        motivo=f"maquina_recuperada:{maquina_id}",
    )

    await guardar_plan_mongo(db, plan)
    _registrar_replanificacion(tenant_id)

    return {"replanificado": True, "trigger": "maquina_recuperada", "plan": plan}
