from pspam.options import options

import ZODB
from ZEO.ClientStorage import ClientStorage
import zLOG

import os

def logging():
    os.environ["STUPID_LOG_FILE"] = options.event_log_file
    os.environ["STUPID_LOG_SEVERITY"] = str(options.event_log_severity)
    zLOG.initialize()

def open():
    cs = ClientStorage(options.zeo_addr)
    db = ZODB.DB(cs, cache_size=options.cache_size)
    return db
