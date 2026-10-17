"""Repository-relative locations, resolved from this file so the working directory never matters."""

import os
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH: Path = REPO_ROOT / "config.yaml"
CONFIG_PATH: Path = Path(os.environ.get("JOB_BOARD_CONFIG", str(DEFAULT_CONFIG_PATH)))
FRONTEND_DIST: Path = REPO_ROOT / "frontend" / "dist"
