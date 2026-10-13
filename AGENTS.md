# AGENTS.md — Repository Directives for Autonomous Coding Agents

**Project:** Traffic Control Research Lab (`traffic_lab`)  
**Target Agents:** Google Jules, Gemini Pro, Antigravity, and autonomous subagents  
**Language Standard for Agents:** ASD-STE100 (Simplified Technical English)

---

## 1. Project Purpose

This project is a scientific research platform for adaptive traffic signal control.
The simulator is a scientific instrument, not the final product.
The project uses SUMO (`eclipse-sumo` / `libsumo`) as the simulation engine.

---

## 2. Non-Negotiable Invariants

You must obey these rules in all tasks. If you violate a rule, results become invalid.

1. **Separation of Truth, Observation, and Estimate:**
   - Controllers must never see `TrueState`.
   - Controllers must receive `EstimatedState` only.
   - The oracle is an exact sensor, not a code bypass.
   - Do not import `TrueState` in `traffic_lab/control/` or any controller module.

2. **No Speculative Abstraction (Charter §6):**
   - Do not add base classes with only one child.
   - Do not add registries, plugin systems, or generic factory layers.
   - Do not add configuration options that no config file uses.
   - Use `typing.Protocol` with minimal methods.

3. **No Unmeasured Optimizations:**
   - Do not optimize code without a before/after measurement.
   - Do not do per-vehicle queries in the step loop.

4. **Dependency Restrictions:**
   - Never add `pyarrow`. It collides with `libsumo`'s bundled `libarrow` (D-004). Tests will fail.
   - Do not add new external dependencies without explicit architect instruction.

5. **Test Environment Safety:**
   - Never use `SIGSEGV` or `SIGABRT` to stop a process in tests. On macOS, this opens crash dialogs. Use `SIGKILL`.
   - Test against real SUMO. Do not mock SUMO behavior.

---

## 3. Communication Standard: ASD-STE100

Agents must communicate with other agents and in artifacts using **ASD-STE100**.

### 3.1 Rules of ASD-STE100
* **Approved Words Only:** Use words with one clear meaning.
* **Sentence Length:** Max 20 words for instructions. Max 25 words for descriptions.
* **Voice and Mood:** Use active voice. Use imperative mood for steps ("Run tests", not "The tests should be run").
* **Prohibited Modal Verbs:** Do not use "should", "may", "might", or "could". Use **must** for requirements and **can** for capability.
* **Noun Clusters:** Do not put more than three nouns together.
* **Direct Statements:** Do not write conversational filler or polite phrases.

### 3.2 Reporting Rule (Two-Tier Model)
* **Agent-to-Agent (Tickets, PRs, Commits, Technical Logs):** ASD-STE100 (English).
* **Agent-to-Human (Final Summary for the User):** Spanish (*Español*). Make it simple, structured, and easy to understand. Do not omit technical details, test results, or modified files.

---

## 4. Environment and Setup Commands

This project uses Python 3.12 and `uv`.

### 4.1 Dependency Synchronization
```bash
# In the active checkout or worktree:
uv sync
```

### 4.2 Required Verification Commands
All four commands must exit with code 0 before you commit:

```bash
# 1. Code style and linting
uv run ruff check .

# 2. Code format validation
uv run ruff format --check .

# 3. Strict type checking
uv run mypy

# 4. Unit tests
uv run pytest
```

Note: If `uv` is not in your global `PATH`, use `~/.local/bin/uv` or the virtual environment directly:
```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest
```

---

## 5. Working Mode for Builders (Google Jules / Subagents)

When you receive an implementation ticket:

1. **Read the Contract First:** Read the ticket file and all cited decisions in `docs/04_DECISION_REGISTER.md`.
2. **Obey the Non-Goals:** Read the `Non-goals` section of the ticket. Do not build items listed there.
3. **Escalate When Ambiguous:**
   - If a contract is ambiguous, stop.
   - If an "Escalate if" condition triggers, stop and report.
   - Do not make undocumented design choices.
4. **Commit Discipline:**
   - Make small, logical commits (`type(scope): summary`).
   - Include the ticket ID in the commit body.
   - Make sure all four checks pass on every commit.

---

## 6. Completion Report Format (ASD-STE100)

When you finish a ticket or open a Pull Request, write your report with this structure:

```markdown
## Ticket Completion Summary
- **Ticket ID:** <e.g., T1.10>
- **Status:** Complete / Escalated

### 1. Acceptance Criteria Verification
| Criterion | Verification Command / Test | Result |
| --- | --- | --- |
| <Criterion text> | pytest tests/... | PASS |

### 2. Contract Compliance
- Invariants implemented: <list>
- Non-goals observed: YES
- Truth leaks introduced: NONE

### 3. Commits
- `<hash>` `type(scope): summary`
```
