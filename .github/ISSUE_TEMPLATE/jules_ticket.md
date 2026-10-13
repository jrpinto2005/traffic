---
name: "Jules Implementation Ticket"
about: "Ticket formatted in ASD-STE100 for autonomous execution by Google Jules"
title: "[TICKET] "
labels: ["jules", "builder"]
assignees: []
---

<!-- Format: ASD-STE100 (Simplified Technical English). No conversational filler. -->

# Ticket: [Insert Ticket ID and Short Title]

**Archetype:** Builder  
**Milestone:** [e.g. M1]  
**Depends On:** [Merged ticket IDs]  
**Implements Decisions:** [e.g. D-013, D-020]  

---

## 1. Context
[Two to three short sentences. State why this code exists and what breaks without it.]

---

## 2. Frozen Contract
<!-- Copy exact Python signatures, dataclasses, and schemas. Do not use external links. -->

```python
# [Insert frozen types, protocols, schemas here]
```

### Invariants
1. [Invariant 1: measurable condition that must always hold true]
2. [Invariant 2: boundary behavior]
3. [Invariant 3: error handling behavior]

---

## 3. Scope
1. [Exact deliverable 1]
2. [Exact deliverable 2]
3. [Tests covering all invariants]

---

## 4. Non-Goals
<!-- Required. List items the agent must NOT build. -->
1. Do not add base classes or abstract registries.
2. Do not add configuration options not specified in the contract.
3. Do not import `TrueState` into controller or observation modules.
4. Do not optimize without before and after profiling numbers.

---

## 5. Acceptance Criteria
- [ ] `uv run pytest tests/[path]/test_[name].py` exits with code 0.
- [ ] `uv run ruff check .` exits with code 0.
- [ ] `uv run ruff format --check .` exits with code 0.
- [ ] `uv run mypy` exits with code 0.

---

## 6. Escalate If
<!-- Conditions where Jules or the agent must halt and request human decision -->
1. The contract requires an unstated parameter or data field.
2. An invariant contradicts another invariant.
3. A test requires mocking SUMO.

---

## 7. Delivery Instructions for Jules
1. Run all checks before committing: `uv run ruff check .`, `uv run mypy`, `uv run pytest`.
2. Commit in small units with conventional messages: `type(scope): summary`.
3. Open a Pull Request with the completion table specified in `AGENTS.md`.
