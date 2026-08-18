# M1 Tickets — Single intersection, oracle observation, honest baselines

The founding slice (`03_ROADMAP.md` M1). Every layer exists in thin form and the milestone
produces the project's first real result: mean delay vs. demand for four controllers, on
paired seeds, with confidence intervals.

## A correction to the roadmap's ticket list

The roadmap listed ten M1 tickets and **none of them was sensing**, on the reasoning that M1
uses oracle observation. That reasoning is wrong under `06_ARCHITECTURE.md` §4.1, where **the
oracle is a sensor, not a bypass**. If no sensor exists at M1, controllers read `TrueState`
directly and the structural guarantee that makes a truth leak impossible has to be retrofitted
at M3 — and retrofits of that kind are exactly the ones that never fully happen.

`T1.9` therefore exists, it is small, and it is not optional. Controllers see
`EstimatedState` from the very first commit.

## Dependency order

```
T1.1 skeleton ─┐
T1.2 domain ───┼─→ T1.3 network ──→ T1.5 demand ─┐
               │                                  │
               ├─→ T1.4 adapter ──┬─→ T1.6 snapshots
               │                  ├─→ T1.8 metrics ──┐
               │                  └─→ T1.13 profiling│
               ├─→ T1.7 constraints ──┐              │
               └─→ T1.9 sensing ──────┴─→ T1.10 controllers
                                                     │
                                      T1.11 runner ──┴──→ T1.12 analysis
```

**Waves:** (1) T1.1 ∥ T1.2 · (2) T1.3 ∥ T1.4 ∥ T1.7 ∥ T1.9 · (3) T1.5 ∥ T1.6 ∥ T1.8 ∥ T1.13
· (4) T1.10 ∥ T1.11 · (5) T1.12 · (6) Reviewer pass.

## Before any ticket starts

M0 must be complete. Its spikes can amend `D-002`, `D-022` and `D-025`, and three of these
tickets are written against those decisions as currently stated.
