# M0 Environment — T0.0 findings

**Ticket:** `tickets/M0/T0.0_environment.md` · **Status:** complete
**Amends:** `D-004`

---

## Outcome

The environment is working, but **by a different route than the ticket specified**, and the
detour uncovered a real defect that would have surfaced mid-M1.

| Component | Version |
| --- | --- |
| Python | 3.12.1 arm64 |
| SUMO | SUMO 1.27.1 (`eclipse-sumo` PyPI distribution, arm64) |
| uv | 0.12.5 |
| Host | macOS, arm64 |

Verified working: `sumo`, `netconvert`, `netgenerate`, `jtrrouter`, `duarouter`,
and `import traci, libsumo, sumolib`.

---

## Finding 1 — Homebrew is the wrong install route on this machine

The ticket specified `brew tap dlr-ts/sumo && brew install sumo`. It failed, twice over:

1. **Homebrew 5 refuses untrusted third-party taps.**
   `Refusing to load formula dlr-ts/sumo/sumo from untrusted tap dlr-ts/sumo`. Proceeding
   would require `brew trust dlr-ts/sumo`, a persistent security-posture change on the
   developer's machine. Not taken.
2. **Architecture mismatch, which is the more serious one.** The host is `arm64` but
   Homebrew is installed at `/usr/local` — the Intel prefix. A Homebrew SUMO would likely
   have been x86_64, and **`libsumo` would not have imported into an arm64 Python.** That is
   exactly escalation condition 1 of T0.0, and `D-002` depends on libsumo for the ~10×
   speedup that makes M5 sweeps and M7 training affordable.

**Resolution.** Install SUMO as a **Python distribution** (`eclipse-sumo`, `libsumo`,
`traci`, `sumolib` on PyPI, published by DLR). This is strictly better than a system
package for this project:

- The SUMO version is **pinned in `uv.lock`**, which serves `D-008`'s manifest
  requirement and Principle 7 directly — reproducing an experiment reproduces its simulator.
- Architecture matches the Python interpreter by construction.
- No system modification, no tap to trust, no `SUMO_HOME` to set.

---

## Finding 2 — pyarrow and libsumo cannot share a process

**This is the finding that justifies the milestone.**

`libsumo` bundles libarrow 24.0.0. `D-004` specified pyarrow for Parquet results. Installed
together, uv warns; the warning is **not benign**. Reproduced:

```
pyarrow.lib.ArrowKeyError: Attempted to register factory for scheme 'file'
but that scheme is already registered.
```

Both libraries register the `file` filesystem scheme in the same process, and pyarrow's
filesystem API — which `pyarrow.parquet.write_table` goes through — breaks.

**Where it would have hit us.** T1.11's experiment runner runs a simulation via libsumo and
writes results to Parquet **in the same process**. Every run in every sweep. It would have
appeared at M1 as an unexplained crash after the simulation completed, with a message
pointing at a filesystem registry rather than at a version conflict.

### Test evidence

| Step | Result |
| --- | --- |
| `import libsumo` and `import pyarrow` together | ok (warning only) |
| Run a 100-step simulation via libsumo | ok |
| **polars** native parquet write and read back | **ok** |
| **pyarrow** `write_table` | **ArrowKeyError** |

**Resolution.** Drop pyarrow as a dependency. Polars reads and writes Parquet natively
(Rust arrow-rs) and DuckDB queries Parquet natively; neither needs pyarrow. Retested with
pyarrow removed: libsumo, polars and duckdb coexist, simulation runs, Parquet round-trips,
DuckDB queries the result. **The fix costs nothing and removes a dependency.**

---

## Consequences for the decision register

`D-004` amended on two points: SUMO is installed as a Python distribution rather than a
system package, and **pyarrow is explicitly excluded** with the reason recorded so nobody
re-adds it as an "obvious" companion to Parquet.

## What was not done

`SUMO_HOME` was not set, and is not needed — `sumolib.checkBinary()` resolves the binaries
from the installed distribution. Tickets and docs that assume `SUMO_HOME` should be read as
"SUMO tools are resolvable", which they are.
