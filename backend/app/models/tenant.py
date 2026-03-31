from pydantic import BaseModel, Field
from typing import Literal


class FeatureFlags(BaseModel):
    m1_anomalias: bool = True
    m2_prediccion: bool = False
    m3_costos: bool = False
    m4_oportunidad: bool = False
    aps_planificacion: bool = False
    qc_calidad: bool = False
    dxf_agrupador: bool = False


PLAN_FEATURES: dict[str, FeatureFlags] = {
    "starter": FeatureFlags(
        m1_anomalias=True,
        m2_prediccion=False,
        m3_costos=False,
        m4_oportunidad=False,
        aps_planificacion=False,
        qc_calidad=False,
        dxf_agrupador=False,
    ),
    "pro": FeatureFlags(
        m1_anomalias=True,
        m2_prediccion=True,
        m3_costos=True,
        m4_oportunidad=False,
        aps_planificacion=True,
        qc_calidad=False,
        dxf_agrupador=False,
    ),
    "enterprise": FeatureFlags(
        m1_anomalias=True,
        m2_prediccion=True,
        m3_costos=True,
        m4_oportunidad=True,
        aps_planificacion=True,
        qc_calidad=False,
        dxf_agrupador=False,
    ),
}


class Tenant(BaseModel):
    tenant_id: str
    nombre: str
    plan: Literal["starter", "pro", "enterprise"] = "starter"
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    idioma_default: Literal["es", "en", "he"] = "es"
    activo: bool = True
