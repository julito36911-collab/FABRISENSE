from pydantic import BaseModel
from typing import Literal, Optional


class Operador(BaseModel):
    """
    Operador de planta registrado en el sistema.
    / Plant operator registered in the system.
    / מפעיל מפעל רשום במערכת.
    """
    operador_id: str
    nombre: str
    certificaciones: list[str] = []        # ["CNC-Fanuc", "Soldadura-MIG", ...]
    turno: Literal["mañana", "tarde", "noche"] = "mañana"
    tenant_id: str
    activo: bool = True


class OperadorCreate(BaseModel):
    nombre: str
    certificaciones: list[str] = []
    turno: Literal["mañana", "tarde", "noche"] = "mañana"


class OperadorUpdate(BaseModel):
    nombre: Optional[str] = None
    certificaciones: Optional[list[str]] = None
    turno: Optional[Literal["mañana", "tarde", "noche"]] = None
    activo: Optional[bool] = None
