import hashlib
import json
import os
import time
from io import BytesIO

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from redis import Redis

from config import REDIS_HOST, REDIS_PASSWORD, REDIS_PORT, CACHE_TTL_SECONDS

class CacheUnavailable(RuntimeError):
    """The cached snapshot is absent, stale or invalid."""


def cache_key(database, query):
    identity = json.dumps(
        [database, query],
        separators=(",", ":"),
    ).encode()

    digest = hashlib.sha256(identity).hexdigest()

    return f"coat:athena:parquet:v1:{digest}"


class RedisService:
    """Preserve the existing interface, but read exclusively from Redis."""

    def __init__(self):
        self.last_refreshed_at = None

    def run_query_to_df(self, database, query):
        maximum_age = int(CACHE_TTL_SECONDS)

        if maximum_age <= 0:
            raise ValueError("Cache maximum age must be positive")

        host = REDIS_HOST
        password = REDIS_PASSWORD

        if not host or not password:
            raise ValueError(
                "Redis host and password must not be empty"
            )

        with Redis(
            host=host,
            port=int(REDIS_PORT),
            password=password,
            ssl=True,
            ssl_cert_reqs="required",
            ssl_check_hostname=True,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=30,
        ) as client:
            payload = client.get(cache_key(database, query))

        if payload is None:
            raise CacheUnavailable(
                "No cached dataset is available. "
                "Check the cache-loading CronJob."
            )

        try:
            with BytesIO(payload) as buffer:
                metadata = pq.read_metadata(buffer).metadata or {}

                refreshed_at = float(
                    metadata[b"coat.snapshot_started_at"]
                )

                if not 0 <= time.time() - refreshed_at < maximum_age:
                    raise CacheUnavailable(
                        "The cached dataset is stale."
                    )

                buffer.seek(0)

                dataframe = pd.read_parquet(
                    buffer,
                    engine="pyarrow",
                )

        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            pa.ArrowException,
        ) as error:
            raise CacheUnavailable(
                "The cached dataset could not be decoded."
            ) from error

        self.last_refreshed_at = refreshed_at

        return dataframe