"""The body of one `run_many` child process.

`run_many` starts one `spawn` process per run with `run_in_child` as its target
and the run's spec pickled to bytes. Two things follow from that shape:

* **The child decides what its exit means.** A run that returns exits 0; a run
  that raises writes its traceback to the path it was given and exits 1,
  quietly, so the console carries nothing but `run_many`'s progress. A child
  that dies -- `os._exit`, a signal, a segfault inside libsumo -- writes
  nothing, and the parent reads that from its exit code alone.
* **This module imports nothing heavy at the top**, and the spec stays bytes
  until the child is ready to unpickle it, so the child controls its
  environment before anything of SUMO is loaded.
"""

from __future__ import annotations

import pickle
import sys
import traceback
from pathlib import Path


def run_in_child(payload: bytes, traceback_path: str) -> None:
    """Run the pickled `RunSpec` in `payload`; on an exception, record it and exit 1."""
    try:
        from traffic_lab.experiments.runner import run_one

        run_one(pickle.loads(payload))
    except BaseException:
        Path(traceback_path).write_text(traceback.format_exc())
        sys.exit(1)
