#! /usr/bin/env python

# A server version of hammie.py


"""Usage: %(program)s [options] IP:PORT

Where:
    -h
        show usage and exit
    -p FILE
        use file as the persistent store.  loads data from this file if it
        exists, and saves data to this file at the end.
    -d
        use the DBM store instead of cPickle.

    IP
        IP address to bind (use 0.0.0.0 to listen on all IPs of this machine)
    PORT
        Port number to listen to.
"""

import os
import SimpleXMLRPCServer
import getopt
import sys
import traceback
import xmlrpclib

from spambayes import hammie, Options
from spambayes.storage import open_storage

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


program = sys.argv[0] # For usage(); referenced by docstring above

class XMLHammie(hammie.Hammie):
    def score(self, msg, *extra):
        try:
            msg = msg.data
        except AttributeError:
            pass
        return xmlrpclib.Binary(hammie.Hammie.score(self, msg, *extra))

    def filter(self, msg, *extra):
        try:
            msg = msg.data
        except AttributeError:
            pass
        return xmlrpclib.Binary(hammie.Hammie.filter(self, msg, *extra))


def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__
    sys.exit(code)


def main():
    """Main program; parse options and go."""
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hdp:')
    except getopt.error, msg:
        usage(2, msg)

    options = Options.options

    dbname = options["Storage", "persistent_storage_file"]
    dbname = os.path.expanduser(dbname)
    usedb = options["Storage", "persistent_use_database"]
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-p':
            dbname = arg
        elif opt == "-d":
            usedb = True

    if len(args) != 1:
        usage(2, "IP:PORT not specified")

    ip, port = args[0].split(":")
    port = int(port)

    bayes = open_storage(dbname, usedb)
    h = XMLHammie(bayes)

    server = SimpleXMLRPCServer.SimpleXMLRPCServer((ip, port),
                                                   SimpleXMLRPCServer.SimpleXMLRPCRequestHandler)
    server.register_instance(h)
    server.serve_forever()

if __name__ == "__main__":
    main()
