import os

APP_ENV = os.getenv("APP_ENV", "dev")

DASHBOARD_NAME = "AWS Cost Optimization Hub Dashboard"

AUTH_DISABLED = (os.getenv("AUTH_DISABLED") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

APP_BASE_URL = os.getenv("APP_BASE_URL")