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

### Método A: Vía GitHub Issues (Recomendado)
1. Sube o sincroniza tu repositorio con tu cuenta de GitHub.
2. Asegúrate de instalar la aplicación de **Jules GitHub App** (disponible en [jules.google](https://jules.google)).
3. Crea un Issue en tu repositorio usando la plantilla **`Jules Implementation Ticket`** (ubicada en `.github/ISSUE_TEMPLATE/jules_ticket.md`).
4. Añade la etiqueta `jules` al issue (o asígnalo a Jules).
5. **Jules iniciará sesión automáticamente en la nube**:
   - Analizará el ticket y el archivo `AGENTS.md`.
   - Generará un plan de acción para tu aprobación en GitHub.
   - Escribirá el código, correrá los tests (`pytest`, `ruff`, `mypy`).
   - Creará un Pull Request con el reporte en formato ASD-STE100.

### Método B: Vía la Interfaz Web (jules.google)
1. Entra a **[jules.google](https://jules.google)** con tu cuenta de Google Pro.
2. Selecciona este repositorio (`traffic`) y la rama de trabajo.
3. Copia el contenido del ticket (por ejemplo, de `tickets/M1/T1.10_controllers.md`).
4. Jules procesará el prompt, te mostrará el plan en pantalla y generará el branch y PR correspondiente.

### Método C: Vía CLI Local (@google/jules)
Si prefieres lanzar tareas desde la terminal de tu Mac:
```bash
npx @google/jules run --repo <usuario>/traffic --prompt "Implement ticket T1.10 following AGENTS.md"
```

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
