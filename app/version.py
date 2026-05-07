"""App version info shown in the gear menu so the homelab can see what's running.

Git sha resolution order:
1. `BENTO_GIT_SHA` env var (set by the deploy command, e.g.
   `BENTO_GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build`)
2. `git rev-parse --short HEAD` from the project root (works in dev)
3. empty string (only the version number shows)
"""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

BENTO_VERSION = "0.1.0"


def _resolve_git_sha() -> str:
    sha = os.environ.get("BENTO_GIT_SHA", "").strip()
    if sha:
        return sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:  # FileNotFoundError on systems without git, etc.
        logger.debug("git rev-parse unavailable: %s", e)
    return ""


GIT_SHA = _resolve_git_sha()
