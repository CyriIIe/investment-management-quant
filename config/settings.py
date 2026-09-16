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

# Univers de courbe : VOLTODAY et NUMTRADES décrivent la séance courante,
# pas une période historique. Tous les seuils sont modifiables ici uniquement.
MAX_DAYS_SINCE_LAST_TRANSACTION = 3.0
MIN_SESSION_VOLUME = 1_000.0
MIN_SESSION_TRANSACTIONS = 5
MAX_BID_ASK_SPREAD = 0.25
REJECT_IF_REQUIRED_LIQUIDITY_DATA_UNAVAILABLE = True

# TRADEMOMENT est stocké à titre de proxy, mais sa sémantique "dernière
# transaction" doit être confirmée avant toute utilisation dans le filtre.
TRADEMOMENT_IS_VERIFIED_LAST_TRANSACTION = False
# Lorsque TRADEMOMENT n'est pas documenté, l'activité de séance confirme qu'au
# moins une transaction a eu lieu aujourd'hui, sans prétendre la dater à la minute.
USE_SESSION_ACTIVITY_WHEN_TRADE_TIMESTAMP_UNVERIFIED = True
REQUIRE_POSITIVE_SESSION_ACTIVITY = True

# Moteur de courbe. Ces trois vérifications doivent rester explicites tant que
# docs/moex-fields.md ne peut pas être confirmé par un recoupement indépendant.
YIELD_UNIT_VERIFIED = True
DURATION_UNIT_VERIFIED = True
PRICE_CONVENTION_VERIFIED = True
YIELD_UNIT = "percent"
DURATION_UNIT = "days"
BASIS_POINTS_PER_PERCENT = 100.0

MIN_ELIGIBLE_BONDS_FOR_CURVE = 8
CURVE_POLYNOMIAL_DEGREE = 2
CURVE_ROBUST_LOSS = "soft_l1"
CURVE_ROBUST_F_SCALE = 0.10
MIN_RESIDUAL_HISTORY_POINTS = 5
ROBUST_MAD_SCALE = 1.4826
TOP_RESIDUALS_COUNT = 10
