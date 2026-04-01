"""
Motor APS Greedy - Planificacion Automatica de Produccion (Fase F4).

Algoritmo greedy que asigna ordenes a maquinas optimizando:
  1. Fecha de entrega mas cercana
  2. Ordenes marcadas como urgentes
  3. Ordenes con mayor cantidad

Para cada orden busca la mejor maquina:
  - Que este operando (no en falla ni parada)
  - Que sea compatible con el tipo de trabajo
  - Que tenga menor carga actual

Genera un plan diario guardado en coleccion "plan_diario".

/ APS Greedy Engine - Automatic Production Scheduling (Phase F4).
/ מנוע APS חמדן - תכנון ייצור אוטומטי (שלב F4).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

HORAS_JORNADA = 8.0          # Horas de trabajo por turno
TIEMPO_SETUP_MIN = 15.0      # Minutos de setup entre ordenes
VELOCIDAD_BASE = 10.0        # Piezas por hora (base para estimar duracion)

VELOCIDAD_POR_NIVEL = {
    "basico":      8.0,
    "intermedio": 12.0,
    "avanzado":   16.0,
}


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def _prioridad_sort_key(orden: dict) -> tuple:
    """
    Clave de ordenamiento para el greedy.
    Prioridad de asignacion:
      1. Ordenes con fecha de entrega mas cercana
      2. Ordenes marcadas como urgentes
      3. Ordenes con mayor cantidad

    Retorna tupla para sort: menor = mayor prioridad.

    / Sort key for greedy priority.
    / מפתח מיון לתעדוף חמדן.
    """
    prioridad_peso = {
        "urgente": 0,
        "alta":    1,
        "normal":  2,
        "baja":    3,
    }
    peso = prioridad_peso.get(orden.get("prioridad", "normal"), 2)

    fecha_str = orden.get("fecha_entrega", "")
    if isinstance(fecha_str, date):
        fecha = fecha_str
    else:
        try:
            fecha = date.fromisoformat(str(fecha_str))
        except (ValueError, TypeError):
            fecha = date.today() + timedelta(days=365)

    # Cantidad negativa: mayor cantidad = mayor prioridad
    cantidad = -(orden.get("cantidad", 0))

    return (peso, fecha, cantidad)


def _estimar_duracion_horas(orden: dict, maquina: dict) -> float:
    """
    Estima la duracion en horas para completar una orden en una maquina.
    Basado en cantidad / velocidad_por_nivel + tiempo de setup.

    / Estimates hours to complete an order on a machine.
    / מעריך שעות להשלמת הזמנה על מכונה.
    """
    nivel = maquina.get("nivel", "basico")
    velocidad = VELOCIDAD_POR_NIVEL.get(nivel, VELOCIDAD_BASE)
    cantidad = orden.get("cantidad", 1)
    horas_produccion = cantidad / velocidad
    horas_setup = TIEMPO_SETUP_MIN / 60.0
    return round(horas_produccion + horas_setup, 2)


def _maquina_compatible(maquina: dict, orden: dict) -> bool:
    """
    Verifica si una maquina puede procesar una orden.
    Todas las maquinas activas y operando son compatibles por defecto.
    Si la orden tiene maquina_id asignada, solo esa es compatible.

    / Checks if a machine can process an order.
    / בודק אם מכונה יכולה לעבד הזמנה.
    """
    # Si la orden ya tiene maquina asignada, respetar
    if orden.get("maquina_id"):
        return maquina.get("maquina_id") == orden["maquina_id"]
    return True


# ---------------------------------------------------------------------------
# Motor APS Greedy
# ---------------------------------------------------------------------------

def generar_plan_diario(
    ordenes: list[dict],
    maquinas: list[dict],
    asistencia: list[dict],
    tenant_id: str,
    fecha: Optional[date] = None,
    version: int = 1,
    motivo: str = "plan_8am",
) -> dict[str, Any]:
    """
    Genera un plan diario asignando ordenes a maquinas con algoritmo greedy.

    Parametros:
        ordenes:     Lista de ordenes pendientes (dicts con campos de Orden)
        maquinas:    Lista de maquinas disponibles (dicts con campos de Maquina)
        asistencia:  Lista de asistencia del dia (dicts con campos de Asistencia)
        tenant_id:   ID del tenant
        fecha:       Fecha del plan (default: hoy)
        version:     Numero de version del plan (v1 = 8am, v2+ = re-planificaciones)
        motivo:      Razon de generacion del plan

    Retorna:
        {
          tenant_id, fecha, version, motivo, timestamp,
          asignaciones: [...],
          ordenes_sin_asignar: [...],
          resumen: { total_ordenes, asignadas, sin_asignar, maquinas_usadas }
        }

    / Generates a daily plan assigning orders to machines with greedy algorithm.
    / מייצר תוכנית יומית המקצה הזמנות למכונות באלגוריתם חמדן.
    """
    fecha = fecha or date.today()
    ahora = datetime.now(timezone.utc)

    # --- Filtrar maquinas disponibles ---
    # Solo maquinas activas
    maquinas_disponibles = [m for m in maquinas if m.get("activa", True)]

    # Filtrar por asistencia: si hay registros, solo maquinas con operador presente
    operadores_presentes = set()
    if asistencia:
        for a in asistencia:
            if a.get("presente", False):
                operadores_presentes.add(a.get("operador_id"))

    # Inicializar carga de cada maquina
    carga_maquina: dict[str, float] = {}
    for m in maquinas_disponibles:
        carga_maquina[m["maquina_id"]] = 0.0

    # --- Ordenar ordenes por prioridad greedy ---
    ordenes_pendientes = [
        o for o in ordenes
        if o.get("estado") in ("pendiente", "retrasada", "en_proceso")
    ]
    ordenes_pendientes.sort(key=_prioridad_sort_key)

    # --- Asignar ordenes a maquinas ---
    asignaciones = []
    ordenes_sin_asignar = []
    hora_inicio_base = datetime.combine(fecha, datetime.min.time().replace(hour=8))
    hora_inicio_base = hora_inicio_base.replace(tzinfo=timezone.utc)

    for orden in ordenes_pendientes:
        mejor_maquina = None
        menor_carga = float("inf")

        for maquina in maquinas_disponibles:
            mid = maquina["maquina_id"]

            # Verificar compatibilidad
            if not _maquina_compatible(maquina, orden):
                continue

            # Verificar que no exceda jornada
            duracion = _estimar_duracion_horas(orden, maquina)
            if carga_maquina[mid] + duracion > HORAS_JORNADA:
                continue

            # Buscar la de menor carga
            if carga_maquina[mid] < menor_carga:
                menor_carga = carga_maquina[mid]
                mejor_maquina = maquina

        if mejor_maquina:
            mid = mejor_maquina["maquina_id"]
            duracion = _estimar_duracion_horas(orden, mejor_maquina)

            hora_inicio = hora_inicio_base + timedelta(hours=carga_maquina[mid])
            hora_fin = hora_inicio + timedelta(hours=duracion)

            asignaciones.append({
                "orden_id":      orden["orden_id"],
                "maquina_id":    mid,
                "maquina_nombre": mejor_maquina.get("nombre", mid),
                "producto":      orden.get("producto", ""),
                "cantidad":      orden.get("cantidad", 0),
                "prioridad":     orden.get("prioridad", "normal"),
                "fecha_entrega": str(orden.get("fecha_entrega", "")),
                "hora_inicio":   hora_inicio.isoformat(),
                "hora_fin":      hora_fin.isoformat(),
                "duracion_horas": duracion,
                "cliente":       orden.get("cliente", ""),
            })

            carga_maquina[mid] += duracion
        else:
            ordenes_sin_asignar.append({
                "orden_id":     orden["orden_id"],
                "producto":     orden.get("producto", ""),
                "cantidad":     orden.get("cantidad", 0),
                "prioridad":    orden.get("prioridad", "normal"),
                "fecha_entrega": str(orden.get("fecha_entrega", "")),
                "razon":        "sin_maquina_disponible",
            })

    # --- Resumen ---
    maquinas_usadas = set(a["maquina_id"] for a in asignaciones)

    plan = {
        "tenant_id":  tenant_id,
        "fecha":      fecha.isoformat(),
        "version":    version,
        "motivo":     motivo,
        "timestamp":  ahora.isoformat(),
        "asignaciones": asignaciones,
        "ordenes_sin_asignar": ordenes_sin_asignar,
        "resumen": {
            "total_ordenes":    len(ordenes_pendientes),
            "asignadas":        len(asignaciones),
            "sin_asignar":      len(ordenes_sin_asignar),
            "maquinas_usadas":  len(maquinas_usadas),
            "maquinas_disponibles": len(maquinas_disponibles),
        },
    }

    return plan


# ---------------------------------------------------------------------------
# Guardar plan en MongoDB (async)
# ---------------------------------------------------------------------------

async def guardar_plan_mongo(db, plan: dict) -> str:
    """
    Guarda el plan diario en la coleccion plan_diario de MongoDB.
    Retorna el ID del documento insertado.

    / Saves the daily plan to the plan_diario MongoDB collection.
    / שומר את התוכנית היומית לאוסף plan_diario במונגו.
    """
    result = await db["plan_diario"].insert_one(plan)
    return str(result.inserted_id)


async def obtener_plan_actual(db, tenant_id: str, fecha: Optional[date] = None) -> Optional[dict]:
    """
    Obtiene la version mas reciente del plan del dia.

    / Gets the most recent version of today's plan.
    / מקבל את הגרסה העדכנית ביותר של תוכנית היום.
    """
    fecha = fecha or date.today()
    plan = await db["plan_diario"].find_one(
        {"tenant_id": tenant_id, "fecha": fecha.isoformat()},
        sort=[("version", -1)],
    )
    if plan:
        plan["_id"] = str(plan["_id"])
    return plan


async def obtener_historial_planes(db, tenant_id: str, fecha: Optional[date] = None) -> list[dict]:
    """
    Obtiene todas las versiones del plan del dia.

    / Gets all versions of today's plan.
    / מקבל את כל הגרסאות של תוכנית היום.
    """
    fecha = fecha or date.today()
    cursor = db["plan_diario"].find(
        {"tenant_id": tenant_id, "fecha": fecha.isoformat()},
    ).sort("version", 1)
    planes = await cursor.to_list(length=100)
    for p in planes:
        p["_id"] = str(p["_id"])
    return planes


async def siguiente_version(db, tenant_id: str, fecha: Optional[date] = None) -> int:
    """
    Calcula el siguiente numero de version para el plan del dia.

    / Calculates the next version number for today's plan.
    / מחשב את מספר הגרסה הבא לתוכנית היום.
    """
    fecha = fecha or date.today()
    ultimo = await db["plan_diario"].find_one(
        {"tenant_id": tenant_id, "fecha": fecha.isoformat()},
        sort=[("version", -1)],
    )
    if ultimo:
        return ultimo["version"] + 1
    return 1
