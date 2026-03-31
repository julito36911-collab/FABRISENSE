from pydantic import BaseModel, EmailStr
from typing import Literal, Optional


class User(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    nombre: str
    rol: Literal["admin", "supervisor", "operador", "viewer"] = "viewer"
    idioma: Literal["es", "en", "he"] = "es"
    activo: bool = True


class UserInDB(User):
    hashed_password: str


class UserCreate(BaseModel):
    email: str
    nombre: str
    password: str
    rol: Literal["admin", "supervisor", "operador", "viewer"] = "viewer"
    idioma: Literal["es", "en", "he"] = "es"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
