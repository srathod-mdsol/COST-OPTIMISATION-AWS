#!/usr/bin/env python3
from etl.orchestrator import ETLOrchestrator
from core.config import Config
from core.logger import setup_logger
import os

logger = setup_logger(__name__)

def unlock():
    db_path = Config.ETL_DB_PATH
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        return

    orchestrator = ETLOrchestrator(db_path)
    logger.info("Attempting to release ETL lock...")
    orchestrator.force_unlock()
    logger.info("ETL lock has been released successfully.")

if __name__ == "__main__":
    unlock()
