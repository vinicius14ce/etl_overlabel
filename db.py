import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.pool import Pool

load_dotenv()

def get_source_engine():
    return create_engine(os.environ["SOURCE_DB_URL"], pool_pre_ping=True)

def get_dest_engine():
    engine = create_engine(os.environ["DEST_DB_URL"], pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def set_datestyle(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("SET datestyle = 'DMY'")
        cursor.close()

    return engine

def setup_logger(name):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(log_dir / f"{name}.log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)

    return logger
