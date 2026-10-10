---
name: cloudbuild-ssh-deploy
description: >-
  Instrucciones y solución de problemas para despliegues de Cloud Build hacia Compute Engine mediante SSH y Docker.
---

# Despliegue de Cloud Build por SSH

## Overview
Este skill define el estándar para desplegar repositorios hacia una VM de Compute Engine utilizando Cloud Build, Artifact Registry y SSH.

## Workflow de Configuración
1. **Validar Docker en VM:** Conectarse por SSH a la VM objetivo e instalar Docker (`sudo apt-get update && sudo apt-get install -y docker.io`).
2. **Crear Activador (Vía Consola):** Pedir al usuario que conecte su GitHub en la consola de GCP. Crear activadores GitHub vía CLI suele fallar sin la autorización Oauth.
3. **Inyectar Variables:** Si el activador requiere `_VM_NAME` y `_VM_ZONE`, deben inyectarse correctamente. Descargar el trigger (`gcloud builds triggers describe [NOMBRE] --format=yaml > trigger.yaml`), añadir el bloque `substitutions:` y sus variables, y volver a importarlo (`gcloud builds triggers import --source=trigger.yaml`). Evitar PowerShell al guardar el YAML, usar bash o python para prevenir errores de codificación UTF-16.

## Troubleshooting (Troubleshooting)
- **Error "argument --zone: expected one argument":** Significa que las variables de sustitución `_VM_NAME` y `_VM_ZONE` están vacías en Cloud Build.
- **Error 127 (Command not found: docker):** Significa que la conexión SSH hacia la VM funcionó, pero la VM destino no tiene Docker instalado.
- **Cambios en Trigger ignorados:** Si se actualiza el trigger en GCP, NUNCA usar el botón "Rebuild" o "Retry" en un build antiguo fallido, ya que clonará la configuración errónea anterior (variables vacías). Siempre lanzar un build NUEVO (e.g. `gcloud builds triggers run [NOMBRE] --branch=main`).
