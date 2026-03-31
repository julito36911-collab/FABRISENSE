"""
Servicio de asistencia de operadores.

Soporta dos fuentes:
  1. CSV del reloj biométrico
  2. Entrada manual por supervisor

/ Operator attendance service.
/ שירות נוכחות מפעילים.
"""

import csv
import io
from datetime import date, datetime, time
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Importador CSV biométrico
# ---------------------------------------------------------------------------

# Columnas esperadas por defecto en el export del reloj biométrico
DEFAULT_BIO_MAP = {
    "operador_id": "id_empleado",
    "fecha":       "fecha",
    "hora_entrada": "entrada",
    "hora_salida":  "salida",
}


def _parse_time(valor: str) -> Optional[time]:
    """Intenta parsear hora en formatos HH:MM o HH:MM:SS."""
    if not valor or not valor.strip():
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(valor.strip(), fmt).time()
        except ValueError:
            continue
    return None


def _parse_date(valor: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(valor.strip(), fmt).date()
        except ValueError:
            continue
    return None


def importar_asistencia_csv(
    contenido: bytes,
    column_map: dict[str, str],
    tenant_id: str,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    """
    Parsea un CSV de asistencia del reloj biométrico.

    Parámetros:
        contenido: bytes del archivo CSV
        column_map: mapeo {campo_fabrisense: columna_csv}
        tenant_id: identificador del tenant
        encoding: codificación del archivo

    Retorna dict con 'registros' válidos, 'errores' y conteos.

    / Parses an attendance CSV from the biometric clock.
    / מנתח CSV נוכחות משעון ביומטרי.
    """
    mapa = {**DEFAULT_BIO_MAP, **column_map}

    try:
        texto = contenido.decode(encoding, errors="replace")
    except Exception as e:
        return {"error": f"No se pudo decodificar el archivo: {e}"}

    reader = csv.DictReader(io.StringIO(texto))
    if not reader.fieldnames:
        return {"error": "El CSV está vacío o sin encabezados"}

    registros: list[dict] = []
    errores: list[dict] = []

    for num_fila, fila in enumerate(reader, start=2):
        errores_fila: list[str] = []

        operador_id = fila.get(mapa["operador_id"], "").strip()
        if not operador_id:
            errores_fila.append("'operador_id' es obligatorio")

        fecha_raw = fila.get(mapa["fecha"], "").strip()
        fecha = _parse_date(fecha_raw)
        if fecha is None:
            errores_fila.append(f"'fecha' no reconocida: '{fecha_raw}'")

        if errores_fila:
            errores.append({"fila": num_fila, "datos": dict(fila), "errores": errores_fila})
            continue

        hora_entrada = _parse_time(fila.get(mapa.get("hora_entrada", ""), ""))
        hora_salida  = _parse_time(fila.get(mapa.get("hora_salida", ""), ""))

        registros.append({
            "operador_id":  operador_id,
            "fecha":        fecha.isoformat(),
            "hora_entrada": hora_entrada.strftime("%H:%M:%S") if hora_entrada else None,
            "hora_salida":  hora_salida.strftime("%H:%M:%S") if hora_salida else None,
            "presente":     True,
            "fuente":       "biometrico_csv",
            "tenant_id":    tenant_id,
        })

    return {
        "registros":   registros,
        "errores":     errores,
        "total_filas": len(registros) + len(errores),
        "validos":     len(registros),
        "con_error":   len(errores),
    }


# ---------------------------------------------------------------------------
# Asistencia manual
# ---------------------------------------------------------------------------

def registrar_asistencia_manual(
    operador_id: str,
    tenant_id: str,
    presente: bool = True,
    hora_entrada: Optional[time] = None,
) -> dict[str, Any]:
    """
    Genera un registro de asistencia manual para un operador en el día de hoy.

    / Generates a manual attendance record for an operator for today.
    / יוצר רישום נוכחות ידני למפעיל להיום.
    """
    hoy = date.today()
    return {
        "operador_id":  operador_id,
        "fecha":        hoy.isoformat(),
        "hora_entrada": hora_entrada.strftime("%H:%M:%S") if hora_entrada else datetime.now().strftime("%H:%M:%S"),
        "hora_salida":  None,
        "presente":     presente,
        "fuente":       "manual",
        "tenant_id":    tenant_id,
    }


def filtrar_asistencia_hoy(
    registros: list[dict[str, Any]],
    tenant_id: str,
) -> list[dict[str, Any]]:
    """
    Filtra los registros de asistencia del día actual para un tenant.

    / Filters attendance records for the current day and tenant.
    / מסנן רשומות נוכחות עבור היום הנוכחי וה-tenant.
    """
    hoy = date.today().isoformat()
    return [
        r for r in registros
        if r.get("fecha") == hoy and r.get("tenant_id") == tenant_id
    ]
