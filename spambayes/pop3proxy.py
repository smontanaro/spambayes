#!/usr/bin/env python

"""A POP3 proxy that works with classifier.py, and adds a simple
X-Hammie-Disposition header (Yes or No) to each incoming email.
You point pop3proxy at your POP3 server, and configure your email
client to collect mail from the proxy then filter on the added
header.  Usage:

    pop3proxy.py [options] [<server> [<server port>]]
        <server> is the name of your real POP3 server
        <port>   is the port number of your real POP3 server, which
                 defaults to 110.

        options:
            -z      : Runs a self-test and exits.
            -t      : Runs a test POP3 server on port 8110 (for testing).
            -h      : Displays this help message.

            -p FILE : use the named data file
            -d      : the file is a DBM file rather than a pickle
            -l port : proxy listens on this port number (default 110)
            -u port : User interface listens on this port number
                      (default 8880; Browse http://localhost:8880/)
            -b      : Launch a web browser showing the user interface.

        All command line arguments and switches take their default
        values from the [Hammie], [pop3proxy] and [html_ui] sections
        of bayescustomize.ini.

For safety, and to help debugging, the whole POP3 conversation is
written out to _pop3proxy.log for each run.

To make rebuilding the database easier, trained messages are appended
to _pop3proxyham.mbox and _pop3proxyspam.mbox.
"""

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Richie Hindle <richie@entrian.com>"
__credits__ = "Tim Peters, Neale Pickett, all the spambayes contributors."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


todo = """

User interface improvements:

 o Once the training stuff is on a separate page, make the paste box
   bigger.
 o Deployment: Windows executable?  atlaxwin and ctypes?  Or just
   webbrowser?
 o Can it cleanly dynamically update its status display while having a
   POP3 converation?  Hammering reload sucks.
 o Add a command to save the database without shutting down, and one to
   reload the database.
 o Save the Status (num classified, etc.) between sessions.


New features:

 o (Re)training interface - one message per line, quick-rendering table.
 o "Send me an email every [...] to remind me to train on new
   messages."
 o "Send me a status email every [...] telling how many mails have been
   classified, etc."
 o Possibly integrate Tim Stone's SMTP code - make it use async, make
   the training code update (rather than replace!) the database.
 o Option to keep trained messages and view potential FPs and FNs to
   correct them.
 o Allow use of the UI without the POP3 proxy.


Code quality:

 o Move the UI into its own module.
 o Eventually, pull the common HTTP code from pop3proxy.py and Entrian
   Debugger into a library.


Info:

 o Slightly-wordy index page; intro paragraph for each page.
 o In both stats and training results, report nham and nspam - warn if
   they're very different (for some value of 'very').
 o "Links" section (on homepage?) to project homepage, mailing list,
   etc.


Gimmicks:

 o Classify a web page given a URL.
 o Graphs.  Of something.  Who cares what?
 o Zoe...!

"""

import sys, re, operator, errno, getopt, cPickle, cStringIO, time
import socket, asyncore, asynchat, cgi, urlparse, webbrowser
import classifier, tokenizer, hammie
from Options import options

# HEADER_EXAMPLE is the longest possible header - the length of this one
# is added to the size of each message.
HEADER_FORMAT = '%s: %%s\r\n' % options.hammie_header_name
HEADER_EXAMPLE = '%s: xxxxxxxxxxxxxxxxxxxx\r\n' % options.hammie_header_name

# This keeps the global status of the module - the command-line options,
# how many mails have been classified, how many active connections there
# are, and so on.
class Status:
    pass
status = Status()


class Listener(asyncore.dispatcher):
    """Listens for incoming socket connections and spins off
    dispatchers created by a factory callable.
    """

    def __init__(self, port, factory, factoryArgs=(),
                 socketMap=asyncore.socket_map):
        asyncore.dispatcher.__init__(self, map=socketMap)
        self.socketMap = socketMap
        self.factory = factory
        self.factoryArgs = factoryArgs
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        self.set_socket(s, socketMap)
        self.set_reuse_addr()
        print "%s listening on port %d." % (self.__class__.__name__, port)
        self.bind(('', port))
        self.listen(5)

    def handle_accept(self):
        clientSocket, clientAddress = self.accept()
        args = [clientSocket] + list(self.factoryArgs)
        if self.socketMap != asyncore.socket_map:
            self.factory(*args, **{'socketMap': self.socketMap})
        else:
            self.factory(*args)


class BrighterAsyncChat(asynchat.async_chat):
    """An asynchat.async_chat that doesn't give spurious warnings on
    receiving an incoming connection, and lets SystemExit cause an
    exit."""

    def handle_connect(self):
        """Suppress the asyncore "unhandled connect event" warning."""
        pass

    def handle_error(self):
        """Let SystemExit cause an exit."""
        type, v, t = sys.exc_info()
        if type == SystemExit:
            raise
        else:
            asynchat.async_chat.handle_error(self)


