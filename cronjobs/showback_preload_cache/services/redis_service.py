import hashlib
import json
import logging
import time
from io import BytesIO

import pyarrow as pa
import pyarrow.parquet as pq
from redis import Redis

from config import (
    CACHE_TTL_SECONDS,
    MAX_PARQUET_BYTES,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
)


logger = logging.getLogger(__name__)


def cache_key(database, query):
    identity = json.dumps(
        [database, query],
        separators=(",", ":"),
    ).encode()

    digest = hashlib.sha256(identity).hexdigest()

    return f"coat:athena:parquet:v1:{digest}"


class RedisService:
    def __init__(self):
        self.client = Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            ssl=True,
            ssl_cert_reqs="required",
            ssl_check_hostname=True,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=30,
        )

    def ping(self):
        self.client.ping()

    def close(self):
        self.client.close()

    def store_dataframe(
        self,
        database,
        query,
        dataframe,
        snapshot_started_at,
    ):
        table = pa.Table.from_pandas(
            dataframe,
            preserve_index=False,
        )

        metadata = dict(table.schema.metadata or {})
        metadata[b"coat.snapshot_started_at"] = str(
            snapshot_started_at
        ).encode("ascii")

        table = table.replace_schema_metadata(metadata)

        with BytesIO() as buffer:
            pq.write_table(
                table,
                buffer,
                compression="zstd",
            )

            size = buffer.getbuffer().nbytes

            if size > MAX_PARQUET_BYTES:
                raise ValueError(
                    f"Compressed Parquet is {size:,} bytes; "
                    f"the configured maximum is {MAX_PARQUET_BYTES:,}. "
                    "Review Redis and pod sizing before increasing it."
                )

            remaining_lifetime = int(
                CACHE_TTL_SECONDS
                - (time.time() - snapshot_started_at)
            )

            if remaining_lifetime <= 0:
                raise TimeoutError(
                    "Snapshot exceeded its maximum age before publication"
                )

            # Readers see either the complete old file or the complete new file.
            self.client.set(
                cache_key(database, query),
                buffer.getvalue(),
                ex=remaining_lifetime,
            )

        logger.info(
            "Published Redis snapshot: rows=%s parquet_bytes=%s ttl_seconds=%s",
            len(dataframe),
            size,
            remaining_lifetime,
        )