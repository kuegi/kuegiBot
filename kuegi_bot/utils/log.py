import logging
import logging.handlers
import os


def setup_custom_logger(name="kuegi_bot",log_level=logging.INFO,
                        logToConsole= True,logToFile= False):
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if len(logger.handlers) == 0:
        if logToConsole:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(fmt='%(asctime)s - %(levelname)s:%(name)s - %(module)s - %(message)s'))
            logger.addHandler(handler)

        if logToFile:
            base = 'logs/'
            try:
                os.makedirs(base)
            except Exception:
                pass
            fh = logging.handlers.RotatingFileHandler(base+name+'.log', mode='a', maxBytes=200*1024, backupCount=50)
            fh.setFormatter(logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s'))
            fh.setLevel(logging.INFO)
            logger.addHandler(fh)

    return logger
