# M2 Tickets — Trace format and the 2D replay renderer

The visualization vertical slice (`03_ROADMAP.md` M2). Decouples visual replay from
the SUMO microsimulator (`D-009`, `D-030`) and produces rich research overlays.

## Status

**This table is the authoritative place M2 status is recorded.**

| Ticket | State | Description |
| --- | --- | --- |
| T2.1 trace recorder | ✅ merged 2026-10-13 | Trace schema, streaming writer, opt-in runner flag (`D-030`) |
| T2.2 trace reader | ⏳ ready | Trace deserializer, integrity validator, standalone loading |
| T2.3 2D replay engine | ⏳ ready | Headless/offline renderer decoupled from SUMO |
| T2.4 research overlays | ⏳ ready | Signal displays, queues, vehicle telemetry, live metrics HUD |
| T2.5 export & artifact | ⏳ ready | MP4/GIF export and congested run artifact for README |

## Dependency Order

```
T2.1 trace recorder ──→ T2.2 trace reader ──→ T2.3 replay engine ──→ T2.4 overlays ──→ T2.5 export
```

The critical path is sequential:
1. T2.1 produces the trace file from runs.
2. T2.2 reads and validates the trace file.
3. T2.3 renders the baseline 2D frames.
4. T2.4 draws the research overlays on frames.
5. T2.5 stitches frames into animated GIF/MP4 video for documentation.
