#! /usr/bin/env python

"""A client for hammiesrv.

Just feed it your mail on stdin, and it spits out the same message
with a new X-Hammie-Disposition header.

"""

import xmlrpclib
import sys

RPCBASE="http://localhost:65000"

def main():
    msg = sys.stdin.read()
    try:
        x = xmlrpclib.ServerProxy(RPCBASE)
        m = xmlrpclib.Binary(msg)
        out = x.filter(m)
        print out
    except:
        if __debug__:
            import traceback
            traceback.print_exc()
        print msg

if __name__ == "__main__":
    main()
