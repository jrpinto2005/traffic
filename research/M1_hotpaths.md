# M1 Hot-Path Report

**Ticket:** `tickets/M1/T1.13_profiling.md` · **Status:** complete

---

## 1. Overview

This document reports where simulation time goes at milestone M1.
The profiler measures the execution of `run_one` on the acceptance config `configs/smoke.yaml`.

---

## 2. Performance Baseline

| Parameter | Value |
| --- | --- |
| Simulated Duration | 420.0 s (0.1167 simulated hours) |
| Wall-Clock Time | ~0.86 s – 0.94 s |
| Wall-Clock / Simulated Hour | ~7.3 s – 8.0 s |
| Peak Resident Memory | ~173 MB |

### Comparison with M0
T0.3 measured raw LibSUMO steps at ~1.43 s – 2.57 s per simulated hour on Apple M3 hardware.
M1 runs full platform infrastructure:
- Batched projection on every step.
- Constraint layer state updates on every step.
- Metric accumulation on every step.
- Sensor observation and estimation on decision intervals.
- Trip accounting and Parquet dataset write at run end.

The run completes in less than one second of wall-clock time.

---

## 3. Hot Paths

The top time consumers in the M1 step loop are:

1. **Batched State Projection (`SumoBackend.project`, `_project_vehicles`, `_project_lanes`):**
   Accounts for ~62% of step-loop wall-clock time. Vehicle projection and domain type instantiation consume most of this time.
2. **SUMO C++ Simulation Step (`libsumo.simulation_step`):**
   Accounts for ~18% of step-loop wall-clock time. This is C++ simulation execution inside LibSUMO.
3. **Transport Fetch (`transport.fetch`):**
   Accounts for ~30% of step-loop wall-clock time inside projection. Calls LibSUMO variable getters per step.

---

## 4. Findings and Invariants

- Hot paths match `D-031` expectations: state projection and backend query calls dominate execution time.
- No optimization is required at M1 per `D-031`. Reporting is the deliverable.
