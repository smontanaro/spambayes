#!/usr/bin/env python

"""A POP3 proxy that works with classifier.py, and adds a simple
X-Spambayes-Classification header (ham/spam/unsure) to each incoming
email.  You point pop3proxy at your POP3 server, and configure your
email client to collect mail from the proxy then filter on the added
header.  Usage:

    pop3proxy.py [options] [<server> [<server port>]]
        <server> is the name of your real POP3 server
        <port>   is the port number of your real POP3 server, which
                 defaults to 110.

        options:
            -z      : Runs a self-test and exits.
            -t      : Runs a fake POP3 server on port 8110 (for testing).
            -h      : Displays this help message.

            -p FILE : use the named database file
            -d      : the database is a DBM file rather than a pickle
            -l port : proxy listens on this port number (default 110)
            -u port : User interface listens on this port number
                      (default 8880; Browse http://localhost:8880/)
            -b      : Launch a web browser showing the user interface.

        All command line arguments and switches take their default
        values from the [pop3proxy] and [html_ui] sections of
        bayescustomize.ini.

For safety, and to help debugging, the whole POP3 conversation is
written out to _pop3proxy.log for each run, if options.verbose is True.

To make rebuilding the database easier, uploaded messages are appended
to _pop3proxyham.mbox and _pop3proxyspam.mbox.
"""

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Richie Hindle <richie@entrian.com>"
__credits__ = "Tim Peters, Neale Pickett, Tim Stone, all the Spambayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


todo = """

Web training interface:

 o Functional tests.
 o Review already-trained messages, and purge them.
 o Put in a link to view a message (plain text, html, multipart...?)
   Include a Reply link that launches the registered email client, eg.
   mailto:tim@fourstonesExpressions.com?subject=Re:%20pop3proxy&body=Hi%21%0D
 o Keyboard navigation (David Ascher).  But aren't Tab and left/right
   arrow enough?
 o [Francois Granger] Show the raw spambrob number close to the buttons
   (this would mean using the extra X-Hammie header by default).
 o Add Today and Refresh buttons on the Review page.
 o "There are no untrained messages to display.  Return Home."


User interface improvements:

 o Once the pieces are on separate pages, make the paste box bigger.
 o Deployment: Windows executable?  atlaxwin and ctypes?  Or just
   webbrowser?
 o Can it cleanly dynamically update its status display while having a
   POP3 converation?  Hammering reload sucks.
 o Save the stats (num classified, etc.) between sessions.
 o "Reload database" button.


New features:

 o "Send me an email every [...] to remind me to train on new
   messages."
 o "Send me a status email every [...] telling how many mails have been
   classified, etc."
 o Possibly integrate Tim Stone's SMTP code - make it use async, make
   the training code update (rather than replace!) the database.
 o Allow use of the UI without the POP3 proxy.
 o Remove any existing X-Spambayes-Classification header from incoming
   emails.
 o Whitelist.
 o Online manual.
 o Links to project homepage, mailing list, etc.
 o Edit settings through the web.
 o List of words with stats (it would have to be paged!) a la SpamSieve.


Code quality:

 o Move the UI into its own module.
 o Eventually, pull the common HTTP code from pop3proxy.py and Entrian
   Debugger into a library.
 o Cope with the email client timing out and closing the connection.
 o Lose the trailing dot from cached messages.


Info:

 o Slightly-wordy index page; intro paragraph for each page.
 o In both stats and training results, report nham and nspam - warn if
   they're very different (for some value of 'very').
 o "Links" section (on homepage?) to project homepage, mailing list,
   etc.


Gimmicks:

 o Classify a web page given a URL.
 o Graphs.  Of something.  Who cares what?
 o NNTP proxy.
 o Zoe...!

Notes, for the sake of somewhere better to put them:

Don't proxy spams at all?  This would mean writing a full POP3 client
and server - it would download all your mail on a timer and serve to you
all the non-spams.  It could be 'safe' in that it leaves the messages in
the real POP3 account until you collect them from it (or in the case of
spams, until you collect contemporaneous hams).  The web interface would
then present all the spams so that you could correct any FPs and mark
them for collection.  The thing is no longer a proxy (because the first
POP3 command in a conversion is STAT or LIST, which tells you how many
mails there are - it wouldn't know the answer, and finding out could
take weeks over a modem - I've already had problems with clients timing
out while the proxy was downloading stuff from the server).

Adam's idea: add checkboxes to a Google results list for "Relevant" /
"Irrelevant", then submit that to build a search including the
highest-scoring tokens and excluding the lowest-scoring ones.
"""

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

