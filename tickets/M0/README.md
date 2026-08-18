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

## Exit

M0 is complete when `03_ROADMAP.md` M0's exit criteria are all checked, and when `D-002`,
`D-004`, `D-022` and `D-025` have each been either confirmed against measurement or amended.
**Amendment is a likely and acceptable outcome** — that is what the milestone is for.
