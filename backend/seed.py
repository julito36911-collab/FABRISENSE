"""
Seed Data — FabriSense MVP (Fase F5).

Inserta datos de prueba en MongoDB:
  - 1 tenant demo: "MetalWorks Ltda", plan "pro"
  - 1 usuario admin para el tenant
  - 8 maquinas CNC (las mismas del simulador)
  - 6 operadores con certificaciones variadas
  - 5 ordenes de ejemplo

Uso:
    cd backend
    python seed.py

/ Seed Data — FabriSense MVP (Phase F5).
/ נתוני זרע — FabriSense MVP (שלב F5).
"""

import os
import sys
import uuid
from datetime import date, timedelta

# Fix encoding en Windows (consola cp1252 no soporta caracteres como ñ)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

# Cargar .env antes de importar config
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from pymongo import MongoClient
from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# Conexion
# ---------------------------------------------------------------------------

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = "fabrisense"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

TENANT_ID = "metalworks-ltda"
HOY = date.today()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _borrar_si_existe(coleccion: str, filtro: dict) -> None:
    db[coleccion].delete_many(filtro)


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _skip(msg: str) -> None:
    print(f"  [--] {msg}")


# ---------------------------------------------------------------------------
# 1. Tenant
# ---------------------------------------------------------------------------

def seed_tenant() -> None:
    print("\n[1/5] Tenant...")
    _borrar_si_existe("tenants", {"tenant_id": TENANT_ID})

    db["tenants"].insert_one({
        "tenant_id":      TENANT_ID,
        "nombre":         "MetalWorks Ltda",
        "plan":           "pro",
        "idioma_default": "es",
        "activo":         True,
        "fecha_inicio":   HOY.isoformat(),
        "features": {
            "m1_anomalias":    True,
            "m2_prediccion":   True,
            "m3_costos":       True,
            "m4_oportunidad":  False,
            "aps_planificacion": True,
            "qc_calidad":      False,
            "dxf_agrupador":   False,
        },
    })
    _ok(f"Tenant '{TENANT_ID}' — MetalWorks Ltda (plan: pro)")


# ---------------------------------------------------------------------------
# 2. Usuario admin
# ---------------------------------------------------------------------------

def seed_usuario() -> None:
    print("\n[2/5] Usuario admin...")
    _borrar_si_existe("users", {"tenant_id": TENANT_ID})

    user_id = str(uuid.uuid4())
    hashed_pw = pwd_context.hash("Admin1234!")

    db["users"].insert_one({
        "user_id":         user_id,
        "tenant_id":       TENANT_ID,
        "email":           "admin@metalworks.com",
        "nombre":          "Administrador MetalWorks",
        "rol":             "admin",
        "idioma":          "es",
        "activo":          True,
        "hashed_password": hashed_pw,
    })
    _ok("admin@metalworks.com  /  password: Admin1234!")


# ---------------------------------------------------------------------------
# 3. Maquinas
# ---------------------------------------------------------------------------

MAQUINAS = [
    {
        "maquina_id":  "CNC-01",
        "nombre":      "Centro de Mecanizado Fanuc Alpha",
        "tipo":        "centro_mecanizado",
        "marca_cnc":   "Fanuc",
        "nivel":       "avanzado",
        "tasa_horaria": 75.0,
    },
    {
        "maquina_id":  "CNC-02",
        "nombre":      "Torno CNC Siemens T200",
        "tipo":        "torno",
        "marca_cnc":   "Siemens",
        "nivel":       "intermedio",
        "tasa_horaria": 60.0,
    },
    {
        "maquina_id":  "CNC-03",
        "nombre":      "Fresadora Heidenhain FH-5",
        "tipo":        "fresadora",
        "marca_cnc":   "Heidenhain",
        "nivel":       "avanzado",
        "tasa_horaria": 80.0,
    },
    {
        "maquina_id":  "CNC-04",
        "nombre":      "Torno CNC Fanuc Beta",
        "tipo":        "torno",
        "marca_cnc":   "Fanuc",
        "nivel":       "basico",
        "tasa_horaria": 45.0,
    },
    {
        "maquina_id":  "CNC-05",
        "nombre":      "Centro de Mecanizado Siemens CMX",
        "tipo":        "centro_mecanizado",
        "marca_cnc":   "Siemens",
        "nivel":       "intermedio",
        "tasa_horaria": 65.0,
    },
    {
        "maquina_id":  "CNC-06",
        "nombre":      "Fresadora Fanuc Robodrill",
        "tipo":        "fresadora",
        "marca_cnc":   "Fanuc",
        "nivel":       "avanzado",
        "tasa_horaria": 70.0,
    },
    {
        "maquina_id":  "CNC-07",
        "nombre":      "Torno CNC Heidenhain TNC",
        "tipo":        "torno",
        "marca_cnc":   "Heidenhain",
        "nivel":       "intermedio",
        "tasa_horaria": 55.0,
    },
    {
        "maquina_id":  "CNC-08",
        "nombre":      "Centro Mecanizado Basico CM-8",
        "tipo":        "centro_mecanizado",
        "marca_cnc":   "Fanuc",
        "nivel":       "basico",
        "tasa_horaria": 40.0,
    },
]


def seed_maquinas() -> None:
    print("\n[3/5] Maquinas (8 CNC)...")
    _borrar_si_existe("maquinas", {"tenant_id": TENANT_ID})

    docs = [{**m, "tenant_id": TENANT_ID, "activa": True} for m in MAQUINAS]
    db["maquinas"].insert_many(docs)
    for m in MAQUINAS:
        _ok(f"{m['maquina_id']} — {m['nombre']} ({m['tipo']}, {m['marca_cnc']}, ${m['tasa_horaria']}/h)")