import os, sys, re, operator, errno, getopt, string, time, bisect
import socket, asyncore, asynchat, cgi, urlparse, webbrowser
import mailbox, email.Header
from spambayes import storage, tokenizer, mboxutils
from spambayes.FileCorpus import FileCorpus, ExpiryFileCorpus
from spambayes.FileCorpus import FileMessageFactory, GzipFileMessageFactory
from email.Iterators import typed_subpart_iterator
from spambayes.Options import options

# HEADER_EXAMPLE is the longest possible header - the length of this one
# is added to the size of each message.
HEADER_FORMAT = '%s: %%s\r\n' % options.hammie_header_name
HEADER_EXAMPLE = '%s: xxxxxxxxxxxxxxxxxxxx\r\n' % options.hammie_header_name


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
        if options.verbose:
            print "%s listening on port %d." % (self.__class__.__name__, port)
        self.bind(('', port))
        self.listen(5)

    def handle_accept(self):
        # If an incoming connection is instantly reset, eg. by following a
        # link in the web interface then instantly following another one or
        # hitting stop, handle_accept() will be triggered but accept() will
        # return None.
        result = self.accept()
        if result:
            clientSocket, clientAddress = result
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
        if type == socket.error and v[0] == 9:  # Why?  Who knows...
            pass
        elif type == SystemExit:
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
            error = "Can't connect to %s:%d: %s" % (serverName, serverPort, e)
            print >>sys.stderr, error
            self.lineCallback('-ERR %s\r\n' % error)
            self.lineCallback('')   # "The socket's been closed."
            self.close()

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
            return len(self.args) == 0
        else:
            # Assume that an unknown command will get a single-line
            # response.  This should work for errors and for POP-AUTH,
            # and is harmless even for multiline responses - the first
            # line will be passed to onTransaction and ignored, then the
            # rest will be proxied straight through.
            return False

    ## This is an attempt to solve the problem whereby the email client
    ## times out and closes the connection but the ServerLineReader is still
    ## connected, so you get errors from the POP3 server next time because
    ## there's already an active connection.  But after introducing this,
    ## I kept getting unexplained "Bad file descriptor" errors in recv.
    ##
    ## def handle_close(self):
    ##     """If the email client closes the connection unexpectedly, eg.
    ##     because of a timeout, close the server connection."""
    ##     self.serverSocket.shutdown(2)
    ##     self.serverSocket.close()
    ##     self.close()

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

    def __init__(self, serverName, serverPort, proxyPort):
        proxyArgs = (serverName, serverPort)
        Listener.__init__(self, proxyPort, BayesProxy, proxyArgs)
        print 'Listener on port %d is proxying %s:%d' % (proxyPort, serverName, serverPort)


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

    def __init__(self, clientSocket, serverName, serverPort):
        POP3ProxyBase.__init__(self, clientSocket, serverName, serverPort)
        self.handlers = {'STAT': self.onStat, 'LIST': self.onList,
                         'RETR': self.onRetr, 'TOP': self.onTop}
        state.totalSessions += 1
        state.activeSessions += 1
        self.isClosed = False

    def send(self, data):
        """Logs the data to the log file."""
        if options.verbose:
            state.logFile.write(data)
            state.logFile.flush()
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
        if options.verbose:
            state.logFile.write(data)
            state.logFile.flush()
        return data

    def close(self):
        # This can be called multiple times by async.
        if not self.isClosed:
            self.isClosed = True
            state.activeSessions -= 1
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
            ok, messageText = response.split('\n', 1)

            # Now find the spam disposition and add the header.
            prob = state.bayes.spamprob(tokenizer.tokenize(messageText))
            if prob < options.ham_cutoff:
                disposition = options.header_ham_string
                if command == 'RETR':
                    state.numHams += 1
            elif prob > options.spam_cutoff:
                disposition = options.header_spam_string
                if command == 'RETR':
                    state.numSpams += 1
            else:
                disposition = options.header_unsure_string
                if command == 'RETR':
                    state.numUnsure += 1

            headers, body = re.split(r'\n\r?\n', messageText, 1)
            headers = headers + "\n" + HEADER_FORMAT % disposition + "\r\n"
            messageText = headers + body

            # Cache the message; don't pollute the cache with test messages.
            if command == 'RETR' and not state.isTest:
                # The message name is the time it arrived, with a uniquifier
                # appended if two arrive within one clock tick of each other.
                messageName = "%10.10d" % long(time.time())
                if messageName == state.lastBaseMessageName:
                    state.lastBaseMessageName = messageName
                    messageName = "%s-%d" % (messageName, state.uniquifier)
                    state.uniquifier += 1
                else:
                    state.lastBaseMessageName = messageName
                    state.uniquifier = 2

                # Write the message into the Unknown cache.
                message = state.unknownCorpus.makeMessage(messageName)
                message.setSubstance(messageText)
                state.unknownCorpus.addMessage(message)

            # Return the +OK and the message with the header added.
            return ok + "\n" + messageText

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

    def __init__(self, uiPort, socketMap=asyncore.socket_map):
        Listener.__init__(self, uiPort, UserInterface, (), socketMap=socketMap)
        print 'User interface url is http://localhost:%d' % (uiPort)


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

    header = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">
             <html><head><title>Spambayes proxy: %s</title>
             <style>
             body { font: 90%% arial, swiss, helvetica; margin: 0 }
             table { font: 90%% arial, swiss, helvetica }
             form { margin: 0 }
             .banner { background: #c0e0ff; padding=5; padding-left: 15;
                       border-top: 1px solid black;
                       border-bottom: 1px solid black }
             .header { font-size: 133%% }
             .content { margin: 15 }
             .messagetable td { padding-left: 1ex; padding-right: 1ex }
             .sectiontable { border: 1px solid #808080; width: 95%% }
             .sectionheading { background: fffae0; padding-left: 1ex;
                               border-bottom: 1px solid #808080;
                               font-weight: bold }
             .sectionbody { padding: 1em }
             .reviewheaders a { color: #000000 }
             .stripe_on td { background: #f4f4f4 }
             </style>
             </head>\n"""

    bodyStart = """<body>
                <div class='banner'>
                %s
                <span class='header'>Spambayes proxy: %s</span></div>
                <div class='content'>\n"""

    footer = """</div>
             <form action='save' method='POST'>
             <table width='100%%' cellspacing='0'>
             <tr><td class='banner'>&nbsp;<a href='home'>Spambayes Proxy</a>,
             %s.
             <a href='http://www.spambayes.org/'>Spambayes.org</a></td>
             <td align='right' class='banner'>
             %s
             </td></tr></table></form>
             </body></html>\n"""

    saveButtons = """<input type='submit' name='how' value='Save'>&nbsp;&nbsp;
            <input type='submit' name='how' value='Save &amp; shutdown'>"""

    pageSection = """<table class='sectiontable' cellspacing='0'>
                  <tr><td class='sectionheading'>%s</td></tr>
                  <tr><td class='sectionbody'>%s</td></tr></table>
                  &nbsp;<br>\n"""

    summary = """POP3 proxy running on <b>%(proxyPortsString)s</b>,
              proxying to <b>%(serversString)s</b>.<br>
              Active POP3 conversations: <b>%(activeSessions)d</b>.<br>
              POP3 conversations this session: <b>%(totalSessions)d</b>.<br>
              Emails classified this session: <b>%(numSpams)d</b> spam,
                <b>%(numHams)d</b> ham, <b>%(numUnsure)d</b> unsure.<br>
              Total emails trained: Spam: <b>%(nspam)d</b>
                                     Ham: <b>%(nham)d</b><br>
              """

    wordQuery = """<form action='wordquery'>
                <input name='word' value='' type='text' size='30'>
                <input type='submit' value='Tell me about this word'>
                </form>"""

    review = """<p>The Spambayes proxy stores all the messages it sees.
             You can train the classifier based on those messages
             using the <a href='review'>Review messages</a> page."""

    reviewHeader = """<p>These are untrained emails, which you can use to
                   train the classifier.  Check the appropriate button for
                   each email, then click 'Train' below.  'Defer' leaves the
                   message here, to be trained on later.  Click one of the
                   Discard / Defer / Ham / Spam headers to check all of the
                   buttons in that section in one go.</p>
                   <form action='review' method='GET'>
                       <input type='hidden' name='prior' value='%d'>
                       <input type='hidden' name='next' value='%d'>
                       <table border='0' cellpadding='0' cellspacing='0'>
                       <tr><td><input type='submit' name='go'
                                      value='Previous day' %s>&nbsp;</td>
                           <td><input type='submit' name='go'
                                      value='Next day' %s>&nbsp;</td>
                           <td>&nbsp;&nbsp;&nbsp;&nbsp;</td>
                        </tr></table>
                   </form>
                   &nbsp;
                   <form action='review' method='POST'>
                   <table class='messagetable' cellpadding='0' cellspacing='0'>
                   """

    onReviewHeader = \
    """<script type='text/javascript'>
    function onHeader(type, switchTo)
    {
        if (document.forms && document.forms.length >= 2)
        {
            form = document.forms[1];
            for (i = 0; i < form.length; i++)
            {
                splitName = form[i].name.split(':');
                if (splitName.length == 3 && splitName[1] == type &&
                    form[i].value == switchTo.toLowerCase())
                {
                    form[i].checked = true;
                }
            }
        }
    }
    </script>
    """

    reviewSubheader = \
        """<tr><td><b>Messages classified as %s:</b></td>
          <td><b>From:</b></td>
          <td class='reviewheaders' nowrap><b>
              <a href='javascript: onHeader("%s", "Discard");'>Discard</a> /
              <a href='javascript: onHeader("%s", "Defer");'>Defer</a> /
              <a href='javascript: onHeader("%s", "Ham");'>Ham</a> /
              <a href='javascript: onHeader("%s", "Spam");'>Spam</a>
          </b></td></tr>"""

    upload = """<form action='%s' method='POST'
                enctype='multipart/form-data'>
             Either upload a message %s file:
             <input type='file' name='file' value=''><br>
             Or paste one whole message (incuding headers) here:<br>
             <textarea name='text' rows='3' cols='60'></textarea><br>
             %s
             </form>"""

    uploadSumbit = """<input type='submit' name='which' value='%s'>"""

    train = upload % ('train', "or mbox",
                      (uploadSumbit % "Train as Spam") + "&nbsp;" + \
                      (uploadSumbit % "Train as Ham"))

    classify = upload % ('classify', "", uploadSumbit % "Classify")

    def __init__(self, clientSocket, socketMap=asyncore.socket_map):
        # Grumble: asynchat.__init__ doesn't take a 'map' argument,
        # hence the two-stage construction.
        BrighterAsyncChat.__init__(self)
        BrighterAsyncChat.set_socket(self, clientSocket, socketMap)
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
            self.pushError(400, "Malformed request: '%s'" % requestLine)
            self.close_when_done()
        else:
            method = method.upper()
            _, _, path, _, query, _ = urlparse.urlparse(url)
            params = cgi.parse_qs(query, keep_blank_values=True)
            if self.get_terminator() == '\r\n\r\n' and method == 'POST':
                # We need to read a body; set a numeric async_chat terminator.
                match = re.search(r'(?i)content-length:\s*(\d+)', headers)
                contentLength = int(match.group(1))
                if contentLength > 0:
                    self.set_terminator(contentLength)
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
                    bodyFile = StringIO.StringIO(body)
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
            # XXX Why doesn't Expires work?  Must read RFC 2616 one day...
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
                isKill = (params.get('how', '').lower().find('shutdown') >= 0)
                self.pushPreamble(name, showImage=(not isKill))
                handler(params)
                timeString = time.asctime(time.localtime())
                self.push(self.footer % (timeString, self.saveButtons))

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

    def pushPreamble(self, name, showImage=True):
        self.push(self.header % name)
        if name == 'Home':
            homeLink = name
        else:
            homeLink = "<a href='home'>Home</a> &gt; %s" % name
        if showImage:
            image = "<img src='helmet.gif' align='absmiddle'>&nbsp;"
        else:
            image = ""
        self.push(self.bodyStart % (image, homeLink))

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

    def trimAndQuote(self, field, limit, quote=False):
        """Trims a string, adding an ellipsis if necessary, and
        HTML-quotes it.  Also pumps it through email.Header.decode_header,
        which understands charset sections in email headers - I suspect
        this will only work for Latin character sets, but hey, it works for
        Francois Granger's name.  8-)"""
        sections = email.Header.decode_header(field)
        field = ' '.join([text for text, _ in sections])
        if len(field) > limit:
            field = field[:limit-3] + "..."
        return cgi.escape(field, quote)

    def onHome(self, params):
        """Serve up the homepage."""
        stateDict = state.__dict__
        stateDict.update(state.bayes.__dict__)
        # so the property() isn't as cool as we thought.  -ntp
        stateDict['nham'] = state.bayes.nham
        stateDict['nspam'] = state.bayes.nspam
        body = (self.pageSection % ('Status', self.summary % stateDict)+
                self.pageSection % ('Train on proxied messages', self.review)+
                self.pageSection % ('Train on a given message', self.train)+
                self.pageSection % ('Classify a message', self.classify)+
                self.pageSection % ('Word query', self.wordQuery))
        self.push(body)

    def doSave(self):
        """Saves the database."""
        self.push("<b>Saving... ")
        self.push(' ')
        state.bayes.store()
        self.push("Done</b>.\n")

    def onSave(self, params):
        """Command handler for "Save" and "Save & shutdown"."""
        self.doSave()
        if params['how'].lower().find('shutdown') >= 0:
            self.push("<b>Shutdown</b>. Goodbye.</div></body></html>")
            self.push(' ')
            self.shutdown(2)
            self.close()
            raise SystemExit

    def onTrain(self, params):
        """Train on an uploaded or pasted message."""
        # Upload or paste?  Spam or ham?
        content = params.get('file') or params.get('text')
        isSpam = (params['which'] == 'Train as Spam')

        # Convert platform-specific line endings into unix-style.
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Single message or mbox?
        if content.startswith('From '):
            # Get a list of raw messages from the mbox content.
            class SimpleMessage:
                def __init__(self, fp):
                    self.guts = fp.read()
            contentFile = StringIO.StringIO(content)
            mbox = mailbox.PortableUnixMailbox(contentFile, SimpleMessage)
            messages = map(lambda m: m.guts, mbox)
        else:
            # Just the one message.
            messages = [content]

        # Append the message(s) to a file, to make it easier to rebuild
        # the database later.   This is a temporary implementation -
        # it should keep a Corpus of trained messages.
        if isSpam:
            f = open("_pop3proxyspam.mbox", "a")
        else:
            f = open("_pop3proxyham.mbox", "a")

        # Train on the uploaded message(s).
        self.push("<b>Training...</b>\n")
        self.push(' ')
        for message in messages:
            tokens = tokenizer.tokenize(message)
            state.bayes.learn(tokens, isSpam)
            f.write("From pop3proxy@spambayes.org Sat Jan 31 00:00:00 2000\n")
            f.write(message)
            f.write("\n\n")

        # Save the database and return a link Home and another training form.
        f.close()
        self.doSave()
        self.push("<p>OK. Return <a href='home'>Home</a> or train again:</p>")
        self.push(self.pageSection % ('Train another', self.train))

    def keyToTimestamp(self, key):
        """Given a message key (as seen in a Corpus), returns the timestamp
        for that message.  This is the time that the message was received,
        not the Date header."""
        return long(key[:10])

    def getTimeRange(self, timestamp):
        """Given a unix timestamp, returns a 3-tuple: the start timestamp
        of the given day, the end timestamp of the given day, and the
        formatted date of the given day."""
        # This probably works on Summertime-shift days; time will tell.  8-)
        this = time.localtime(timestamp)
        start = (this[0], this[1], this[2], 0, 0, 0, this[6], this[7], this[8])
        end = time.localtime(time.mktime(start) + 36*60*60)
        end = (end[0], end[1], end[2], 0, 0, 0, end[6], end[7], end[8])
        date = time.strftime("%A, %B %d, %Y", start)
        return time.mktime(start), time.mktime(end), date

    def buildReviewKeys(self, timestamp):
        """Builds an ordered list of untrained message keys, ready for output
        in the Review list.  Returns a 5-tuple: the keys, the formatted date
        for the list (eg. "Friday, November 15, 2002"), the start of the prior
        page or zero if there isn't one, likewise the start of the given page,
        and likewise the start of the next page."""
        # Fetch all the message keys and sort them into timestamp order.
        allKeys = state.unknownCorpus.keys()
        allKeys.sort()

        # The default start timestamp is derived from the most recent message,
        # or the system time if there are no messages (not that it gets used).
        if not timestamp:
            if allKeys:
                timestamp = self.keyToTimestamp(allKeys[-1])
            else:
                timestamp = time.time()
        start, end, date = self.getTimeRange(timestamp)

        # Find the subset of the keys within this range.
        startKeyIndex = bisect.bisect(allKeys, "%d" % long(start))
        endKeyIndex = bisect.bisect(allKeys, "%d" % long(end))
        keys = allKeys[startKeyIndex:endKeyIndex]
        keys.reverse()

        # What timestamps to use for the prior and next days?  If there any
        # messages before/after this day's range, use the timestamps of those
        # messages - this will skip empty days.
        prior = end = 0
        if startKeyIndex != 0:
            prior = self.keyToTimestamp(allKeys[startKeyIndex-1])
        if endKeyIndex != len(allKeys):
            end = self.keyToTimestamp(allKeys[endKeyIndex])

        # Return the keys and their date.
        return keys, date, prior, start, end

    def appendMessages(self, lines, keyedMessages, label):
        """Appends the lines of a table of messages to 'lines'."""
        buttons = \
          """<input type='radio' name='classify:%s:%s' value='discard'>&nbsp;
             <input type='radio' name='classify:%s:%s' value='defer' %s>&nbsp;
             <input type='radio' name='classify:%s:%s' value='ham' %s>&nbsp;
             <input type='radio' name='classify:%s:%s' value='spam' %s>"""
        stripe = 0
        for key, message in keyedMessages:
            # Parse the message and get the relevant headers and the first
            # part of the body if we can.
            subject = self.trimAndQuote(message["Subject"] or "(none)", 50)
            from_ = self.trimAndQuote(message["From"] or "(none)", 40)
            try:
                part = typed_subpart_iterator(message, 'text', 'plain').next()
                text = part.get_payload()
            except StopIteration:
                try:
                    part = typed_subpart_iterator(message, 'text', 'html').next()
                    text = part.get_payload()
                    text, _ = tokenizer.crack_html_style(text)
                    text, _ = tokenizer.crack_html_comment(text)
                    text = tokenizer.html_re.sub(' ', text)
                    text = '(this message only has an HTML body)\n' + text
                except StopIteration:
                    text = '(this message has no text body)'
            text = text.replace('&nbsp;', ' ')      # Else they'll be quoted
            text = re.sub(r'(\s)\s+', r'\1', text)  # Eg. multiple blank lines
            text = self.trimAndQuote(text.strip(), 200, True)

            # Output the table row for this message.
            defer = ham = spam = ""
            if label == 'Spam':
                spam='checked'
            elif label == 'Ham':
                ham='checked'
            elif label == 'Unsure':
                defer='checked'
            subject = "<span title=\"%s\">%s</span>" % (text, subject)
            radioGroup = buttons % (label, key,
                                    label, key, defer,
                                    label, key, ham,
                                    label, key, spam)
            stripeClass = ['stripe_on', 'stripe_off'][stripe]
            lines.append("""<tr class='%s'><td>%s</td><td>%s</td>
                            <td align='center'>%s</td></tr>""" % \
                            (stripeClass, subject, from_, radioGroup))
            stripe = stripe ^ 1

    def onReview(self, params):
        """Present a list of message for (re)training."""
        # Train/discard sumbitted messages.
        id = ''
        numTrained = 0
        numDeferred = 0
        for key, value in params.items():
            if key.startswith('classify:'):
                id = key.split(':')[2]
                if value == 'spam':
                    targetCorpus = state.spamCorpus
                elif value == 'ham':
                    targetCorpus = state.hamCorpus
                elif value == 'discard':
                    targetCorpus = None
                    try:
                        state.unknownCorpus.removeMessage(state.unknownCorpus[id])
                    except KeyError:
                        pass  # Must be a reload.
                else: # defer
                    targetCorpus = None
                    numDeferred += 1
                if targetCorpus:
                    try:
                        targetCorpus.takeMessage(id, state.unknownCorpus)
                        if numTrained == 0:
                            self.push("<p><b>Training... ")
                            self.push(" ")
                        numTrained += 1
                    except KeyError:
                        pass  # Must be a reload.

        # Report on any training, and save the database if there was any.
        if numTrained > 0:
            plural = ''
            if numTrained != 1:
                plural = 's'
            self.push("Trained on %d message%s. " % (numTrained, plural))
            self.doSave()
            self.push("<br>&nbsp;")

        # If any messages were deferred, show the same page again.
        if numDeferred > 0:
            start = self.keyToTimestamp(id)

        # Else after submitting a whole page, display the prior page or the
        # next one.  Derive the day of the submitted page from the ID of the
        # last processed message.
        elif id:
            start = self.keyToTimestamp(id)
            _, _, prior, _, next = self.buildReviewKeys(start)
            if prior:
                start = prior
            else:
                start = next

        # Else if they've hit Previous or Next, display that page.
        elif params.get('go') == 'Next day':
            start = self.keyToTimestamp(params['next'])
        elif params.get('go') == 'Previous day':
            start = self.keyToTimestamp(params['prior'])

        # Else show the most recent day's page, as decided by buildReviewKeys.
        else:
            start = 0

        # Build the lists of messages: spams, hams and unsure.
        keys, date, prior, this, next = self.buildReviewKeys(start)
        keyedMessages = {options.header_spam_string: [],
                         options.header_ham_string: [],
                         options.header_unsure_string: []}
        for key in keys:
            # Parse the message and get the judgement header.
            cachedMessage = state.unknownCorpus[key]
            message = mboxutils.get_message(cachedMessage.getSubstance())
            judgement = message[options.hammie_header_name] or \
                                            options.header_unsure_string
            keyedMessages[judgement].append((key, message))

        # Present the list of messages in their groups in reverse order of
        # appearance.
        if keys:
            priorState = nextState = ""
            if not prior:
                priorState = 'disabled'
            if not next:
                nextState = 'disabled'
            lines = [self.onReviewHeader,
                     self.reviewHeader % (prior, next, priorState, nextState)]
            for header, label in ((options.header_spam_string, 'Spam'),
                                  (options.header_ham_string, 'Ham'),
                                  (options.header_unsure_string, 'Unsure')):
                if keyedMessages[header]:
                    lines.append("<tr><td>&nbsp;</td><td></td><td></td></tr>")
                    lines.append(self.reviewSubheader %
                                 (label, label, label, label, label))
                    self.appendMessages(lines, keyedMessages[header], label)

            lines.append("""<tr><td></td><td></td><td align='center'>&nbsp;<br>
                            <input type='submit' value='Train'></td></tr>""")
            lines.append("</table></form>")
            content = "\n".join(lines)
            title = "Untrained messages received on %s" % date
        else:
            content = "<p>There are no untrained messages to display.</p>"
            title = "No untrained messages"

        self.push(self.pageSection % (title, content))

    def onClassify(self, params):
        """Classify an uploaded or pasted message."""
        message = params.get('file') or params.get('text')
        message = message.replace('\r\n', '\n').replace('\r', '\n') # For Macs
        tokens = tokenizer.tokenize(message)
        prob, clues = state.bayes.spamprob(tokens, evidence=True)
        self.push("<p>Spam probability: <b>%.8f</b></p>" % prob)
        self.push("<table class='sectiontable' cellspacing='0'>")
        self.push("<tr><td class='sectionheading'>Clues:</td></tr>\n")
        self.push("<tr><td class='sectionbody'><table>")
        for w, p in clues:
            self.push("<tr><td>%s</td><td>%.8f</td></tr>\n" % (w, p))
        self.push("</table></td></tr></table>")
        self.push("<p>Return <a href='home'>Home</a> or classify another:</p>")
        self.push(self.pageSection % ('Classify another', self.classify))

    def onWordquery(self, params):
        word = params['word']
        word = word.lower()
        wi = state.bayes._wordinfoget(word)
        if wi:
            members = wi.__dict__
            members['spamprob'] = state.bayes.probability(wi)
            info = """Number of spam messages: <b>%(spamcount)d</b>.<br>
                   Number of ham messages: <b>%(hamcount)d</b>.<br>
                   Probability that a message containing this word is spam:
                   <b>%(spamprob)f</b>.<br>""" % members
        else:
            info = "%r does not appear in the database." % word

        query = self.setFieldValue(self.wordQuery, 'word', params['word'])
        body = (self.pageSection % ("Statistics for %r" % word, info) +
                self.pageSection % ('Word query', query))
        self.push(body)


# This keeps the global state of the module - the command-line options,
# statistics like how many mails have been classified, the handle of the
# log file, the Classifier and FileCorpus objects, and so on.
class State:
    def __init__(self):
        """Initialises the State object that holds the state of the app.
        The default settings are read from Options.py and bayescustomize.ini
        and are then overridden by the command-line processing code in the
        __main__ code below."""
        # Open the log file.
        if options.verbose:
            self.logFile = open('_pop3proxy.log', 'wb', 0)

        # Load up the old proxy settings from Options.py / bayescustomize.ini
        # and give warnings if they're present.   XXX Remove these soon.
        if options.pop3proxy_port != 110 or \
           options.pop3proxy_server_name != '' or \
           options.pop3proxy_server_port != 110:
            print "\n    pop3proxy_port, pop3proxy_server_name and"
            print "    pop3proxy_server_port are deprecated!  Please use"
            print "    pop3proxy_servers and pop3proxy_ports instead.\n"
        self.servers = [(options.pop3proxy_server_name,
                         options.pop3proxy_server_port)]
        self.proxyPorts = [options.pop3proxy_port]

        # Load the new proxy settings - these will override the old ones
        # if both are present.
        if options.pop3proxy_servers:
            self.servers = []
            for server in options.pop3proxy_servers.split(','):
                server = server.strip()
                if server.find(':') > -1:
                    server, port = server.split(':', 1)
                else:
                    port = '110'
                self.servers.append((server, int(port)))

        if options.pop3proxy_ports:
            splitPorts = options.pop3proxy_ports.split(',')
            self.proxyPorts = map(int, map(string.strip, splitPorts))

        if len(self.servers) != len(self.proxyPorts):
            print "pop3proxy_servers & pop3proxy_ports are different lengths!"
            sys.exit()

        # Load up the other settings from Option.py / bayescustomize.ini
        self.databaseFilename = options.pop3proxy_persistent_storage_file
        self.useDB = options.pop3proxy_persistent_use_database
        self.uiPort = options.html_ui_port
        self.launchUI = options.html_ui_launch_browser
        self.gzipCache = options.pop3proxy_cache_use_gzip
        self.cacheExpiryDays = options.pop3proxy_cache_expiry_days
        self.spamCache = options.pop3proxy_spam_cache
        self.hamCache = options.pop3proxy_ham_cache
        self.unknownCache = options.pop3proxy_unknown_cache
        self.runTestServer = False
        self.isTest = False

        # Set up the statistics.
        self.totalSessions = 0
        self.activeSessions = 0
        self.numSpams = 0
        self.numHams = 0
        self.numUnsure = 0

        # Unique names for cached messages - see BayesProxy.onRetr
        self.lastBaseMessageName = ''
        self.uniquifier = 2

    def buildServerStrings(self):
        """After the server details have been set up, this creates string
        versions of the details, for display in the Status panel."""
        serverStrings = ["%s:%s" % (s, p) for s, p in self.servers]
        self.serversString = ', '.join(serverStrings)
        self.proxyPortsString = ', '.join(map(str, self.proxyPorts))

    def createWorkers(self):
        """Using the options that were initialised in __init__ and then
        possibly overridden by the driver code, create the Bayes object,
        the Corpuses, the Trainers and so on."""
        print "Loading database...",
        if self.isTest:
            self.useDB = True
            self.databaseFilename = '_pop3proxy_test.pickle'   # Never saved
        if self.useDB:
            self.bayes = storage.DBDictClassifier(self.databaseFilename)
        else:
            self.bayes = storage.PickledClassifier(self.databaseFilename)
        print "Done."

        # Don't set up the caches and training objects when running the self-test,
        # so as not to clutter the filesystem.
        if not self.isTest:
            def ensureDir(dirname):
                try:
                    os.mkdir(dirname)
                except OSError, e:
                    if e.errno != errno.EEXIST:
                        raise

            # Create/open the Corpuses.
            map(ensureDir, [self.spamCache, self.hamCache, self.unknownCache])
            if self.gzipCache:
                factory = GzipFileMessageFactory()
            else:
                factory = FileMessageFactory()
            age = options.pop3proxy_cache_expiry_days*24*60*60
            self.spamCorpus = ExpiryFileCorpus(age, factory, self.spamCache)
            self.hamCorpus = ExpiryFileCorpus(age, factory, self.hamCache)
            self.unknownCorpus = FileCorpus(factory, self.unknownCache)

            # Expire old messages from the trained corpuses.
            self.spamCorpus.removeExpiredMessages()
            self.hamCorpus.removeExpiredMessages()

            # Create the Trainers.
            self.spamTrainer = storage.SpamTrainer(self.bayes)
            self.hamTrainer = storage.HamTrainer(self.bayes)
            self.spamCorpus.addObserver(self.spamTrainer)
            self.hamCorpus.addObserver(self.hamTrainer)

state = State()


def main(servers, proxyPorts, uiPort, launchUI):
    """Runs the proxy forever or until a 'KILL' command is received or
    someone hits Ctrl+Break."""
    for (server, serverPort), proxyPort in zip(servers, proxyPorts):
        BayesProxyListener(server, serverPort, proxyPort)
    UserInterfaceListener(uiPort)
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
    state.isTest = True
    testServerReady = threading.Event()
    def runTestServer():
        testSocketMap = {}
        TestListener(socketMap=testSocketMap)
        testServerReady.set()
        asyncore.loop(map=testSocketMap)

    proxyReady = threading.Event()
    def runProxy():
        # Name the database in case it ever gets auto-flushed to disk.
        UserInterfaceListener(8881)
        BayesProxyListener('localhost', 8110, 8111)
        state.bayes.learn(tokenizer.tokenize(spam1), True)
        state.bayes.learn(tokenizer.tokenize(good1), False)
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

def run():
    # Read the arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'htdbzp:l:u:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    runSelfTest = False
    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-t':
            state.isTest = True
            state.runTestServer = True
        elif opt == '-b':
            state.launchUI = True
        elif opt == '-d':
            state.useDB = True
        elif opt == '-p':
            state.databaseFilename = arg
        elif opt == '-l':
            state.proxyPorts = [int(arg)]
        elif opt == '-u':
            state.uiPort = int(arg)
        elif opt == '-z':
            state.isTest = True
            runSelfTest = True

    # Do whatever we've been asked to do...
    state.createWorkers()
    if runSelfTest:
        print "\nRunning self-test...\n"
        state.buildServerStrings()
        test()
        print "Self-test passed."   # ...else it would have asserted.

    elif state.runTestServer:
        print "Running a test POP3 server on port 8110..."
        TestListener()
        asyncore.loop()

    elif 0 <= len(args) <= 2:
        # Normal usage, with optional server name and port number.
        if len(args) == 1:
            state.servers = [(args[0], 110)]
        elif len(args) == 2:
            state.servers = [(args[0], int(args[1]))]

        if not state.servers or not state.servers[0][0]:
            print >>sys.stderr, \
                  ("Error: You must give a POP3 server name, either in\n"
                   "bayescustomize.ini as pop3proxy_servers or on the\n"
                   "command line.  pop3server.py -h prints a usage message.")
        else:
            state.buildServerStrings()
            main(state.servers, state.proxyPorts, state.uiPort, state.launchUI)

    else:
        print >>sys.stderr, __doc__

if __name__ == '__main__':
    run()
