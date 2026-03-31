from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime


class SensorData(BaseModel):
    """
    Lectura de sensores de una máquina CNC.
    / CNC machine sensor reading.
    / קריאת חיישנים של מכונת CNC.
    """
    maquina_id: str
    temperatura: float          # °C
    vibracion: float            # mm/s RMS
    rpm: int
    estado: Literal["operando", "falla", "parado", "urgente"] = "operando"
    timestamp: datetime
    tenant_id: str
    orden_id: Optional[str] = None      # Orden en proceso al momento de la lectura


class SensorDataCreate(BaseModel):
    """Payload recibido desde el simulador o broker MQTT."""
    maquina_id: str
    temperatura: float
    vibracion: float
    rpm: int
    estado: Literal["operando", "falla", "parado", "urgente"] = "operando"
    timestamp: datetime
    orden_urgente: Optional[str] = None
