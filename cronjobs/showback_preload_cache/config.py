import os


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

MAX_PARQUET_BYTES = int(
    os.getenv("ATHENA_CACHE_MAX_PARQUET_BYTES", "67108864")
)

# Redis config validation

if not REDIS_HOST or not REDIS_PASSWORD:
    raise ValueError("Redis host and password must not be empty")

if CACHE_TTL_SECONDS <= 0 or MAX_PARQUET_BYTES <= 0:
    raise ValueError("Cache TTL and maximum size must be positive")