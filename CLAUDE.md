# FabriSense — Contexto para Claude Code

## Qué es este proyecto
FabriSense es un sistema de inteligencia operacional para fábricas metalmecánicas.
Producto separado de FabriControl (ERP). Se venden por separado.
Comparten la misma base de datos MongoDB en el mismo servidor Emergent.

## Tech Stack
- Backend: FastAPI + Python
- Frontend: React 18 + Tailwind CSS + i18next
- Base de datos: MongoDB Atlas (motor async driver)
- MQTT: Mosquitto (sensores en tiempo real)
- Cola: Redis Streams (buffer de sensores)
- Auth: JWT + bcrypt

## 3 Idiomas desde el inicio
- Español (es) — idioma por defecto
- English (en)
- עברית Hebrew (he) — RTL automático
Todos los textos UI y mensajes del backend deben estar en los 3 idiomas.

## Arquitectura de datos
Sensores → MQTT → mqtt_receiver.py → Redis Streams → consumer.py → MongoDB + Alertas

## 3 Fuentes de órdenes
1. FabriControl (lectura directa MongoDB — misma BD)
2. CSV genérico (cualquier ERP)
3. Entrada manual (formulario web)

## Feature flags por plan
- Starter: M1 anomalías
- Pro: M1 + M2 predicción + M3 costos + APS
- Enterprise: Todo

## Fases del MVP — Estado actual
- F1: Configurador + Auth + Simulación ✅ COMPLETADA
- F2: Conectores + Modelos + MQTT pipeline ✅ COMPLETADA
- F3: M1 + M2 + M3 + M4 + Alertas ✅ COMPLETADA
- F4: APS planificación automática ✅ COMPLETADA
- F5: Dashboard + ROI + MongoDB real + Seed ✅ COMPLETADA — MVP DONE

## Reglas importantes
- consumer.py corre como proceso SEPARADO de FastAPI
- Anti-flood en alertas: no repetir misma alerta en 60 min
- Anti-flood en APS: máximo 1 re-planificación por minuto
- Todos los modelos llevan tenant_id (multi-tenant)
- Umbrales de sensores son configurables por máquina

## Para correr el stack
```bash
docker-compose up -d              # MongoDB + Mosquitto + Redis
cd backend
python seed.py                    # Insertar datos de prueba en MongoDB (1 sola vez)
uvicorn app.main:app --reload     # API (conecta MongoDB al arrancar)
python consumer.py                # Worker sensores
python simulator/simulador_cnc.py # Simulador 8 máquinas
```

## Seed — Datos de prueba
```bash
cd backend
python seed.py
```
Inserta:
- Tenant: `metalworks-ltda` (plan pro)
- Admin: `admin@metalworks.com` / `Admin1234!`
- 8 máquinas CNC (CNC-01 a CNC-08)
- 6 operadores con certificaciones
- 5 órdenes de ejemplo

## Colecciones MongoDB
- `tenants` — planes y feature flags
- `users` — usuarios del sistema
- `maquinas` — máquinas CNC del tenant
- `operadores` — operadores de planta
- `ordenes` — órdenes de producción
- `sensor_data` — **Time Series** (timeField: timestamp, metaField: maquina_id)
- `asistencia` — registro de asistencia diaria
- `historial_paros` — paros detectados con timestamps
- `plan_diario` — planes APS generados (versiones v1, v2...)
- `alertas` — alertas generadas por M1-M4
- `leads_configurador` — leads del configurador público
- `config_cliente` — umbrales personalizados por máquina

## Endpoints disponibles (v0.2.0)

### Auth — /api/auth
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | /api/auth/register | Registrar usuario (requiere admin) |
| POST | /api/auth/login | Login → JWT token |
| GET  | /api/auth/me | Perfil del usuario actual |

### Tenants — /api/tenants
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | /api/tenants/{tenant_id}/features | Feature flags del plan |

### Conectores y Órdenes
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | /api/connect/fabricontrol/sync | Sincronizar con FabriControl |
| GET  | /api/connect/fabricontrol/status | Estado última sync |
| POST | /api/import/ordenes-csv | Preview CSV de órdenes |
| POST | /api/import/ordenes-csv/confirm | Confirmar importación CSV |
| POST | /api/ordenes/nueva | Crear orden manual |
| GET  | /api/ordenes | Listar órdenes (filtros: estado, prioridad) |
| GET  | /api/ordenes/{orden_id} | Detalle de orden |

### Asistencia — /api/asistencia
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | /api/import/asistencia-csv | Importar CSV biométrico |
| POST | /api/asistencia/hoy | Marcar asistencia manual |
| GET  | /api/asistencia/hoy | Asistencia del día |

### Inteligencia M1-M4 — /api
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | /api/maquina/{id}/salud | M1: Score de salud (0-100) |
| GET | /api/maquinas/salud | M1: Salud de todas las máquinas |
| GET | /api/maquina/{id}/prediccion | M2: Predicción de degradación |
| GET | /api/maquina/{id}/costo | M3: Costo real vs presupuesto |
| GET | /api/costos/resumen | M3: Resumen costos del mes |
| GET | /api/maquina/{id}/oportunidad | M4: Costo de oportunidad |
| GET | /api/oportunidad/ranking | M4: Ranking por costo de oportunidad |

### APS — /api/aps
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET  | /api/aps/plan-hoy | Plan actual del día |
| POST | /api/aps/generar | Forzar generación manual de plan |
| GET  | /api/aps/historial | Versiones del plan de hoy |
| POST | /api/aps/trigger/paro | Simular paro de máquina (dev) |
| POST | /api/aps/trigger/urgente | Simular orden urgente (dev) |
| POST | /api/aps/trigger/recuperacion | Simular máquina recuperada (dev) |

### Dashboard — /api/dashboard
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | /api/dashboard/resumen | Métricas principales del tenant |
| GET | /api/dashboard/maquinas | Máquinas con score de salud M1 |
| GET | /api/dashboard/alertas-recientes | Últimas 10 alertas |
| GET | /api/dashboard/plan-hoy | Plan APS del día |
| GET | /api/dashboard/asistencia-hoy | Resumen asistencia del día |
| GET | /api/dashboard/roi | ROI según mes del tenant |

### Sistema
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /docs | Swagger UI automático |
