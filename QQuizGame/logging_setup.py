import logging
import datetime
from pymongo import MongoClient


formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def init_logging_db():
    client = MongoClient('localhost', 27017)
    db = client["test_database"]
    updates = db["updates"]
    return updates


def parse_upd(update, type="none"):
    upd_dict = update.to_dict()
    upd_dict['utc_date'] = datetime.datetime.utcnow()
    upd_dict['action_type'] = type
    return upd_dict


def setup_logger(name, log_file, level=logging.INFO):
    """Function setup as many loggers as you want"""

    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


