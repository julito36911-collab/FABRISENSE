import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from app.database import get_database
from app.models.user import LoginRequest, TokenResponse, User, UserCreate, UserInDB
from app.services.auth import (
    create_access_token,
    hash_password,
    verify_access_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer()


def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    try:
        return verify_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserCreate,
    current: dict = Depends(_get_current_user),
    db=Depends(get_database),
):
    if current.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo los administradores pueden registrar usuarios")

    existing = await db["users"].find_one({"email": body.email})
    if existing:
        raise HTTPException(status_code=409, detail="El email ya está registrado")

    user_id = str(uuid.uuid4())
    tenant_id = current.get("tenant_id", "default")

    doc = {
        "user_id":         user_id,
        "tenant_id":       tenant_id,
        "email":           body.email,
        "nombre":          body.nombre,
        "rol":             body.rol,
        "idioma":          body.idioma,
        "activo":          True,
        "hashed_password": hash_password(body.password),
    }
    await db["users"].insert_one(doc)

    return User(
        user_id=user_id,
        tenant_id=tenant_id,
        email=body.email,
        nombre=body.nombre,
        rol=body.rol,
        idioma=body.idioma,
        activo=True,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db=Depends(get_database)):
    doc = await db["users"].find_one({"email": body.email})
    if not doc:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    if not doc.get("activo", True):
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    if not verify_password(body.password, doc["hashed_password"]):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    token = create_access_token(
        user_id=doc["user_id"],
        tenant_id=doc["tenant_id"],
        rol=doc["rol"],
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=User)
async def me(current: dict = Depends(_get_current_user), db=Depends(get_database)):
    doc = await db["users"].find_one({"user_id": current["sub"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return User(
        user_id=doc["user_id"],
        tenant_id=doc["tenant_id"],
        email=doc["email"],
        nombre=doc["nombre"],
        rol=doc["rol"],
        idioma=doc.get("idioma", "es"),
        activo=doc.get("activo", True),
    )
