from pydantic import BaseModel
from typing import Literal, Optional


class Maquina(BaseModel):
    """
    Máquina CNC registrada en el sistema.
    / CNC machine registered in the system.
    / מכונת CNC רשומה במערכת.
    """
    maquina_id: str
    nombre: str
    tipo: str                              # fresadora, torno, centro_mecanizado, etc.
    marca_cnc: str                         # Fanuc, Siemens, Heidenhain, etc.
    nivel: Literal["basico", "intermedio", "avanzado"] = "basico"
    tasa_horaria: float = 0.0             # Costo por hora en USD
    tenant_id: str
    activa: bool = True


class MaquinaCreate(BaseModel):
    nombre: str
    tipo: str
    marca_cnc: str
    nivel: Literal["basico", "intermedio", "avanzado"] = "basico"
    tasa_horaria: float = 0.0


class MaquinaUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    marca_cnc: Optional[str] = None
    nivel: Optional[Literal["basico", "intermedio", "avanzado"]] = None
    tasa_horaria: Optional[float] = None
    activa: Optional[bool] = None
