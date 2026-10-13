# Google Jules Working Instructions

These instructions guide **Google Jules** when working in cloud execution environments for `traffic_lab`.

---

## 1. Environment Setup

The repository uses Python 3.12 and `uv`.

```bash
# Install / synchronize dependencies in the sandbox VM
uv sync
```

SUMO packages (`eclipse-sumo`, `libsumo`, `traci`, `sumolib`) are installed directly via wheels managed by `uv.lock`. `SUMO_HOME` is not required.

---

## 2. Mandatory Quality Gates

Never submit a Pull Request if any of these commands fail:

```bash
# 1. Ruff linting
uv run ruff check .

# 2. Ruff formatting
uv run ruff format --check .

# 3. Mypy type-checking (configured strictly in pyproject.toml)
uv run mypy

# 4. Pytest test suite
uv run pytest
```

---

## 3. Architecture Invariants

* **Observation Boundary:** Modules under `traffic_lab/control/` must never import or reference `TrueState`.
* **No `pyarrow`:** Do not install `pyarrow`. It conflicts with `libsumo`'s bundled libraries.
* **No Speculative Abstractions:** Do not create abstract helper classes, plugin registries, or factory layers unless explicitly requested in the ticket.
* **Small Commits:** Make discrete commits for discrete units of work:
  - First commit: types and contracts
  - Second commit: core implementation
  - Third commit: comprehensive test cases
* **Language Standard:** Follow ASD-STE100 in commit messages, Pull Request descriptions, and error comments.
