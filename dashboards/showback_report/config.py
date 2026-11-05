import os


APP_ENV = os.getenv("APP_ENV")

APP_BASE_URL = os.getenv("APP_BASE_URL")

DASHBOARD_NAME = "Hosting Showback Report"

# Auth0 config

AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID")

AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET")

AUTH0_DOMAIN = (os.getenv("AUTH0_DOMAIN") or "").strip().rstrip("/")

AUTH_DISABLED = (os.getenv("AUTH_DISABLED") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Athena config

ATHENA_REGION = os.getenv("ATHENA_REGION")

ATHENA_ROLE = os.getenv("ATHENA_ROLE")

ATHENA_OUTPUT_LOCATION = os.getenv("ATHENA_OUTPUT_LOCATION")

ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP")

ATHENA_DATABASE = os.getenv(
    "ATHENA_CACHE_DATABASE",
    "cloud_optimisation_datamarts",
)

ATHENA_QUERY = os.getenv(
    "ATHENA_CACHE_QUERY",
    "SELECT * FROM fct_net_unblended_cost_categorised;",
)

# Redis config

REDIS_HOST = os.environ["REDIS_HOST"]

REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

REDIS_PASSWORD = os.environ["REDIS_PASSWORD"]

CACHE_TTL_SECONDS = int(
    os.getenv("ATHENA_CACHE_TTL_SECONDS", "3024000")
)

# Redis config validation

if not REDIS_HOST or not REDIS_PASSWORD:
    raise ValueError("Redis host and password must not be empty")

if CACHE_TTL_SECONDS <= 0:
    raise ValueError("Cache TTL and maximum size must be positive")