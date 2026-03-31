import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from app.models.user import LoginRequest, TokenResponse, User, UserCreate, UserInDB
from app.services.auth import (
    create_access_token,
    hash_password,
    verify_access_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer()

# In-memory user store for development (replaced by MongoDB later)
_users: dict[str, UserInDB] = {}
_users_by_email: dict[str, str] = {}  # email → user_id


def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    try:
        payload = verify_access_token(credentials.credentials)
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
def register(
    body: UserCreate,
    current: dict = Depends(_get_current_user),
):
    if current.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo los administradores pueden registrar usuarios")

    if body.email in _users_by_email:
        raise HTTPException(status_code=409, detail="El email ya está registrado")

    user_id = str(uuid.uuid4())
    tenant_id = current.get("tenant_id", "default")

    user = UserInDB(
        user_id=user_id,
        tenant_id=tenant_id,
        email=body.email,
        nombre=body.nombre,
        rol=body.rol,
        idioma=body.idioma,
        activo=True,
        hashed_password=hash_password(body.password),
    )
    _users[user_id] = user
    _users_by_email[body.email] = user_id

    return User(**user.model_dump(exclude={"hashed_password"}))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user_id = _users_by_email.get(body.email)
    if not user_id:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    user = _users[user_id]
    if not user.activo:
        raise HTTPException(status_code=403, detail="Usuario inactivo")
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    token = create_access_token(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        rol=user.rol,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=User)
def me(current: dict = Depends(_get_current_user)):
    user = _users.get(current["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return User(**user.model_dump(exclude={"hashed_password"}))
