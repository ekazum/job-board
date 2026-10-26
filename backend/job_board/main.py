"""ASGI entry point: `uvicorn job_board.main:app` (or `python -m job_board.main`)."""

from functools import partial

import uvicorn
from dotenv import load_dotenv

from job_board.app_factory import AppFactory
from job_board.config.app_config import AppConfig
from job_board.config.paths import CONFIG_PATH, ENV_PATH, FRONTEND_DIST

HOST = "127.0.0.1"
PORT = 8000

load_dotenv(ENV_PATH)  # LLM API keys (GROQ_API_KEY, ...) from the repo's .env, which is git-ignored
app = AppFactory(partial(AppConfig.from_yaml, CONFIG_PATH), FRONTEND_DIST, config_path=CONFIG_PATH).build()


def main() -> None:
    """Run the server on localhost:8000."""
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
