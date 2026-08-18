# M0 Tickets — Prior art, spikes, and stack confirmation

M0 is the **only milestone exempt from the vertical-slice rule** (`03_ROADMAP.md` §0.2). It
exists to decide what the slice is made of. Its code is throwaway by design: nothing written
here survives into `traffic_lab/`.

**Spike tickets use a lighter template than the Builder template in
`08_AGENT_HANDOFF_PROTOCOL.md` §4.** A spike has a question and a time box, not a frozen
contract, because the point is that we do not yet know enough to write one.

## Order

```
T0.0  Environment            ← BLOCKS EVERYTHING
  │
  ├── T0.1  Prior art        (needs SUMO only to run the libraries)
  │
  └── T0.2  Reference scenario   ← produces the toy network the rest reuse
        │
        ├── T0.3  Performance
        ├── T0.4  Footguns
        └── T0.5  SUMO semantics
```

T0.1 and T0.2 run in parallel. T0.3, T0.4 and T0.5 run in parallel after T0.2.

## Status, 2026-08-18

| Ticket | State |
| --- | --- |
| T0.0 environment | ✅ complete — SUMO from PyPI, not Homebrew |
| T0.1 prior art | ✅ complete — build all five components |
| T0.2 reference scenario | ⚠️ complete **after correction** — the D-023 seeding mechanism was wrong and untested |
| T0.3 performance | ⚠️ complete **after correction** — found a D-031 contradiction and resolved it instead of escalating |
| T0.4 footguns | ⚠️ complete **after correction** — teleport distortion was measured in an invalid regime |
| T0.5 SUMO semantics | ⚠️ complete **after correction** — answered from documentation where the ticket demanded experiment; the jam-length claim was wrong |

Corrections and their evidence are in `spikes/M0_verify/` and folded into each
`research/M0_*.md`. One documentation-only claim survives unverified and T1.5 depends on it:
`jtrrouter`'s sink and `--max-edges-factor` behaviour.

## Exit

M0 is complete when `03_ROADMAP.md` M0's exit criteria are all checked, and when `D-002`,
`D-004`, `D-022` and `D-025` have each been either confirmed against measurement or amended.
**Amendment is a likely and acceptable outcome** — that is what the milestone is for.
