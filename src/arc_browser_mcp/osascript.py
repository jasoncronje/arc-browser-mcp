from __future__ import annotations

import subprocess

from .errors import ArcAutomationError


class OsascriptRunner:
    def run_jxa(self, script: str, *, timeout: float = 10.0) -> str:
        return self._run(["osascript", "-l", "JavaScript", "-e", script], timeout=timeout)

    def run_applescript(self, script: str, *, timeout: float = 10.0) -> str:
        return self._run(["osascript", "-e", script], timeout=timeout)

    def _run(self, args: list[str], *, timeout: float) -> str:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
        except FileNotFoundError as exc:
            raise ArcAutomationError("osascript is not available on this system") from exc
        except subprocess.TimeoutExpired as exc:
            raise ArcAutomationError("osascript timed out") from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout).strip()
            if not message:
                message = f"osascript failed with exit code {exc.returncode}"
            raise ArcAutomationError(message) from exc

        return result.stdout.strip()