class ServerLineReader(BrighterAsyncChat):
    """An async socket that reads lines from a remote server and
    simply calls a callback with the data.  The BayesProxy object
    can't connect to the real POP3 server and talk to it
    synchronously, because that would block the process."""

    def __init__(self, serverName, serverPort, lineCallback):
        BrighterAsyncChat.__init__(self)
        self.lineCallback = lineCallback
        self.request = ''
        self.set_terminator('\r\n')
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.connect((serverName, serverPort))
        except socket.error, e:
            print >>sys.stderr, "Can't connect to %s:%d: %s" % \
                                (serverName, serverPort, e)
            self.close()
            self.lineCallback('')   # "The socket's been closed."

    def collect_incoming_data(self, data):
        self.request = self.request + data

    def found_terminator(self):
        self.lineCallback(self.request + '\r\n')
        self.request = ''

    def handle_close(self):
        self.lineCallback('')
        self.close()


class POP3ProxyBase(BrighterAsyncChat):
    """An async dispatcher that understands POP3 and proxies to a POP3
    server, calling `self.onTransaction(request, response)` for each
    transaction. Responses are not un-byte-stuffed before reaching
    self.onTransaction() (they probably should be for a totally generic
    POP3ProxyBase class, but BayesProxy doesn't need it and it would
    mean re-stuffing them afterwards).  self.onTransaction() should
    return the response to pass back to the email client - the response
    can be the verbatim response or a processed version of it.  The
    special command 'KILL' kills it (passing a 'QUIT' command to the
    server).
    """

    def __init__(self, clientSocket, serverName, serverPort):
        BrighterAsyncChat.__init__(self, clientSocket)
        self.request = ''
        self.response = ''
        self.set_terminator('\r\n')
        self.command = ''           # The POP3 command being processed...
        self.args = ''              # ...and its arguments
        self.isClosing = False      # Has the server closed the socket?
        self.seenAllHeaders = False # For the current RETR or TOP
        self.startTime = 0          # (ditto)
        self.serverSocket = ServerLineReader(serverName, serverPort,
                                             self.onServerLine)

    def onTransaction(self, command, args, response):
        """Overide this.  Takes the raw request and the response, and
        returns the (possibly processed) response to pass back to the
        email client.
        """
        raise NotImplementedError

    def onServerLine(self, line):
        """A line of response has been received from the POP3 server."""
        isFirstLine = not self.response
        self.response = self.response + line

        # Is this the line that terminates a set of headers?
        self.seenAllHeaders = self.seenAllHeaders or line in ['\r\n', '\n']

        # Has the server closed its end of the socket?
        if not line:
            self.isClosing = True

        # If we're not processing a command, just echo the response.
        if not self.command:
            self.push(self.response)
            self.response = ''

        # Time out after 30 seconds for message-retrieval commands if
        # all the headers are down.  The rest of the message will proxy
        # straight through.
        if self.command in ['TOP', 'RETR'] and \
           self.seenAllHeaders and time.time() > self.startTime + 30:
            self.onResponse()
            self.response = ''
        # If that's a complete response, handle it.
        elif not self.isMultiline() or line == '.\r\n' or \
           (isFirstLine and line.startswith('-ERR')):
            self.onResponse()
            self.response = ''

    def isMultiline(self):
        """Returns True if the request should get a multiline
        response (assuming the response is positive).
        """
        if self.command in ['USER', 'PASS', 'APOP', 'QUIT',
                            'STAT', 'DELE', 'NOOP', 'RSET', 'KILL']:
            return False
        elif self.command in ['RETR', 'TOP']:
            return True
        elif self.command in ['LIST', 'UIDL']:
            return len(args) == 0
        else:
            # Assume that an unknown command will get a single-line
            # response.  This should work for errors and for POP-AUTH,
            # and is harmless even for multiline responses - the first
            # line will be passed to onTransaction and ignored, then the
            # rest will be proxied straight through.
            return False

    def collect_incoming_data(self, data):
        """Asynchat override."""
        self.request = self.request + data

    def found_terminator(self):
        """Asynchat override."""
        verb = self.request.strip().upper()
        if verb == 'KILL':
            self.shutdown(2)
            self.close()
            raise SystemExit
        elif verb == 'CRASH':
            # For testing
            x = 0
            y = 1/x

        self.serverSocket.push(self.request + '\r\n')
        if self.request.strip() == '':
            # Someone just hit the Enter key.
            self.command = self.args = ''
        else:
            # A proper command.
            splitCommand = self.request.strip().split(None, 1)
            self.command = splitCommand[0].upper()
            self.args = splitCommand[1:]
            self.startTime = time.time()

        self.request = ''

    def onResponse(self):
        # Pass the request and the raw response to the subclass and
        # send back the cooked response.
        if self.response:
            cooked = self.onTransaction(self.command, self.args, self.response)
            self.push(cooked)

        # If onServerLine() decided that the server has closed its
        # socket, close this one when the response has been sent.
        if self.isClosing:
            self.close_when_done()

        # Reset.
        self.command = ''
        self.args = ''
        self.isClosing = False
        self.seenAllHeaders = False


