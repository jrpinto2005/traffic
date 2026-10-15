# M3 Tickets — Imperfect Observation and the Sensing–Control Gap

The sensing and state estimation milestone (`03_ROADMAP.md` M3). Implements the parametric
camera sensor model, counting-with-decay state estimator, type boundaries, 2D visual divergence,
and the paired sensing-control gap ablation study (`D-005`, `D-017`, `D-021`, `D-033`).

## Status

**This table is the authoritative place M3 status is recorded.**

| Ticket | State | Description |
| --- | --- | --- |
| T3.1 camera sensor | ✅ complete | Parametric camera model: FOV, range, noise, latency, dropout (`D-021`) |
| T3.2 decay estimator | ✅ complete | Counting with exponential decay estimator for partial coverage (`D-021`) |
| T3.3 type boundary | ✅ complete | Strict type checking preventing TrueState leaks into controllers or estimators |
| T3.4 visual divergence | ✅ complete | 2D replay renderer overlay showing ground truth vs observations diverging |
| T3.5 sensing gap experiment | ✅ complete | Paired Monte Carlo evaluation, attribution analysis, and degradation curves |

## Dependency Order

```
T3.1 camera sensor ──┐
                    ├──→ T3.3 type boundary ──→ T3.4 visual divergence ──→ T3.5 experiments
T3.2 decay estimator ┘
```

The critical path:
1. T3.1 builds the degraded camera sensor model generating imperfect `Observation` streams.
2. T3.2 builds the decay estimator converting imperfect `Observation` into `EstimatedState`.
3. T3.3 verifies architectural integrity: no `TrueState` leaks to controllers or estimators.
4. T3.4 extends the 2D renderer to visually show truth vs observation divergence.
5. T3.5 executes the sensing-control gap ablation experiment, generating headline figures and reports.
