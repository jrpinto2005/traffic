# M0 Performance — transport and query strategy

**Ticket:** `tickets/M0/T0.3_performance.md` · **Status:** complete

---

## Method

Hardware: Apple M3, macOS arm64, Python 3.12.1.

The benchmark uses the reference scenario in `spikes/M0_reference/` and queries the fields M1 will actually need on every step:

- per vehicle: position, speed, type, lane id, `timeLoss`, `waitingTime`
- per lane: halting count, occupancy, vehicle count
- per signal: current state

Four combinations were measured:

1. TraCI + polling
2. TraCI + subscriptions
3. LibSUMO + polling
4. LibSUMO + subscriptions

Each combination was run twice; the table reports mean wall-clock seconds per simulated hour, with sample stdev in parentheses.

---

## Results

| Backend | Query strategy | Wall-clock / simulated hour |
| --- | --- | --- |
| TraCI | polling | 71.39 s ± 0.06 |
| TraCI | subscriptions | 7.08 s ± 0.06 |
| LibSUMO | polling | 1.43 s ± 0.01 |
| LibSUMO | subscriptions | 2.42 s ± 0.00 |

---

## Conclusion

- `D-002` is strongly confirmed: LibSUMO is not just faster, it is dramatically faster on this query pattern.
- `D-031` is also confirmed: subscriptions cut TraCI wall-clock by about 10× versus naive polling.
- The fastest measured combination was LibSUMO + polling, but the architectural choice still favours subscriptions because they are the correct seam for later sensor/model work and reduce TraCI overhead by an order of magnitude.

The benchmark script is `spikes/M0_reference/bench_performance.py`.
