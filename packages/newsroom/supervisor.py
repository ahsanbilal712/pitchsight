"""Supervisor: keeps one newsroom worker alive.

    python -m newsroom.supervisor [worker args...]      # e.g. --mode replay --match m_4242

Starts `python -m newsroom.worker <args>`, writes the worker pid to WHYLINE_WORKER_PIDFILE (default
data/runtime/newsroom.pid) and restarts it within 2 s whenever it exits (the demo's SIGKILL, a crash). Each restart
logs `restart pid=<new pid>`. SIGTERM or SIGINT stops the worker and the supervisor.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from newsroom.resume import demo_log

ROOT = Path(__file__).resolve().parents[2]
POLL_S = 0.1


def pidfile() -> Path:
    p = Path(os.environ.get("WHYLINE_WORKER_PIDFILE", ROOT / "data" / "runtime" / "newsroom.pid"))
    return p if p.is_absolute() else ROOT / p


class Supervisor:
    def __init__(self, worker_args: list[str]) -> None:
        self.args = [sys.executable, "-m", "newsroom.worker", *worker_args]
        self.proc: subprocess.Popen | None = None
        self.stopping = False
        self.restarts = 0

    def start(self) -> int:
        path = os.pathsep.join(p for p in (str(ROOT / "packages"), os.environ.get("PYTHONPATH")) if p)
        self.proc = subprocess.Popen(self.args, cwd=ROOT, env={**os.environ, "PYTHONPATH": path})
        path = pidfile()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(self.proc.pid))
        return self.proc.pid

    def stop(self, *_sig) -> None:
        self.stopping = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.start()
        while not self.stopping:
            if self.proc.poll() is not None and not self.stopping:
                pid = self.start()
                self.restarts += 1
                demo_log(f"restart pid={pid}")
            time.sleep(POLL_S)
        return 0


def main() -> int:
    import logging

    logging.basicConfig(level=os.environ.get("WHYLINE_LOG", "INFO"),
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    return Supervisor(sys.argv[1:]).run()


if __name__ == "__main__":
    sys.exit(main())
