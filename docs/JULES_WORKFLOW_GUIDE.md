# Guía de Uso de Google Jules (Google Pro) en Traffic Lab

Esta guía explica cómo aprovechar tu suscripción de **Google Pro** (Google One AI Premium / Gemini Pro) para delegar tareas y tickets de desarrollo a **Google Jules**, el agente de código autónomo en la nube de Google Labs.

---

## 1. ¿Qué es Google Jules y por qué usarlo aquí?

**Google Jules** es un agente de software autónomo que opera de forma asíncrona directamente en la nube de Google:
* **Cero consumo local:** No calienta tu Mac, no satura memoria RAM ni compite por archivos de git.
* **Entorno aislado (Cloud VM):** Jules levanta una máquina virtual, clona el repositorio, ejecuta `uv sync`, corre SUMO y valida los tests de forma independiente.
* **Integración nativa con GitHub:** Abre Pull Requests limpios con su plan de trabajo, cambios de código y resultados de pruebas.
* **Lectura de `AGENTS.md`:** Jules lee automáticamente el archivo `AGENTS.md` en la raíz de este proyecto y sigue al pie de la letra las restricciones (ASD-STE100, no usar `pyarrow`, tipos estrictos con `mypy`).

---

## 2. Métodos para Usar Jules

Existen tres formas muy sencillas de enviar trabajo a Jules:

### Método A: Despacho Automático desde la Terminal (Recomendado y a costo $0)
Puedes usar el script del proyecto para validar el ticket y despertar a Jules automáticamente:

```bash
# Valida y crea el Issue con etiqueta 'jules' en un solo paso:
python scripts/dispatch_to_jules.py tickets/M1/T1.6_snapshots.md

# O para simular primero sin crear el issue:
python scripts/dispatch_to_jules.py tickets/M1/T1.6_snapshots.md --dry-run
```

Este script:
1. Valida automáticamente que el ticket cumpla las reglas **ASD-STE100** (cero modales ambiguos).
2. Llama a GitHub CLI (`gh issue create`) con la etiqueta `jules`.
3. Activa de inmediato a la **Jules GitHub App** en Google Cloud sin costo adicional.

### Método B: Vía GitHub Issues Manualmente
1. Sube o sincroniza tu repositorio con tu cuenta de GitHub.
2. Asegúrate de tener instalada la **Jules GitHub App** (en [jules.google](https://jules.google)).
3. Crea un Issue en tu repositorio usando la plantilla **`Jules Implementation Ticket`** (`.github/ISSUE_TEMPLATE/jules_ticket.md`).
4. Añade la etiqueta `jules` al issue.
5. Jules se activará automáticamente en la nube de Google.

### Método C: Vía la Interfaz Web (jules.google)
1. Entra a **[jules.google](https://jules.google)** con tu cuenta de Google Pro.
2. Selecciona este repositorio (`traffic`) y la rama de trabajo.
3. Copia el contenido del ticket (por ejemplo, de `tickets/M1/T1.6_snapshots.md`).
4. Jules procesará el prompt, te mostrará el plan en pantalla y generará el branch y PR correspondiente.

---

## 3. Flujo de Trabajo Recomendado: De Ticket a Merge

```text
[Arquitecto redacta ticket en ASD-STE100]
                  │
                  ▼
[Se crea GitHub Issue con etiqueta 'jules' o en jules.google]
                  │
                  ▼
[Jules ejecuta en Cloud VM: uv sync -> código -> tests]
                  │
                  ▼
[Jules abre Pull Request en GitHub con reporte ASD-STE100]
                  │
                  ▼
[Revisor / Arquitecto verifica contra Decision Register]
                  │
                  ▼
[Merge a la rama principal + Resumen en español para el usuario]
```

---

## 4. Preguntas Frecuentes y Buenas Prácticas

* **¿Qué tipo de tickets delegar a Jules?**
  - Tickets tipo **Builder** de 4 o más archivos (ej. controladores, exportadores de métricas, análisis).
  - Tareas de tipo **Spike** que requieran exploración o prototipado.
* **¿Qué tareas hacer localmente?**
  - Cambios pequeños mecánicos de 1 a 3 archivos (directamente con Antigravity o el editor).
* **¿Cómo garantiza Jules que no rompe nada?**
  - Gracias a `AGENTS.md` y `.jules/instructions.md`, Jules sabe que `ruff`, `mypy` estricto y `pytest` deben salir con código de salida 0 antes de crear el PR.