class BayesProxyListener(Listener):
    """Listens for incoming email client connections and spins off
    BayesProxy objects to serve them.
    """

    def __init__(self, serverName, serverPort, proxyPort, bayes):
        proxyArgs = (serverName, serverPort, bayes)
        Listener.__init__(self, proxyPort, BayesProxy, proxyArgs)


class BayesProxy(POP3ProxyBase):
    """Proxies between an email client and a POP3 server, inserting
    judgement headers.  It acts on the following POP3 commands:

     o STAT:
        o Adds the size of all the judgement headers to the maildrop
          size.

     o LIST:
        o With no message number: adds the size of an judgement header
          to the message size for each message in the scan listing.
        o With a message number: adds the size of an judgement header
          to the message size.

     o RETR:
        o Adds the judgement header based on the raw headers and body
          of the message.

     o TOP:
        o Adds the judgement header based on the raw headers and as
          much of the body as the TOP command retrieves.  This can
          mean that the header might have a different value for
          different calls to TOP, or for calls to TOP vs. calls to
          RETR.  I'm assuming that the email client will either not
          make multiple calls, or will cope with the headers being
          different.
    """

    def __init__(self, clientSocket, serverName, serverPort, bayes):
        # Open the log file *before* calling __init__ for the base
        # class, 'cos that might call send or recv.
        self.bayes = bayes
        self.logFile = open('_pop3proxy.log', 'wb')
        POP3ProxyBase.__init__(self, clientSocket, serverName, serverPort)
        self.handlers = {'STAT': self.onStat, 'LIST': self.onList,
                         'RETR': self.onRetr, 'TOP': self.onTop}
        status.totalSessions += 1
        status.activeSessions += 1
        self.isClosed = False

    def send(self, data):
        """Logs the data to the log file."""
        self.logFile.write(data)
        self.logFile.flush()
        try:
            return POP3ProxyBase.send(self, data)
        except socket.error:
            # The email client has closed the connection - 40tude Dialog
            # does this immediately after issuing a QUIT command,
            # without waiting for the response.
            self.close()

    def recv(self, size):
        """Logs the data to the log file."""
        data = POP3ProxyBase.recv(self, size)
        self.logFile.write(data)
        self.logFile.flush()
        return data

    def close(self):
        # This can be called multiple times by async.
        if not self.isClosed:
            self.isClosed = True
            status.activeSessions -= 1
            POP3ProxyBase.close(self)

    def onTransaction(self, command, args, response):
        """Takes the raw request and response, and returns the
        (possibly processed) response to pass back to the email client.
        """
        handler = self.handlers.get(command, self.onUnknown)
        return handler(command, args, response)

    def onStat(self, command, args, response):
        """Adds the size of all the judgement headers to the maildrop
        size."""
        match = re.search(r'^\+OK\s+(\d+)\s+(\d+)(.*)\r\n', response)
        if match:
            count = int(match.group(1))
            size = int(match.group(2)) + len(HEADER_EXAMPLE) * count
            return '+OK %d %d%s\r\n' % (count, size, match.group(3))
        else:
            return response

    def onList(self, command, args, response):
        """Adds the size of an judgement header to the message
        size(s)."""
        if response.count('\r\n') > 1:
            # Multiline: all lines but the first contain a message size.
            lines = response.split('\r\n')
            outputLines = [lines[0]]
            for line in lines[1:]:
                match = re.search('^(\d+)\s+(\d+)', line)
                if match:
                    number = int(match.group(1))
                    size = int(match.group(2)) + len(HEADER_EXAMPLE)
                    line = "%d %d" % (number, size)
                outputLines.append(line)
            return '\r\n'.join(outputLines)
        else:
            # Single line.
            match = re.search('^\+OK\s+(\d+)(.*)\r\n', response)
            if match:
                size = int(match.group(1)) + len(HEADER_EXAMPLE)
                return "+OK %d%s\r\n" % (size, match.group(2))
            else:
                return response

    def onRetr(self, command, args, response):
        """Adds the judgement header based on the raw headers and body
        of the message."""
        # Use '\n\r?\n' to detect the end of the headers in case of
        # broken emails that don't use the proper line separators.
        if re.search(r'\n\r?\n', response):
            # Break off the first line, which will be '+OK'.
            ok, message = response.split('\n', 1)

            # Now find the spam disposition and add the header.
            prob = self.bayes.spamprob(tokenizer.tokenize(message))
            if command == 'RETR':
                status.numEmails += 1
            if prob < options.ham_cutoff:
                disposition = options.header_ham_string
                if command == 'RETR':
                    status.numHams += 1
            elif prob > options.spam_cutoff:
                disposition = options.header_spam_string
                if command == 'RETR':
                    status.numSpams += 1
            else:
                disposition = options.header_unsure_string
                if command == 'RETR':
                    status.numUnsure += 1

            headers, body = re.split(r'\n\r?\n', response, 1)
            headers = headers + "\n" + HEADER_FORMAT % disposition + "\r\n"
            return headers + body
        else:
            # Must be an error response.
            return response

    def onTop(self, command, args, response):
        """Adds the judgement header based on the raw headers and as
        much of the body as the TOP command retrieves."""
        # Easy (but see the caveat in BayesProxy.__doc__).
        return self.onRetr(command, args, response)

    def onUnknown(self, command, args, response):
        """Default handler; returns the server's response verbatim."""
        return response


