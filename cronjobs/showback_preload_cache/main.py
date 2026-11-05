import logging
import time

from config import ATHENA_DATABASE, ATHENA_QUERY
from services.athena_service import AthenaService
from services.redis_service import RedisWriteService


logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    snapshot_started_at = time.time()
    timer = time.monotonic()

    redis_service = RedisWriteService()

    try:
        # Check Redis before incurring the Athena query cost.
        redis_service.ping()

        dataframe = AthenaService().run_query_to_df(
            ATHENA_DATABASE,
            ATHENA_QUERY,
        )

        redis_service.store_dataframe(
            ATHENA_DATABASE,
            ATHENA_QUERY,
            dataframe,
            snapshot_started_at,
        )

        logger.info(
            "Cache refresh completed in %.2f seconds",
            time.monotonic() - timer,
        )
    finally:
        redis_service.close()


if __name__ == "__main__":
    main()