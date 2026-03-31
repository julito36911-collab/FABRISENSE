"""
Router de asistencia de operadores (Tareas 2.6 + 2.7).

Endpoints:
  POST /api/import/asistencia-csv  → Importar CSV del reloj biométrico
  POST /api/asistencia/hoy         → Marcar asistencia manual de un operador
  GET  /api/asistencia/hoy         → Listar quién llegó hoy

/ Operator attendance router (Tasks 2.6 + 2.7).
/ נתב נוכחות מפעילים (משימות 2.6 + 2.7).
"""

from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.models.asistencia import AsistenciaManual
from app.services.asistencia_service import (
    filtrar_asistencia_hoy,
    importar_asistencia_csv,
    registrar_asistencia_manual,
)
from app.services.auth import verify_access_token

router = APIRouter(tags=["asistencia"])
bearer_scheme = HTTPBearer()

# In-memory store (hasta que se conecte MongoDB)
_asistencia: list[dict] = []


def _current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    try:
        return verify_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


# ---------------------------------------------------------------------------
# 2.6 - Importar CSV biométrico
# ---------------------------------------------------------------------------

@router.post("/api/import/asistencia-csv")
async def import_asistencia_csv(
    archivo: UploadFile = File(...),
    current: dict = Depends(_current_user),
) -> dict:
    """
    Importa un CSV del reloj biométrico con registros de asistencia.
    Columnas esperadas por defecto: id_empleado, fecha, entrada, salida.
    El usuario puede proporcionar un mapeo personalizado como query params.

    / Imports a biometric clock CSV with attendance records.
    / מייבא CSV משעון ביומטרי עם רשומות נוכחות.
    """
    if current.get("rol") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Se requiere rol admin o supervisor")

    contenido = await archivo.read()
    tenant_id = current.get("tenant_id", "default")

    resultado = importar_asistencia_csv(contenido, {}, tenant_id)

    if "error" in resultado:
        raise HTTPException(status_code=400, detail=resultado["error"])

    # Agregar al store evitando duplicados (operador_id + fecha)
    claves_existentes = {
        (r["operador_id"], r["fecha"]) for r in _asistencia
        if r.get("tenant_id") == tenant_id
    }
    nuevos = [
        r for r in resultado["registros"]
        if (r["operador_id"], r["fecha"]) not in claves_existentes
    ]
    _asistencia.extend(nuevos)

    return {
        "importados": len(nuevos),
        "duplicados_omitidos": resultado["validos"] - len(nuevos),
        "errores": resultado["con_error"],
        "detalle_errores": resultado["errores"],
    }


# ---------------------------------------------------------------------------
# 2.7 - Asistencia manual
# ---------------------------------------------------------------------------

@router.post("/api/asistencia/hoy")
async def marcar_asistencia(
    body: AsistenciaManual,
    current: dict = Depends(_current_user),
) -> dict:
    """
    El supervisor marca la asistencia de un operador para el día de hoy.
    Si ya existe un registro para ese operador hoy, lo actualiza.

    / Supervisor marks attendance for an operator for today.
    / המפקח מסמן נוכחות עבור מפעיל להיום.
    """
    if current.get("rol") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Se requiere rol admin o supervisor")

    tenant_id = current.get("tenant_id", "default")
    hoy = date.today().isoformat()

    # Verificar si ya existe y actualizar
    for registro in _asistencia:
        if (
            registro["operador_id"] == body.operador_id
            and registro["fecha"] == hoy
            and registro["tenant_id"] == tenant_id
        ):
            registro["presente"] = body.presente
            if body.hora_entrada:
                registro["hora_entrada"] = body.hora_entrada.strftime("%H:%M:%S")
            return {"mensaje": "Asistencia actualizada", "registro": registro}

    # Crear nuevo registro
    hora = body.hora_entrada if isinstance(body.hora_entrada, time) else None
    registro = registrar_asistencia_manual(
        operador_id=body.operador_id,
        tenant_id=tenant_id,
        presente=body.presente,
        hora_entrada=hora,
    )
    _asistencia.append(registro)
    return {"mensaje": "Asistencia registrada", "registro": registro}


@router.get("/api/asistencia/hoy")
async def asistencia_hoy(current: dict = Depends(_current_user)) -> dict:
    """
    Lista de operadores con registro de asistencia para el día de hoy.

    / List of operators with attendance records for today.
    / רשימת מפעילים עם רשומות נוכחות להיום.
    """
    tenant_id = current.get("tenant_id", "default")
    hoy = filtrar_asistencia_hoy(_asistencia, tenant_id)
    presentes = [r for r in hoy if r.get("presente")]
    ausentes  = [r for r in hoy if not r.get("presente")]

    return {
        "fecha": date.today().isoformat(),
        "total_registros": len(hoy),
        "presentes": len(presentes),
        "ausentes": len(ausentes),
        "detalle": hoy,
    }
