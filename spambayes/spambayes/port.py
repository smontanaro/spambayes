try:
    # New in Python 2.5
    from hashlib import md5
except ImportError:
    # Python 2.4
    from md5 import new as md5

try:
    import gdbm
except ImportError:
    gdbm = None

