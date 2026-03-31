"""
Importador CSV genérico de órdenes de producción.

Permite que el usuario defina qué columna del CSV corresponde a cada campo
requerido. Valida los datos y devuelve órdenes válidas + lista de errores.

/ Generic CSV importer for production orders.
/ מייבא CSV גנרי להזמנות ייצור.
"""

import csv
import io
import uuid
from datetime import date, datetime
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Campos requeridos y sus alias por defecto
# ---------------------------------------------------------------------------

CAMPOS_REQUERIDOS = ["orden_id", "producto", "cantidad", "fecha_entrega"]
CAMPOS_OPCIONALES = ["cliente", "prioridad", "notas", "maquina_id", "operador_id"]

DEFAULT_COLUMN_MAP = {
    # campo_fabrisense: columna_csv_por_defecto
    "orden_id":      "orden_id",
    "producto":      "producto",
    "cantidad":      "cantidad",
    "fecha_entrega": "fecha_entrega",
    "cliente":       "cliente",
    "prioridad":     "prioridad",
    "notas":         "notas",
    "maquina_id":    "maquina_id",
    "operador_id":   "operador_id",
}

PRIORIDADES_VALIDAS = {"baja", "normal", "alta", "urgente"}


# ---------------------------------------------------------------------------
# Parsers de campo
# ---------------------------------------------------------------------------

def _parse_fecha(valor: str) -> Optional[date]:
    """Intenta parsear la fecha en múltiples formatos comunes."""
    formatos = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]
    for fmt in formatos:
        try:
            return datetime.strptime(valor.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_cantidad(valor: str) -> Optional[int]:
    try:
        n = int(float(valor.strip()))
        return n if n > 0 else None
    except (ValueError, AttributeError):
        return None


def _normalize_prioridad(valor: str) -> str:
    mapping = {
        "low": "baja", "medium": "normal", "high": "alta", "urgent": "urgente",
    }
    v = valor.strip().lower()
    return mapping.get(v, v if v in PRIORIDADES_VALIDAS else "normal")


# ---------------------------------------------------------------------------
# Función principal de importación
# ---------------------------------------------------------------------------

def importar_csv(
    contenido: bytes,
    column_map: dict[str, str],
    tenant_id: str,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    """
    Parsea un CSV de órdenes usando el mapeo de columnas proporcionado.

    Parámetros:
        contenido: bytes del archivo CSV
        column_map: mapeo {campo_fabrisense: nombre_columna_csv}
        tenant_id: identificador del tenant
        encoding: codificación del CSV (default utf-8)

    Retorna:
        {
            "ordenes": [...],      # Órdenes válidas listas para importar
            "errores": [...],      # Filas con problemas
            "total_filas": int,
            "validas": int,
            "con_error": int,
        }

    / Parses an orders CSV using the provided column mapping.
    / מנתח CSV של הזמנות באמצעות מיפוי העמודות שסופק.
    """
    # Merge con defaults — el usuario solo necesita especificar lo que difiere
    mapa = {**DEFAULT_COLUMN_MAP, **column_map}

    try:
        texto = contenido.decode(encoding, errors="replace")
    except Exception as e:
        return {"error": f"No se pudo decodificar el archivo: {e}"}

    reader = csv.DictReader(io.StringIO(texto))
    if not reader.fieldnames:
        return {"error": "El CSV está vacío o no tiene encabezados"}

    ordenes_validas: list[dict] = []
    errores: list[dict] = []

    for num_fila, fila in enumerate(reader, start=2):  # start=2: fila 1 = header
        errores_fila: list[str] = []

        # --- orden_id ---
        orden_id_raw = fila.get(mapa.get("orden_id", ""), "").strip()
        if not orden_id_raw:
            orden_id_raw = str(uuid.uuid4())[:8].upper()  # Generar si falta

        # --- producto ---
        producto = fila.get(mapa.get("producto", ""), "").strip()
        if not producto:
            errores_fila.append("'producto' es obligatorio")

        # --- cantidad ---
        cantidad_raw = fila.get(mapa.get("cantidad", ""), "").strip()
        cantidad = _parse_cantidad(cantidad_raw)
        if cantidad is None:
            errores_fila.append(f"'cantidad' inválida: '{cantidad_raw}'")

        # --- fecha_entrega ---
        fecha_raw = fila.get(mapa.get("fecha_entrega", ""), "").strip()
        fecha = _parse_fecha(fecha_raw)
        if fecha is None:
            errores_fila.append(f"'fecha_entrega' no reconocida: '{fecha_raw}'")

        if errores_fila:
            errores.append({"fila": num_fila, "datos": dict(fila), "errores": errores_fila})
            continue

        # --- Campos opcionales ---
        cliente    = fila.get(mapa.get("cliente", ""), "Cliente desconocido").strip() or "Cliente desconocido"
        prioridad  = _normalize_prioridad(fila.get(mapa.get("prioridad", ""), "normal"))
        notas      = fila.get(mapa.get("notas", ""), "").strip() or None
        maquina_id = fila.get(mapa.get("maquina_id", ""), "").strip() or None
        operador_id = fila.get(mapa.get("operador_id", ""), "").strip() or None

        ordenes_validas.append({
            "orden_id":      orden_id_raw,
            "cliente":       cliente,
            "producto":      producto,
            "cantidad":      cantidad,
            "prioridad":     prioridad,
            "fecha_entrega": fecha.isoformat(),
            "estado":        "pendiente",
            "fuente":        "csv",
            "maquina_id":    maquina_id,
            "operador_id":   operador_id,
            "notas":         notas,
            "tenant_id":     tenant_id,
        })

    return {
        "ordenes":     ordenes_validas,
        "errores":     errores,
        "total_filas": len(ordenes_validas) + len(errores),
        "validas":     len(ordenes_validas),
        "con_error":   len(errores),
    }


def preview_csv(contenido: bytes, encoding: str = "utf-8", max_filas: int = 5) -> dict[str, Any]:
    """
    Devuelve las primeras filas del CSV y las columnas detectadas para que
    el usuario configure el mapeo antes de importar.

    / Returns the first rows and detected columns for mapping configuration.
    / מחזיר את השורות הראשונות ועמודות שזוהו לתצורת המיפוי.
    """
    try:
        texto = contenido.decode(encoding, errors="replace")
    except Exception as e:
        return {"error": str(e)}

    reader = csv.DictReader(io.StringIO(texto))
    columnas = list(reader.fieldnames or [])
    filas = []
    for i, fila in enumerate(reader):
        if i >= max_filas:
            break
        filas.append(dict(fila))

    return {
        "columnas_detectadas": columnas,
        "preview_filas":       filas,
        "mapeo_sugerido":      {k: v for k, v in DEFAULT_COLUMN_MAP.items() if v in columnas},
    }