class UserInterfaceListener(Listener):
    """Listens for incoming web browser connections and spins off
    UserInterface objects to serve them."""

    def __init__(self, uiPort, bayes, socketMap=asyncore.socket_map):
        uiArgs = (bayes,)
        Listener.__init__(self, uiPort, UserInterface, uiArgs, socketMap=socketMap)


# Until the user interface has had a wider audience, I won't pollute the
# project with .gif files and the like.  Here's the viking helmet.
import base64
helmet = base64.decodestring(
"""R0lGODlhIgAYAPcAAEJCRlVTVGNaUl5eXmtaVm9lXGtrZ3NrY3dvZ4d0Znt3dImHh5R+a6GDcJyU
jrSdjaWlra2tra2tta+3ur2trcC9t7W9ysDDyMbGzsbS3r3W78bW78be78be973e/8bn/86pjNav
kc69re/Lrc7Ly9ba4vfWveTh5M7e79be79bn797n7+fr6+/v5+/v7/f3787e987n987n/9bn99bn
/9bv/97n997v++fv9+f3/+/v9+/3//f39/f/////9////wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACH5BAEAAB4ALAAAAAAiABgA
AAj+AD0IHEiwoMGDA2XI8PBhxg2EECN+YJHjwwccOz5E3FhQBgseMmK44KGRo0kaLHzQENljoUmO
NE74uGHDxQ8aL2GmzFHzZs6NNFr8yKHC5sOfEEUOVcHiR8aNFksi/LCCx1KZPXAilLHBAoYMMSB6
9DEUhsyhUgl+wOBAwQIHFsIapGpzaIcTVnvcSOsBhgUFBgYUMKAgAgqNH2J0aPjxR9YPJerqlYEi
w4YYExQM2FygwIHCKVBgiBChBIsXP5wu3HD2Bw8MC2JD0CygAIHOnhU4cLDA7QWrqfd6iBE5dQsH
BgJvHiDgNoID0A88V6AAAQSyjl16QIHXBwnNAwDIBAhAwDmDBAjQHyiAIPkC7DnUljhxwkGAAQHE
B+icIAGD8+clUMByCNjUUkEdlHCBAvflF0BtB/zHQAMSCjhYYBXsoFVBMWAQWH4AAFBbAg2UWOID
FK432AEO2ABRBwtsFuKDBTSAYgMghBDCAwwgwB4CClQAQ0R/4RciAQjYyMADIIwwAggN+PeWBTPw
VdAHHEjA4IMR8ojjCCaEEGUCFcygnUQxaEndbhBAwKQIFVAAgQMQHPZTBxrkqUEHfHLAAZ+AdgBR
QAAAOw==""")


