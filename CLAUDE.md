# FabriSense — Contexto para Claude Code

## Qué es este proyecto
FabriSense es un sistema de inteligencia operacional para fábricas metalmecánicas.
Producto separado de FabriControl (ERP). Se venden por separado.
Comparten la misma base de datos MongoDB en el mismo servidor Emergent.

## Tech Stack
- Backend: FastAPI + Python
- Frontend: React 18 + Tailwind CSS + i18next
- Base de datos: MongoDB (compartida con FabriControl)
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

## Fases del MVP (Roadmap v7.2)
- F1: Configurador + Auth + Simulación ✅ COMPLETADA
- F2: Conectores + Modelos + MQTT pipeline ✅ COMPLETADA
- F3: M1 + M2 + M3 + M4 + Alertas ✅ COMPLETADA
- F4: APS planificación automática ⬜ SIGUIENTE
- F5: Dashboard + ROI + Stripe + Deploy ⬜ PENDIENTE

## Reglas importantes
- consumer.py corre como proceso SEPARADO de FastAPI
- Anti-flood en alertas: no repetir misma alerta en 60 min
- Anti-flood en APS: máximo 1 re-planificación por minuto
- Todos los modelos llevan tenant_id (multi-tenant)
- Umbrales de sensores son configurables por máquina

## Para correr el stack
docker-compose up -d              # MongoDB + Mosquitto + Redis
uvicorn app.main:app --reload     # API
python consumer.py                # Worker sensores
python simulator/simulador_cnc.py # Simulador 8 máquinas
