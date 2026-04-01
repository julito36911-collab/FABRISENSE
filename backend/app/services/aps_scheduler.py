"""
Planificador APS - Plan de las 8AM (Fase F4).

Genera el plan del dia automaticamente:
  - Lee ordenes pendientes + maquinas disponibles + asistencia del dia
  - Si un operador no llego, redistribuye su carga
  - Llama al motor APS greedy para generar el plan
  - Guarda el plan con timestamp y version (v1 = 8am, v2+ = re-planificaciones)

/ APS Scheduler - 8AM Daily Plan (Phase F4).
/ מתזמן APS - תוכנית יומית של 8 בבוקר (שלב F4).
"""

from datetime import date, datetime, timezone
from typing import Any, Optional

from app.services.aps_engine import (
    generar_plan_diario,
    guardar_plan_mongo,
    siguiente_version,
)


# ---------------------------------------------------------------------------
# Datos demo (hasta MongoDB conectado)
# ---------------------------------------------------------------------------

MAQUINAS_DEMO = [
    {
        "maquina_id": f"CNC-0{i}",
        "nombre": f"Centro CNC-0{i}",
        "tipo": "centro_mecanizado",
        "marca_cnc": "Fanuc",
        "nivel": ["basico", "intermedio", "avanzado"][i % 3],
        "tasa_horaria": 45.0 + i * 5,
        "activa": True,
        "tenant_id": "demo-pro",
    }
    for i in range(1, 9)
]

ORDENES_DEMO = [
    {
        "orden_id": "ORD-001",
        "cliente": "Metalurgica Norte",
        "producto": "Engranaje A-320",
        "cantidad": 50,
        "prioridad": "urgente",
        "fecha_entrega": date.today(),
        "estado": "pendiente",
        "fuente": "fabricontrol",
        "tenant_id": "demo-pro",
    },
    {
        "orden_id": "ORD-002",
        "cliente": "Autopartes Sur",
        "producto": "Eje B-100",
        "cantidad": 120,
        "prioridad": "alta",
        "fecha_entrega": date.today(),
        "estado": "pendiente",
        "fuente": "manual",
        "tenant_id": "demo-pro",
    },
    {
        "orden_id": "ORD-003",
        "cliente": "Fabrica Central",
        "producto": "Buje C-200",
        "cantidad": 200,
        "prioridad": "normal",
        "fecha_entrega": date.today(),
        "estado": "pendiente",
        "fuente": "csv",
        "tenant_id": "demo-pro",
    },
    {
        "orden_id": "ORD-004",
        "cliente": "Industrias Omega",
        "producto": "Placa D-50",
        "cantidad": 30,
        "prioridad": "baja",
        "fecha_entrega": date.today(),
        "estado": "pendiente",
        "fuente": "fabricontrol",
        "tenant_id": "demo-pro",
    },
    {
        "orden_id": "ORD-005",
        "cliente": "Precision Max",
        "producto": "Vastago E-80",
        "cantidad": 80,
        "prioridad": "normal",
        "fecha_entrega": date.today(),
        "estado": "pendiente",
        "fuente": "manual",
        "tenant_id": "demo-pro",
    },
    {
        "orden_id": "ORD-006",
        "cliente": "Torneados Express",
        "producto": "Casquillo F-150",
        "cantidad": 150,
        "prioridad": "alta",
        "fecha_entrega": date.today(),
        "estado": "retrasada",
        "fuente": "fabricontrol",
        "tenant_id": "demo-pro",
    },
]

ASISTENCIA_DEMO = [
    {"operador_id": f"OP-0{i}", "presente": True, "tenant_id": "demo-pro"}
    for i in range(1, 9)
]


# ---------------------------------------------------------------------------
# Generador de plan (in-memory demo)
# ---------------------------------------------------------------------------

def generar_plan_8am(
    tenant_id: str = "demo-pro",
    ordenes: Optional[list[dict]] = None,
    maquinas: Optional[list[dict]] = None,
    asistencia: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """
    Genera el plan de las 8AM con datos in-memory (demo).
    Si un operador no llego, su maquina no se incluye.

    / Generates the 8AM plan with in-memory data (demo).
    / מייצר את תוכנית 8 בבוקר עם נתונים בזיכרון (דמו).
    """
    ordenes = ordenes or ORDENES_DEMO
    maquinas = maquinas or MAQUINAS_DEMO
    asistencia = asistencia or ASISTENCIA_DEMO

    return generar_plan_diario(
        ordenes=ordenes,
        maquinas=maquinas,
        asistencia=asistencia,
        tenant_id=tenant_id,
        version=1,
        motivo="plan_8am",
    )


# ---------------------------------------------------------------------------
# Generador con MongoDB (async)
# ---------------------------------------------------------------------------

async def generar_plan_8am_mongo(
    db,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Genera el plan de las 8AM leyendo datos reales de MongoDB.
      1. Lee ordenes pendientes del tenant
      2. Lee maquinas activas del tenant
      3. Lee asistencia del dia
      4. Si un operador no llego, excluye sus maquinas
      5. Genera plan con motor greedy
      6. Guarda en coleccion plan_diario

    / Generates the 8AM plan reading real data from MongoDB.
    / מייצר את תוכנית 8 בבוקר עם קריאת נתונים ממונגו.
    """
    hoy = date.today()

    # 1. Ordenes pendientes
    cursor_ordenes = db["fabrisense_ordenes"].find({
        "tenant_id": tenant_id,
        "estado": {"$in": ["pendiente", "retrasada", "en_proceso"]},
    })
    ordenes = await cursor_ordenes.to_list(length=500)

    # 2. Maquinas activas
    cursor_maquinas = db["machines"].find({
        "tenant_id": tenant_id,
        "activa": True,
    })
    maquinas = await cursor_maquinas.to_list(length=100)

    # 3. Asistencia del dia
    cursor_asistencia = db["asistencia"].find({
        "tenant_id": tenant_id,
        "fecha": hoy.isoformat(),
    })
    asistencia = await cursor_asistencia.to_list(length=200)

    # 4. Filtrar maquinas de operadores ausentes
    operadores_ausentes = set()
    for a in asistencia:
        if not a.get("presente", False):
            operadores_ausentes.add(a.get("operador_id"))

    # Si hay operadores ausentes con maquinas asignadas, redistribuir
    # (las maquinas sin operador asignado siguen disponibles)
    maquinas_filtradas = []
    for m in maquinas:
        op_asignado = m.get("operador_id")
        if op_asignado and op_asignado in operadores_ausentes:
            continue  # Operador no llego, excluir maquina
        maquinas_filtradas.append(m)

    # 5. Calcular siguiente version
    version = await siguiente_version(db, tenant_id)

    # 6. Generar plan
    plan = generar_plan_diario(
        ordenes=ordenes,
        maquinas=maquinas_filtradas,
        asistencia=asistencia,
        tenant_id=tenant_id,
        version=version,
        motivo="plan_8am",
    )

    # 7. Guardar en MongoDB
    await guardar_plan_mongo(db, plan)

    return plan