class UserInterface(BrighterAsyncChat):
    """Serves the HTML user interface of the proxy."""

    # A couple of notes about the HTML here:
    #  o I've tried to keep content and presentation separate using
    #    one main stylesheet - no <font> tags, and no inline stylesheets
    #  o Form fields must specify their name and value attributes like
    #    this: "... name='n' value='v' ..." even if there is no default
    #    value.  This is so that setFieldValue can set the value.

    header = """<html><head><title>Spambayes proxy: %s</title>
             <style>
             body { font: 90%% arial, swiss, helvetica; margin: 0 }
             table { font: 90%% arial, swiss, helvetica }
             form { margin: 0 }
             .banner { background: #c0e0ff; padding=5; padding-left: 15;
                       border-top: 1px solid black;
                       border-bottom: 1px solid black }
             .header { font-size: 133%% }
             .content { margin: 15 }
             .sectiontable { border: 1px solid #808080; width: 95%% }
             .sectionheading { background: fffae0; padding-left: 1ex;
                               border-bottom: 1px solid #808080;
                               font-weight: bold }
             .sectionbody { padding: 1em }
             </style>
             </head>\n"""

    bodyStart = """<body>
                <div class='banner'>
                <img src='/helmet.gif' align='absmiddle'>
                <span class='header'>&nbsp;Spambayes proxy: %s</span></div>
                <div class='content'>\n"""

    footer = """</div>
             <form action='/shutdown' method='POST'>
             <table width='100%%' cellspacing='0'>
             <tr><td class='banner'>&nbsp;<a href='/'>Spambayes Proxy</a>,
             %s.
             <a href='http://www.spambayes.org/'>Spambayes.org</a></td>
             <td align='right' class='banner'>
             %s
             </td></tr></table></form>
             </body></html>\n"""

    shutdownDB = """<input type='submit' name='how' value='Shutdown'>"""

    shutdownPickle = shutdownDB + """&nbsp;&nbsp;
            <input type='submit' name='how' value='Save &amp; shutdown'>"""

    pageSection = """<table class='sectiontable' cellspacing='0'>
                  <tr><td class='sectionheading'>%s</td></tr>
                  <tr><td class='sectionbody'>%s</td></tr></table>
                  &nbsp;<br>\n"""

    summary = """POP3 proxy running on port <b>%(proxyPort)d</b>,
              proxying to <b>%(serverName)s:%(serverPort)d</b>.<br>
              Active POP3 conversations: <b>%(activeSessions)d</b>.<br>
              POP3 conversations this session: <b>%(totalSessions)d</b>.<br>
              Emails classified this session: <b>%(numSpams)d</b> spam,
                <b>%(numHams)d</b> ham, <b>%(numUnsure)d</b> unsure.
              """

    wordQuery = """<form action='/wordquery'>
                <input name='word' value='' type='text' size='30'>
                <input type='submit' value='Tell me about this word'>
                </form>"""

    upload = """<form action='/%s' method='POST'
                enctype='multipart/form-data'>
             Either upload a message file:
             <input type='file' name='file' value=''><br>
             Or paste the whole message (incuding headers) here:<br>
             <textarea name='text' rows='3' cols='60'></textarea><br>
             %s
             </form>"""

    uploadSumbit = """<input type='submit' name='which' value='%s'>"""

    train = upload % ('train',
                      (uploadSumbit % "Train as Spam") + "&nbsp;" + \
                      (uploadSumbit % "Train as Ham"))

    classify = upload % ('classify', uploadSumbit % "Classify")

    def __init__(self, clientSocket, bayes, socketMap=asyncore.socket_map):
        # Grumble: asynchat.__init__ doesn't take a 'map' argument,
        # hence the two-stage construction.
        BrighterAsyncChat.__init__(self)
        BrighterAsyncChat.set_socket(self, clientSocket, socketMap)
        self.bayes = bayes
        self.request = ''
        self.set_terminator('\r\n\r\n')
        self.helmet = helmet

    def collect_incoming_data(self, data):
        """Asynchat override."""
        self.request = self.request + data

    def found_terminator(self):
        """Asynchat override.
        Read and parse the HTTP request and call an on<Command> handler."""
        requestLine, headers = (self.request+'\r\n').split('\r\n', 1)
        try:
            method, url, version = requestLine.strip().split()
        except ValueError:
            self.pushError(400, "Malformed request: '%s'" % requestLine)  # XXX: 400??
            self.close_when_done()
        else:
            method = method.upper()
            _, _, path, _, query, _ = urlparse.urlparse(url)
            params = cgi.parse_qs(query, keep_blank_values=True)
            if self.get_terminator() == '\r\n\r\n' and method == 'POST':
                # We need to read a body; set a numeric async_chat terminator.
                match = re.search(r'(?i)content-length:\s*(\d+)', headers)
                self.set_terminator(int(match.group(1)))
                self.request = self.request + '\r\n\r\n'
                return

            if type(self.get_terminator()) is type(1):
                # We've just read the body of a POSTed request.
                self.set_terminator('\r\n\r\n')
                body = self.request.split('\r\n\r\n', 1)[1]
                match = re.search(r'(?i)content-type:\s*([^\r\n]+)', headers)
                contentTypeHeader = match.group(1)
                contentType, pdict = cgi.parse_header(contentTypeHeader)
                if contentType == 'multipart/form-data':
                    # multipart/form-data - probably a file upload.
                    bodyFile = cStringIO.StringIO(body)
                    params.update(cgi.parse_multipart(bodyFile, pdict))
                else:
                    # A normal x-www-form-urlencoded.
                    params.update(cgi.parse_qs(body, keep_blank_values=True))

            # Convert the cgi params into a simple dictionary.
            plainParams = {}
            for name, value in params.iteritems():
                plainParams[name] = value[0]
            self.onRequest(path, plainParams)
            self.close_when_done()

    def onRequest(self, path, params):
        """Handles a decoded HTTP request."""
        if path == '/':
            path = '/Home'

        if path == '/helmet.gif':
            # XXX Why doesn't Expires work?  Must read RFC 2616 one day.
            inOneHour = time.gmtime(time.time() + 3600)
            expiryDate = time.strftime('%a, %d %b %Y %H:%M:%S GMT', inOneHour)
            extraHeaders = {'Expires': expiryDate}
            self.pushOKHeaders('image/gif', extraHeaders)
            self.push(self.helmet)
        else:
            try:
                name = path[1:].capitalize()
                handler = getattr(self, 'on' + name)
            except AttributeError:
                self.pushError(404, "Not found: '%s'" % path)
            else:
                # This is a request for a valid page; run the handler.
                self.pushOKHeaders('text/html')
                self.pushPreamble(name)
                handler(params)
                timeString = time.asctime(time.localtime())
                if status.useDB:
                    self.push(self.footer % (timeString, self.shutdownDB))
                else:
                    self.push(self.footer % (timeString, self.shutdownPickle))

    def pushOKHeaders(self, contentType, extraHeaders={}):
        timeNow = time.gmtime(time.time())
        httpNow = time.strftime('%a, %d %b %Y %H:%M:%S GMT', timeNow)
        self.push("HTTP/1.1 200 OK\r\n")
        self.push("Connection: close\r\n")
        self.push("Content-Type: %s\r\n" % contentType)
        self.push("Date: %s\r\n" % httpNow)
        for name, value in extraHeaders.items():
            self.push("%s: %s\r\n" % (name, value))
        self.push("\r\n")

    def pushError(self, code, message):
        self.push("HTTP/1.0 %d Error\r\n" % code)
        self.push("Content-Type: text/html\r\n")
        self.push("\r\n")
        self.push("<html><body><p>%d %s</p></body></html>" % (code, message))

    def pushPreamble(self, name):
        self.push(self.header % name)
        if name == 'Home':
            homeLink = name
        else:
            homeLink = "<a href='/'>Home</a> > %s" % name
        self.push(self.bodyStart % homeLink)

    def setFieldValue(self, form, name, value):
        """Sets the default value of a field in a form.  See the comment
        at the top of this class for how to specify HTML that works with
        this function.  (This is exactly what Entrian PyMeld is for, but
        that ships under the Sleepycat License.)"""
        match = re.search(r"\s+name='%s'\s+value='([^']*)'" % name, form)
        if match:
            quotedValue = re.sub("'", "&#%d;" % ord("'"), value)
            return form[:match.start(1)] + quotedValue + form[match.end(1):]
        else:
            print >>sys.stderr, "Warning: setFieldValue('%s') failed" % name
            return form

    def onHome(self, params):
        """Serve up the homepage."""
        body = (self.pageSection % ('Status', self.summary % status.__dict__)+
                self.pageSection % ('Train', self.train)+
                self.pageSection % ('Classify a message', self.classify)+
                self.pageSection % ('Word query', self.wordQuery))
        self.push(body)

    def onShutdown(self, params):
        """Shutdown the server, saving the pickle if requested to do so."""
        if params['how'].lower().find('save') >= 0:
            if not status.useDB and status.pickleName:
                self.push("<b>Saving...</b>")
                self.push(' ')  # Acts as a flush for small buffers.
                fp = open(status.pickleName, 'wb')
                cPickle.dump(self.bayes, fp, 1)
                fp.close()
        self.push("<b>Shutdown</b>. Goodbye.")
        self.push(' ')
        self.shutdown(2)
        self.close()
        raise SystemExit

    def onTrain(self, params):
        """Train on an uploaded or pasted message."""
        # Upload or paste?  Spam or ham?
        message = params.get('file') or params.get('text')
        isSpam = (params['which'] == 'Train as Spam')

        # Append the message to a file, to make it easier to rebuild
        # the database later.   This is a temporary implementation -
        # it should keep a Corpus (from Tim Stone's forthcoming message
        # management module) to manage a cache of messages.  It needs
        # to keep them for the HTML retraining interface anyway.
        message = message.replace('\r\n', '\n').replace('\r', '\n')
        if isSpam:
            f = open("_pop3proxyspam.mbox", "a")
        else:
            f = open("_pop3proxyham.mbox", "a")
        f.write("From pop3proxy@spambayes.org Sat Jan 31 00:00:00 2000\n")
        f.write(message)
        f.write("\n\n")
        f.close()

        # Train on the message.
        tokens = tokenizer.tokenize(message)
        self.bayes.learn(tokens, isSpam, True)
        self.push("<p>OK. Return <a href='/'>Home</a> or train another:</p>")
        self.push(self.pageSection % ('Train another', self.train))

    def onClassify(self, params):
        """Classify an uploaded or pasted message."""
        message = params.get('file') or params.get('text')
        tokens = tokenizer.tokenize(message)
        prob, clues = self.bayes.spamprob(tokens, evidence=True)
        self.push("<p>Spam probability: <b>%.8f</b></p>" % prob)
        self.push("<table class='sectiontable' cellspacing='0'>")
        self.push("<tr><td class='sectionheading'>Clues:</td></tr>\n")
        self.push("<tr><td class='sectionbody'><table>")
        for w, p in clues:
            self.push("<tr><td>%s</td><td>%.8f</td></tr>\n" % (w, p))
        self.push("</table></td></tr></table>")
        self.push("<p>Return <a href='/'>Home</a> or classify another:</p>")
        self.push(self.pageSection % ('Classify another', self.classify))
    def onWordquery(self, params):
        word = params['word']
        word = word.lower()
        try:
            # Must be a better way to get __dict__ for a new-style class...
            wi = self.bayes.wordinfo[word]
            members = dict(map(lambda n: (n, getattr(wi, n)), wi.__slots__))
            members['atime'] = time.asctime(time.localtime(members['atime']))
            info = """Number of spam messages: <b>%(spamcount)d</b>.<br>
                   Number of ham messages: <b>%(hamcount)d</b>.<br>
                   Number of times used to classify: <b>%(killcount)s</b>.<br>
                   Probability that a message containing this word is spam:
                   <b>%(spamprob)f</b>.<br>
                   Last used: <b>%(atime)s</b>.<br>""" % members
        except KeyError:
            info = "%r does not appear in the database." % word

        query = self.setFieldValue(self.wordQuery, 'word', params['word'])
        body = (self.pageSection % ("Statistics for %r" % word, info) +
                self.pageSection % ('Word query', query))
        self.push(body)


