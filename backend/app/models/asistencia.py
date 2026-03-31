from pydantic import BaseModel
from typing import Optional
from datetime import date, time


class Asistencia(BaseModel):
    """
    Registro de asistencia de un operador.
    / Operator attendance record.
    / רישום נוכחות של מפעיל.
    """
    operador_id: str
    fecha: date
    hora_entrada: Optional[time] = None
    hora_salida: Optional[time] = None
    presente: bool = False
    fuente: str = "manual"          # "manual" | "biometrico_csv"
    tenant_id: str


class AsistenciaManual(BaseModel):
    """Payload para marcar asistencia manual de un operador."""
    operador_id: str
    hora_entrada: Optional[time] = None
    presente: bool = True


class AsistenciaCSVRow(BaseModel):
    """Fila parseada de un CSV biométrico."""
    operador_id: str
    fecha: date
    hora_entrada: Optional[time] = None
    hora_salida: Optional[time] = None