# ---------------------------------------------------------------------------
# 4. Operadores
# ---------------------------------------------------------------------------

OPERADORES = [
    {
        "operador_id":   "OP-01",
        "nombre":        "Carlos Ramirez",
        "certificaciones": ["CNC-Fanuc", "Centro-Mecanizado"],
        "turno":         "mañana",
    },
    {
        "operador_id":   "OP-02",
        "nombre":        "Maria Lopez",
        "certificaciones": ["CNC-Siemens", "Torno-CNC", "Fresadora"],
        "turno":         "mañana",
    },
    {
        "operador_id":   "OP-03",
        "nombre":        "Jorge Mendez",
        "certificaciones": ["CNC-Heidenhain", "Centro-Mecanizado", "Fresadora"],
        "turno":         "mañana",
    },
    {
        "operador_id":   "OP-04",
        "nombre":        "Ana Torres",
        "certificaciones": ["CNC-Fanuc", "Torno-CNC"],
        "turno":         "tarde",
    },
    {
        "operador_id":   "OP-05",
        "nombre":        "Luis Herrera",
        "certificaciones": ["CNC-Siemens", "CNC-Fanuc", "Centro-Mecanizado"],
        "turno":         "tarde",
    },
    {
        "operador_id":   "OP-06",
        "nombre":        "Sofia Vega",
        "certificaciones": ["CNC-Heidenhain", "Torno-CNC", "Soldadura-MIG"],
        "turno":         "tarde",
    },
]


def seed_operadores() -> None:
    print("\n[4/5] Operadores (6)...")
    _borrar_si_existe("operadores", {"tenant_id": TENANT_ID})

    docs = [{**op, "tenant_id": TENANT_ID, "activo": True} for op in OPERADORES]
    db["operadores"].insert_many(docs)
    for op in OPERADORES:
        certs = ", ".join(op["certificaciones"])
        _ok(f"{op['operador_id']} — {op['nombre']} ({op['turno']}) | {certs}")


# ---------------------------------------------------------------------------
# 5. Ordenes de ejemplo
# ---------------------------------------------------------------------------

ORDENES = [
    {
        "orden_id":     "ORD-SEED-001",
        "cliente":      "Automotriz Norte SA",
        "producto":     "Engranaje Helical A-320",
        "cantidad":     150,
        "prioridad":    "urgente",
        "fecha_entrega": HOY.isoformat(),
        "estado":       "en_proceso",
        "fuente":       "fabricontrol",
        "maquina_id":   "CNC-01",
        "operador_id":  "OP-01",
        "notas":        "Cliente critico, entrega hoy",
    },
    {
        "orden_id":     "ORD-SEED-002",
        "cliente":      "Constructora Omega",
        "producto":     "Eje Transmision B-100",
        "cantidad":     80,
        "prioridad":    "alta",
        "fecha_entrega": (HOY + timedelta(days=1)).isoformat(),
        "estado":       "pendiente",
        "fuente":       "manual",
        "maquina_id":   "CNC-02",
        "operador_id":  "OP-02",
        "notas":        None,
    },
    {
        "orden_id":     "ORD-SEED-003",
        "cliente":      "Industrias Sur Ltda",
        "producto":     "Buje Bronce C-200",
        "cantidad":     300,
        "prioridad":    "normal",
        "fecha_entrega": (HOY + timedelta(days=3)).isoformat(),
        "estado":       "pendiente",
        "fuente":       "csv",
        "maquina_id":   None,
        "operador_id":  None,
        "notas":        "Importado desde ERP propio",
    },
    {
        "orden_id":     "ORD-SEED-004",
        "cliente":      "Precision Max SA",
        "producto":     "Vastago Hidraulico D-50",
        "cantidad":     40,
        "prioridad":    "alta",
        "fecha_entrega": (HOY + timedelta(days=2)).isoformat(),
        "estado":       "retrasada",
        "fuente":       "fabricontrol",
        "maquina_id":   "CNC-03",
        "operador_id":  "OP-03",
        "notas":        "Retrasada por falla CNC-03 ayer",
    },
    {
        "orden_id":     "ORD-SEED-005",
        "cliente":      "Metalurgica Centro",
        "producto":     "Placa Base E-80",
        "cantidad":     200,
        "prioridad":    "baja",
        "fecha_entrega": (HOY + timedelta(days=7)).isoformat(),
        "estado":       "pendiente",
        "fuente":       "manual",
        "maquina_id":   None,
        "operador_id":  None,
        "notas":        None,
    },
]


def seed_ordenes() -> None:
    print("\n[5/5] Ordenes (5)...")
    _borrar_si_existe("ordenes", {"tenant_id": TENANT_ID})

    docs = [{**o, "tenant_id": TENANT_ID} for o in ORDENES]
    db["ordenes"].insert_many(docs)
    for o in ORDENES:
        _ok(f"{o['orden_id']} — {o['producto']} x{o['cantidad']} ({o['prioridad']}, {o['estado']})")


# ---------------------------------------------------------------------------
# Ejecutar
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  FabriSense — Seed Data")
    print(f"  MongoDB: {MONGODB_URI[:40]}...")
    print(f"  Base de datos: {DB_NAME}")
    print("=" * 60)

    try:
        seed_tenant()
        seed_usuario()
        seed_maquinas()
        seed_operadores()
        seed_ordenes()

        print("\n" + "=" * 60)
        print("  Seed completado exitosamente.")
        print(f"  Tenant:   {TENANT_ID}")
        print("  Login:    admin@metalworks.com  /  Admin1234!")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()