def initStatus():
    status.proxyPort = options.pop3proxy_port
    status.serverName = options.pop3proxy_server_name
    status.serverPort = options.pop3proxy_server_port
    status.pickleName = options.persistent_storage_file
    status.useDB = options.persistent_use_database
    status.uiPort = options.html_ui_port
    status.launchUI = options.html_ui_launch_browser
    status.gzipCache = options.pop3proxy_cache_use_gzip
    status.cacheExpiryDays = options.pop3proxy_cache_expiry_days
    status.runTestServer = False
    status.totalSessions = 0
    status.activeSessions = 0
    status.numEmails = 0
    status.numSpams = 0
    status.numHams = 0
    status.numUnsure = 0


def main(serverName, serverPort, proxyPort,
         uiPort, launchUI, pickleName, useDB):
    """Runs the proxy forever or until a 'KILL' command is received or
    someone hits Ctrl+Break."""
    print "Loading database...",
    bayes = hammie.createbayes(pickleName, useDB)
    print "Done."
    BayesProxyListener(serverName, serverPort, proxyPort, bayes)
    UserInterfaceListener(uiPort, bayes)
    if launchUI:
        webbrowser.open_new("http://localhost:%d/" % uiPort)
    asyncore.loop()



# ===================================================================
# Test code.
# ===================================================================

