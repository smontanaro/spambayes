"""Wrapper to open an appropriate dbm storage type."""

from spambayes.Options import options
import sys
import whichdb
import os

class error(Exception):
    pass

def open_dbhash(*args):
    """Open a bsddb hash."""
    import bsddb
    return bsddb.hashopen(*args)

def open_gdbm(*args):
    """Open a gdbm database."""
    from spambayes.port import gdbm
    if gdbm is not None:
        return gdbm.open(*args)
    raise ImportError("gdbm not available")

def open_best(*args):
    funcs = [open_dbhash, open_gdbm]
    for f in funcs:
        try:
            return f(*args)
        except ImportError:
            pass
    raise error("No dbm modules available!")

open_funcs = {
    "best": open_best,
    "dbhash": open_dbhash,
    "gdbm": open_gdbm,
    }

def open(db_name, mode):
    if os.path.exists(db_name) and \
       options.default("globals", "dbm_type") != \
       options["globals", "dbm_type"]:
        # let the file tell us what db to use
        dbm_type = whichdb.whichdb(db_name)
    else:
        # fresh file or overridden - open with what the user specified
        dbm_type = options["globals", "dbm_type"].lower()
    f = open_funcs.get(dbm_type)
    if f is None:
        raise error("Unknown dbm type: %s" % dbm_type)
    return f(db_name, mode)
