# ASD-STE100 Agent Communication Standard

**Status:** Active  
**Version:** 1.0  
**Governed by:** `02_PROJECT_CHARTER.md`  
**Implements:** `D-038` (ASD-STE100 inter-agent communication & two-tier reporting)

---

## 1. Purpose

This document defines the communication standard for AI agents in this project.
Agents must communicate with other agents using **ASD-STE100 (Simplified Technical English)**.
Agents must deliver final reports to the human project owner in **clear Spanish**.

### Why ASD-STE100 for Agents?
Frontier LLMs write conversational prose with hedges, politeness tokens, and ambiguous verbs.
In a scientific research lab, this verbosity causes three failure modes:
1. **Token Bloat:** Conversational phrasing consumes 30% to 50% more context window tokens.
2. **Semantic Ambiguity:** Words like "should", "may", or "consider" invite autonomous agents to make design choices that belong only in the decision register.
3. **Speculative Abstraction:** Vague task descriptions cause agents to create unrequested classes, helpers, and registries.

ASD-STE100 eliminates these failure modes with strict mathematical clarity.

---

## 2. Core Rules of ASD-STE100 for Agents

Every agent prompt, ticket description, completion report, PR description, and commit body must obey these rules:

### Rule 1: Approved Vocabulary
Each word has only one approved meaning and one approved part of speech.
* Use **make**, do not use *perform*, *execute*, or *effectuate*.
* Use **start**, do not use *initiate* or *commence*.
* Use **stop**, do not use *terminate* or *abort*.
* Use **show**, do not use *demonstrate* or *illustrate*.
* Use **keep**, do not use *retain* or *maintain* (unless maintaining hardware).
* Use **change**, do not use *modify* or *alter*.

### Rule 2: Strict Sentence Length Limits
* **Procedural Instructions:** Maximum **20 words** per sentence.
* **Descriptive Statements:** Maximum **25 words** per sentence.
* **One Action per Sentence:** Do not connect two actions with "and". Split them into two numbered steps.

### Rule 3: Active Voice and Imperative Mood
* Use active voice. Do not use passive voice.
  - *Incorrect:* "The configuration file must be loaded by the runner."
  - *Correct:* "The runner must load the configuration file."
* Use imperative mood for instructions:
  - *Incorrect:* "You should ensure tests are passing."
  - *Correct:* "Run the tests. Verify that all tests pass."

### Rule 4: Prohibition of Ambiguous Modals
* **Prohibited:** *may*, *might*, *should*, *could*, *would*.
* **Permitted:**
  - **must:** Expresses an absolute requirement.
  - **can:** Expresses an ability or capability.

### Rule 5: Restriction on Noun Clusters
Do not chain more than three nouns together.
* *Incorrect:* "Adaptive traffic signal phase transition controller state machine."
* *Correct:* "State machine for controller signal phase transitions."

### Rule 6: No Slang, Idioms, or Conversational Filler
Do not write greeting lines, conversational sign-offs, or metaphors.
Start directly with the task or finding.

---

## 3. Two-Tier Communication Model

Communication in this repository operates on two distinct tiers:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   TIER 1: INTER-AGENT COMMUNICATION                    │
│                                                                        │
│  Medium:  Tickets, PR descriptions, commit messages, agent handoffs    │
│  Language: English (Strict ASD-STE100)                                 │
│  Focus:   Deterministic, token-efficient, verifiable, zero fluff       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   TIER 2: HUMAN-FACING COMMUNICATION                   │
│                                                                        │
│  Medium:  Final summary to project owner (chat response, walk-through) │
│  Language: Spanish (Español)                                           │
│  Focus:   Very simple to understand, no unnecessary complexity,        │
│           but complete and transparent with all technical details.     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Tier 2 Human Reporting Specification (Spanish)

When an agent (Architect or Lead Agent) presents results, status, or completed tickets to the human owner, the report must follow this exact template:

```markdown
### 🎯 Resumen Ejecutivo (Qué se hizo y por qué)
[Explicación en español claro y cotidiano, en 2 o 3 frases. Cero enredos.]

### ⚙️ Cambios Principales
* **[Componente o archivo]:** [Qué cambió y cuál es el impacto práctico.]

### 🧪 Pruebas y Validación Realizadas
* **Comandos ejecutados:** `uv run ruff check .`, `uv run mypy`, `uv run pytest tests/...`
* **Resultados:** [X pruebas pasadas, 0 errores, tipos estrictos limpios.]

### 📋 Archivos Modificados / Creados
* `archivo_1.py`: [Descripción breve de la modificación]
* `archivo_2.py`: [Descripción breve]

### 🚀 Siguiente Paso Recomendado
[Acción inmediata concreta: e.g. "Aprobar el merge", "Iniciar ticket T1.12".]
```

---

## 5. Automated Validation

The repository includes an automated checker in `scripts/validate_ste100.py`.
Run this script to check any markdown file against the core rules:

```bash
python scripts/validate_ste100.py tickets/M1/T1.10_controllers.md
```