# One example of spam and one of ham - both are used to train, and are
# then classified.  Not a good test of the classifier, but a perfectly
# good test of the POP3 proxy.  The bodies of these came from the
# spambayes project, and I added the headers myself because the
# originals had no headers.

spam1 = """From: friend@public.com
Subject: Make money fast

Hello tim_chandler , Want to save money ?
Now is a good time to consider refinancing. Rates are low so you can cut
your current payments and save money.

http://64.251.22.101/interest/index%38%30%300%2E%68t%6D

Take off list on site [s5]
"""

good1 = """From: chris@example.com
Subject: ZPT and DTML

Jean Jordaan wrote:
> 'Fraid so ;>  It contains a vintage dtml-calendar tag.
>   http://www.zope.org/Members/teyc/CalendarTag
>
> Hmm I think I see what you mean: one needn't manually pass on the
> namespace to a ZPT?

Yeah, Page Templates are a bit more clever, sadly, DTML methods aren't :-(

Chris
"""

class TestListener(Listener):
    """Listener for TestPOP3Server.  Works on port 8110, to co-exist
    with real POP3 servers."""

    def __init__(self, socketMap=asyncore.socket_map):
        Listener.__init__(self, 8110, TestPOP3Server, socketMap=socketMap)


class TestPOP3Server(BrighterAsyncChat):
    """Minimal POP3 server, for testing purposes.  Doesn't support
    UIDL.  USER, PASS, APOP, DELE and RSET simply return "+OK"
    without doing anything.  Also understands the 'KILL' command, to
    kill it.  The mail content is the example messages above.
    """

    def __init__(self, clientSocket, socketMap=asyncore.socket_map):
        # Grumble: asynchat.__init__ doesn't take a 'map' argument,
        # hence the two-stage construction.
        BrighterAsyncChat.__init__(self)
        BrighterAsyncChat.set_socket(self, clientSocket, socketMap)
        self.maildrop = [spam1, good1]
        self.set_terminator('\r\n')
        self.okCommands = ['USER', 'PASS', 'APOP', 'NOOP',
                           'DELE', 'RSET', 'QUIT', 'KILL']
        self.handlers = {'STAT': self.onStat,
                         'LIST': self.onList,
                         'RETR': self.onRetr,
                         'TOP': self.onTop}
        self.push("+OK ready\r\n")
        self.request = ''

    def collect_incoming_data(self, data):
        """Asynchat override."""
        self.request = self.request + data

    def found_terminator(self):
        """Asynchat override."""
        if ' ' in self.request:
            command, args = self.request.split(None, 1)
        else:
            command, args = self.request, ''
        command = command.upper()
        if command in self.okCommands:
            self.push("+OK (we hope)\r\n")
            if command == 'QUIT':
                self.close_when_done()
            if command == 'KILL':
                self.shutdown(2)
                self.close()
                raise SystemExit
        else:
            handler = self.handlers.get(command, self.onUnknown)
            self.push(handler(command, args))   # Or push_slowly for testing
        self.request = ''

    def push_slowly(self, response):
        """Useful for testing."""
        for c in response:
            self.push(c)
            time.sleep(0.02)

    def onStat(self, command, args):
        """POP3 STAT command."""
        maildropSize = reduce(operator.add, map(len, self.maildrop))
        maildropSize += len(self.maildrop) * len(HEADER_EXAMPLE)
        return "+OK %d %d\r\n" % (len(self.maildrop), maildropSize)

    def onList(self, command, args):
        """POP3 LIST command, with optional message number argument."""
        if args:
            try:
                number = int(args)
            except ValueError:
                number = -1
            if 0 < number <= len(self.maildrop):
                return "+OK %d\r\n" % len(self.maildrop[number-1])
            else:
                return "-ERR no such message\r\n"
        else:
            returnLines = ["+OK"]
            for messageIndex in range(len(self.maildrop)):
                size = len(self.maildrop[messageIndex])
                returnLines.append("%d %d" % (messageIndex + 1, size))
            returnLines.append(".")
            return '\r\n'.join(returnLines) + '\r\n'

    def _getMessage(self, number, maxLines):
        """Implements the POP3 RETR and TOP commands."""
        if 0 < number <= len(self.maildrop):
            message = self.maildrop[number-1]
            headers, body = message.split('\n\n', 1)
            bodyLines = body.split('\n')[:maxLines]
            message = headers + '\r\n\r\n' + '\n'.join(bodyLines)
            return "+OK\r\n%s\r\n.\r\n" % message
        else:
            return "-ERR no such message\r\n"

    def onRetr(self, command, args):
        """POP3 RETR command."""
        try:
            number = int(args)
        except ValueError:
            number = -1
        return self._getMessage(number, 12345)

    def onTop(self, command, args):
        """POP3 RETR command."""
        try:
            number, lines = map(int, args.split())
        except ValueError:
            number, lines = -1, -1
        return self._getMessage(number, lines)

    def onUnknown(self, command, args):
        """Unknown POP3 command."""
        return "-ERR Unknown command: %s\r\n" % repr(command)


