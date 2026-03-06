import logging
import time
from uuid import uuid4

from sqlmodel import Session

from app.config import settings
from app.database import engine, init_db
from app.logging_config import configure_logging
from app.services.alerts import process_pending_alerts
from app.services.ingestion import IngestionService
from app.utils import set_correlation_id

logger = logging.getLogger(__name__)


def run_worker() -> None:
    configure_logging()
    init_db()
    ingestion_service = IngestionService()
    last_ingestion_monotonic = 0.0

    logger.info("TradeShield worker started")
    while True:
        set_correlation_id(f"worker-{uuid4().hex[:10]}")
        with Session(engine) as session:
            current_monotonic = time.monotonic()
            result = None
            if current_monotonic - last_ingestion_monotonic >= settings.ingestion_interval_seconds:
                result = ingestion_service.run_cycle(session, trigger="scheduled", queue_alerts=True)
                last_ingestion_monotonic = current_monotonic

            dispatch = process_pending_alerts(session)
            if result:
                logger.info(
                    "Worker ingestion complete inserted=%s updated=%s queued_alerts=%s delivered=%s retries=%s",
                    result.inserted_count,
                    result.updated_count,
                    result.queued_alerts,
                    dispatch.delivered_count,
                    dispatch.retry_count,
                )
            elif dispatch.processed_count:
                logger.info(
                    "Worker delivery pass processed=%s delivered=%s retries=%s failed=%s",
                    dispatch.processed_count,
                    dispatch.delivered_count,
                    dispatch.retry_count,
                    dispatch.failed_count,
                )
        time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    run_worker()
