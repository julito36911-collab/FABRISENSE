from pydantic import BaseModel
from typing import Literal, Optional
from datetime import date


class Orden(BaseModel):
    """
    Orden de producción en el sistema.
    / Production order in the system.
    / הזמנת ייצור במערכת.
    """
    orden_id: str
    cliente: str
    producto: str
    cantidad: int
    prioridad: Literal["baja", "normal", "alta", "urgente"] = "normal"
    fecha_entrega: date
    estado: Literal[
        "pendiente", "en_proceso", "completada", "cancelada", "retrasada"
    ] = "pendiente"
    fuente: Literal["manual", "fabricontrol", "csv"] = "manual"
    maquina_id: Optional[str] = None       # Máquina asignada
    operador_id: Optional[str] = None      # Operador asignado
    notas: Optional[str] = None
    tenant_id: str


class OrdenCreate(BaseModel):
    """Datos necesarios para crear una orden manualmente."""
    cliente: str
    producto: str
    cantidad: int
    prioridad: Literal["baja", "normal", "alta", "urgente"] = "normal"
    fecha_entrega: date
    maquina_id: Optional[str] = None
    operador_id: Optional[str] = None
    notas: Optional[str] = None


class OrdenUpdate(BaseModel):
    estado: Optional[Literal[
        "pendiente", "en_proceso", "completada", "cancelada", "retrasada"
    ]] = None
    prioridad: Optional[Literal["baja", "normal", "alta", "urgente"]] = None
    maquina_id: Optional[str] = None
    operador_id: Optional[str] = None
    notas: Optional[str] = None
