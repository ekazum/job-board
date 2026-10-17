"""ASGI entry point: `uvicorn job_board.main:app` (or `python -m job_board.main`)."""

from functools import partial

import uvicorn

from job_board.app_config import AppConfig
from job_board.app_factory import AppFactory
from job_board.paths import CONFIG_PATH, FRONTEND_DIST

HOST = "127.0.0.1"
PORT = 8000

app = AppFactory(partial(AppConfig.from_yaml, CONFIG_PATH), FRONTEND_DIST).build()


def main() -> None:
    """Run the server on localhost:8000."""
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
