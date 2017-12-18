import logging

import os


def get_logger(lambda_function_name=None):
    """
    Return logger with formatter

    :param lambda_function_name:
    :return: object - logger
    """
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(lambda_function_name)
    logger.setLevel(os.environ.get("LOG_LEVEL", logging.DEBUG))
    logger.addFilter(logging.StreamHandler())
    return logger
