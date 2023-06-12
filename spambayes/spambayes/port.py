from hashlib import md5

try:
    import bsddb3
    bsddb = bsddb3
    del bsddb3
except ImportError:
    try:
        import bsddb
    except ImportError:
        bsddb = None

try:
    import dbm.gnu
except ImportError:
    gdbm = None
