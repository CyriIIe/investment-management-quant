"""Configuration centralisée du collecteur MOEX."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "moex.sqlite3"

ISS_BASE_URL = "https://iss.moex.com"
TQOB_SECURITIES_ENDPOINT = "/iss/engines/stock/markets/bonds/boards/TQOB/securities.json?iss.meta=off"
REQUEST_INTERVAL_SECONDS = 1.1
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0