def test():
    """Runs a self-test using TestPOP3Server, a minimal POP3 server
    that serves the example emails above.
    """
    # Run a proxy and a test server in separate threads with separate
    # asyncore environments.
    import threading
    initStatus()
    testServerReady = threading.Event()
    def runTestServer():
        testSocketMap = {}
        TestListener(socketMap=testSocketMap)
        testServerReady.set()
        asyncore.loop(map=testSocketMap)

    proxyReady = threading.Event()
    def runProxy():
        # Name the database in case it ever gets auto-flushed to disk.
        bayes = hammie.createbayes('_pop3proxy.db')
        UserInterfaceListener(8881, bayes)
        BayesProxyListener('localhost', 8110, 8111, bayes)
        bayes.learn(tokenizer.tokenize(spam1), True)
        bayes.learn(tokenizer.tokenize(good1), False)
        proxyReady.set()
        asyncore.loop()

    threading.Thread(target=runTestServer).start()
    testServerReady.wait()
    threading.Thread(target=runProxy).start()
    proxyReady.wait()

    # Connect to the proxy.
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy.connect(('localhost', 8111))
    response = proxy.recv(100)
    assert response == "+OK ready\r\n"

    # Stat the mailbox to get the number of messages.
    proxy.send("stat\r\n")
    response = proxy.recv(100)
    count, totalSize = map(int, response.split()[1:3])
    assert count == 2

    # Loop through the messages ensuring that they have judgement
    # headers.
    for i in range(1, count+1):
        response = ""
        proxy.send("retr %d\r\n" % i)
        while response.find('\n.\r\n') == -1:
            response = response + proxy.recv(1000)
        assert response.find(options.hammie_header_name) >= 0

    # Smoke-test the HTML UI.
    httpServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    httpServer.connect(('localhost', 8881))
    httpServer.sendall("get / HTTP/1.0\r\n\r\n")
    response = ''
    while 1:
        packet = httpServer.recv(1000)
        if not packet: break
        response += packet
    assert re.search(r"(?s)<html>.*Spambayes proxy.*</html>", response)

    # Kill the proxy and the test server.
    proxy.sendall("kill\r\n")
    proxy.recv(100)
    pop3Server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pop3Server.connect(('localhost', 8110))
    pop3Server.sendall("kill\r\n")
    pop3Server.recv(100)


# ===================================================================
# __main__ driver.
# ===================================================================

if __name__ == '__main__':
    # Read the arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'htdbzp:l:u:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    initStatus()
    runSelfTest = False
    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-t':
            status.runTestServer = True
        elif opt == '-b':
            status.launchUI = True
        elif opt == '-d':
            status.useDB = True
        elif opt == '-p':
            status.pickleName = arg
        elif opt == '-l':
            status.proxyPort = int(arg)
        elif opt == '-u':
            status.uiPort = int(arg)
        elif opt == '-z':
            runSelfTest = True

    # Do whatever we've been asked to do...
    if runSelfTest:
        print "\nRunning self-test...\n"
        test()
        print "Self-test passed."   # ...else it would have asserted.

    elif status.runTestServer:
        print "Running a test POP3 server on port 8110..."
        TestListener()
        asyncore.loop()

    elif 0 <= len(args) <= 2:
        # Normal usage, with optional server name and port number.
        if len(args) >= 1:
            status.serverName = args[0]
        if len(args) >= 2:
            status.serverPort = int(args[1])

        if not status.serverName:
            print >>sys.stderr, \
                  ("Error: You must give a POP3 server name, either in\n"
                   "bayescustomize.ini as pop3proxy_server_name or on the\n"
                   "command line.  pop3server.py -h prints a usage message.")
        else:
            main(status.serverName, status.serverPort, status.proxyPort,
                 status.uiPort, status.launchUI, status.pickleName,
                 status.useDB)

    else:
        print >>sys.stderr, __doc__
