#!/usr/bin/env python

"""
Read a message or a mailbox file on standard input, upload it to a
web browser and write it to standard output.

usage:  %(progname)s [-h] [-n] [-s server] [-p port]

Options:
    -h, --help    - print help and exit
    -n, --null    - suppress writing to standard output (default %(null)s)
    -s, --server= - provide alternate web server (default %(server)s)
    -p, --port=   - provide alternate server port (default %(port)s)
"""

import sys
import httplib
import mimetypes
import getopt
from spambayes.Options import options

progname = sys.argv[0]

__author__ = "Skip Montanaro <skip@pobox.com>"
__credits__ = "Spambayes gang, Wade Leftwich"

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

# appropriated verbatim from a recipe by Wade Leftwich in the Python
# Cookbook: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/146306

def post_multipart(host, selector, fields, files):
    """
    Post fields and files to an http host as multipart/form-data.  fields is
    a sequence of (name, value) elements for regular form fields.  files is
    a sequence of (name, filename, value) elements for data to be uploaded
    as files.  Return the server's response page.
    """
    content_type, body = encode_multipart_formdata(fields, files)
    h = httplib.HTTP(host)
    h.putrequest('POST', selector)
    h.putheader('content-type', content_type)
    h.putheader('content-length', str(len(body)))
    h.endheaders()
    h.send(body)
    errcode, errmsg, headers = h.getreply()
    return h.file.read()

def encode_multipart_formdata(fields, files):
    """
    fields is a sequence of (name, value) elements for regular form fields.
    files is a sequence of (name, filename, value) elements for data to be
    uploaded as files.  Return (content_type, body) ready for httplib.HTTP
    instance
    """
    BOUNDARY = '----------ThIs_Is_tHe_bouNdaRY_$'
    CRLF = '\r\n'
    L = []
    for (key, value) in fields:
        L.append('--' + BOUNDARY)
        L.append('Content-Disposition: form-data; name="%s"' % key)
        L.append('')
        L.append(value)
    for (key, filename, value) in files:
        L.append('--' + BOUNDARY)
        L.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
        L.append('Content-Type: %s' % get_content_type(filename))
        L.append('')
        L.append(value)
    L.append('--' + BOUNDARY + '--')
    L.append('')
    body = CRLF.join(L)
    content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
    return content_type, body

def get_content_type(filename):
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'

def usage(*args):
    defaults = {}
    for d in args:
        defaults.update(d)
    print __doc__ % defaults

def main(argv):
    null = False
    server = "localhost"
    port = options.html_ui_port

    try:
        opts, args = getopt.getopt(argv, "hns:p:",
                                   ["help", "null", "server=", "port="])
    except getopt.Error:
        usage(globals(), locals())
        sys.exit(1)

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage(globals(), locals())
            sys.exit(0)
        elif opt in ("-n", "--null"):
            null = True
        elif opt in ("-s", "--server"):
            server = arg
        elif opt in ("-p", "--port"):
            port = int(arg)

    if args:
        usage(globals(), locals())
        sys.exit(1)

    data = sys.stdin.read()
    post_multipart("%s:%d"%(server,port), "/upload", [],
                   [('file', 'message.dat', data)])
    sys.stdout.write(data)

if __name__ == "__main__":
    main(sys.argv[1:])
