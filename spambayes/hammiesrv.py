#! /usr/bin/env python

# A server version of hammie.py


"""Usage: %(program)s [options] IP:PORT

Where:
    -h
        show usage and exit
    -p FILE
        use file as the persistent store.  loads data from this file if it
        exists, and saves data to this file at the end.  Default: %(DEFAULTDB)s
    -d
        use the DBM store instead of cPickle.  The file is larger and
        creating it is slower, but checking against it is much faster,
        especially for large word databases.

    IP
        IP address to bind (use 0.0.0.0 to listen on all IPs of this machine)
    PORT
        Port number to listen to.
"""

import SimpleXMLRPCServer
import getopt
import sys
import traceback
import xmlrpclib
import hammie

program = sys.argv[0] # For usage(); referenced by docstring above

# Default DB path
DEFAULTDB = hammie.DEFAULTDB

class HammieHandler(SimpleXMLRPCServer.SimpleXMLRPCRequestHandler):
    def do_POST(self):
        """Handles the HTTP POST request.

        Attempts to interpret all HTTP POST requests as XML-RPC calls,
        which are forwarded to the _dispatch method for handling.

        This one also prints out tracebacks, to help me debug :)
        """

        try:
            # get arguments
            data = self.rfile.read(int(self.headers["content-length"]))
            params, method = xmlrpclib.loads(data)

            # generate response
            try:
                response = self._dispatch(method, params)
                # wrap response in a singleton tuple
                response = (response,)
            except:
                # report exception back to server
                response = xmlrpclib.dumps(
                    xmlrpclib.Fault(1, "%s:%s" % (sys.exc_type, sys.exc_value))
                    )
            else:
                response = xmlrpclib.dumps(response, methodresponse=1)
        except:
            # internal error, report as HTTP server error
            traceback.print_exc()
            print `data`
            self.send_response(500)
            self.end_headers()
        else:
            # got a valid XML RPC response
            self.send_response(200)
            self.send_header("Content-type", "text/xml")
            self.send_header("Content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

            # shut down the connection
            self.wfile.flush()
            self.connection.shutdown(1)
            

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)


def main():
    """Main program; parse options and go."""
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hdp:')
    except getopt.error, msg:
        usage(2, msg)

    pck = DEFAULTDB
    usedb = False
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-p':
            pck = arg
        elif opt == "-d":
            usedb = True

    if len(args) != 1:
        usage(2, "IP:PORT not specified")

    ip, port = args[0].split(":")
    port = int(port)
    
    bayes = hammie.createbayes(pck, usedb)
    h = hammie.Hammie(bayes)

    server = SimpleXMLRPCServer.SimpleXMLRPCServer((ip, port), HammieHandler)
    server.register_instance(h)
    server.serve_forever()

if __name__ == "__main__":
    main()
