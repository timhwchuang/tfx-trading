"""Single-instance lock for long-running FT-003 sweeps."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        synchronize = 0x00100000
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock_pid(lock_path: Path) -> int:
    try:
        text = lock_path.read_text(encoding="utf-8").strip()
        return int(text.split()[0]) if text else -1
    except (OSError, ValueError):
        return -1


class SweepInstanceLock:
    """Exclusive lock file; stale locks (dead PID) are replaced."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = Path(lock_path)
        self._fd: int | None = None

    def _raise_if_live_lock(self) -> None:
        pid = _read_lock_pid(self.lock_path)
        if _pid_alive(pid):
            raise RuntimeError(
                f"another sweep is running (pid={pid}); lock={self.lock_path}"
            )

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(3):
            if self.lock_path.exists():
                self._raise_if_live_lock()
                self.lock_path.unlink(missing_ok=True)

            try:
                fd = os.open(
                    str(self.lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                if self.lock_path.exists():
                    self._raise_if_live_lock()
                continue

            self._fd = fd
            os.write(fd, f"{os.getpid()} ft003_run_sweep\n".encode("utf-8"))
            return

        self._raise_if_live_lock()

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def __enter__(self) -> SweepInstanceLock:
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()
