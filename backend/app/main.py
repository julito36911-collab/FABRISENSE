from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import tenants
from app.routers import auth
from app.routers import connectors
from app.routers import asistencia

app = FastAPI(
    title="FabriSense API",
    version="0.1.0",
    description="Sistema de Inteligencia Operacional para fábricas metalmecánicas",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(connectors.router)
app.include_router(asistencia.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "fabrisense-api", "version": "0.1.0"}
