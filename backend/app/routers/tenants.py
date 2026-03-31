from fastapi import APIRouter, HTTPException
from app.models.tenant import FeatureFlags, PLAN_FEATURES, Tenant

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

# In-memory store for development (replaced by MongoDB later)
_tenants: dict[str, Tenant] = {
    "demo-starter": Tenant(
        tenant_id="demo-starter",
        nombre="Demo Starter",
        plan="starter",
        features=PLAN_FEATURES["starter"],
    ),
    "demo-pro": Tenant(
        tenant_id="demo-pro",
        nombre="Demo Pro",
        plan="pro",
        features=PLAN_FEATURES["pro"],
    ),
    "demo-enterprise": Tenant(
        tenant_id="demo-enterprise",
        nombre="Demo Enterprise",
        plan="enterprise",
        features=PLAN_FEATURES["enterprise"],
    ),
}


@router.get("/{tenant_id}/features", response_model=FeatureFlags)
def get_tenant_features(tenant_id: str):
    tenant = _tenants.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.activo:
        raise HTTPException(status_code=403, detail="Tenant is inactive")
    return tenant.features
