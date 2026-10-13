# M1 Tickets — Single intersection, oracle observation, honest baselines

The founding slice (`03_ROADMAP.md` M1). Every layer exists in thin form and the milestone
produces the project's first real result: mean delay vs. demand for four controllers, on
paired seeds, with confidence intervals.

## Status, 2026-10-07 (updated with T1.4)

**This table is the one place M1 status is recorded.** Tickets carry no status line of their
own, for the reason the glossary was dropped: a second copy is a second place to drift.
Update it in the same commit that merges a ticket.

| Ticket | State |
| --- | --- |
| T1.1 skeleton | ✅ merged 2026-08-18 |
| T1.2 domain types | ✅ merged 2026-08-18 |
| T1.3 network generator | ✅ merged 2026-10-07 — see the completion record, including two findings about the M0 reference scenario |
| T1.4 backend adapter | ✅ merged 2026-10-07 — audited; one defect fixed; four gaps handed to T1.3, T1.8, T1.9 (see the ticket's completion record) |
| T1.5 demand | ✅ merged 2026-10-08 — see the completion record |
| T1.6 snapshots | ✅ merged 2026-10-12 — initial-state snapshot keying, production, and loading |
| T1.7 constraint layer | ✅ merged 2026-08-24 |
| T1.8 metrics | ✅ merged 2026-10-07 — see the completion record |
| T1.9 sensing, oracle | ✅ merged 2026-10-07 — exact oracle against the real simulator; see the completion record |
| T1.10 controllers | 🚧 issued 2026-10-12, amended contract |
| T1.11 runner | ✅ merged 2026-10-12 — the run core; see the completion record |
| T1.12 analysis | ✅ merged 2026-10-13 — implemented by Google Jules (PR #1); paired comparison, BCa CIs, Holm-Bonferroni, viz style |
| T1.13 profiling | ✅ merged 2026-10-13 — implemented by Google Jules (PR #2); profiling harness and baseline report |
| T1.14 signal display | ✅ merged 2026-10-07 — see the completion record |
| T1.15 detection zone | ✅ merged 2026-10-07 |
| T1.16 experiment spec | ⬜ blocked on T1.10 — split from T1.11 |

Ready now: T1.6. In flight: T1.10. Critical path to the headline figure:
T1.10 → T1.16.
**Open risk:** the full suite hung once under TraCI for 17 minutes without reproducing.

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

**Waves, corrected 2026-08-18.** The original listing paired T1.1 with T1.2 in one wave. They
are not parallel: T1.2 needs `traffic_lab/__init__.py` and a `pyproject.toml` carrying the build
target before its tests can import anything, and both are T1.1's deliverables. Two concurrent
agents would create the same two files, which by `08_AGENT_HANDOFF_PROTOCOL.md` §5.1 means the
split was wrong rather than that the agents need coordinating.

Since T1.3, T1.4, T1.7 and T1.9 all depend on T1.2, **there is no parallelism at all until T1.2
lands**. The critical path is narrow and unavoidable:

| Wave | Tickets | Concurrency |
| --- | --- | --- |
| 1 | T1.1 | single — no worktree needed |
| 2 | T1.2 | single — no worktree needed |
| 3 | T1.3 ∥ T1.4 ∥ T1.7 ∥ T1.9 | 4 worktrees |
| 4 | T1.5 ∥ T1.6 ∥ T1.8 ∥ T1.13 | 4 worktrees |
| 5 | T1.10 ∥ T1.11 | 2 worktrees |
| 6 | T1.12 | single |
| 7 | Reviewer pass | single |

## Before any ticket starts

M0 must be complete. Its spikes can amend `D-002`, `D-022` and `D-025`, and three of these
tickets are written against those decisions as currently stated.

**Satisfied:** M0 is complete (`tickets/M0/README.md`). Its amendments are in the register's
change log at v1.4 and v1.5. Read a ticket's decision references against the register as
amended, and escalate if the two disagree.
