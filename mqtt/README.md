# FabriSense - MQTT / Mosquitto

## Desarrollo local

```bash
docker-compose up mqtt
```

Broker disponible en `mqtt://localhost:1883` sin autenticación.

Topics de referencia:
- `fabrisense/{tenant_id}/machines/{machine_id}/telemetry`
- `fabrisense/{tenant_id}/machines/{machine_id}/alerts`
- `fabrisense/{tenant_id}/orders/{order_id}/status`

## Producción

Antes del deploy, cambiar `mosquitto.conf`:

1. Comentar `allow_anonymous true`
2. Descomentar bloque TLS 1.2+
3. Generar certificados con Let's Encrypt o CA propia
4. Crear archivo `passwd` con `mosquitto_passwd`
5. Exponer puerto 8883 en lugar de 1883
