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
            -h      : Displays this help message.
            -d FILE : use the named DBM database file
            -D FILE : the the named Pickle database file
            -l port : proxy listens on this port number (default 110)
            -u port : User interface listens on this port number
                      (default 8880; Browse http://localhost:8880/)
            -b      : Launch a web browser showing the user interface.

        All command line arguments and switches take their default
        values from the [pop3proxy] and [html_ui] sections of
        bayescustomize.ini.

For safety, and to help debugging, the whole POP3 conversation is
written out to _pop3proxy.log for each run, if
options["globals", "verbose"] is True.

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

User interface improvements:

 o Once the pieces are on separate pages, make the paste box bigger.
 o Deployment: Windows executable?  atlaxwin and ctypes?  Or just
   webbrowser?
 o Save the stats (num classified, etc.) between sessions.
 o "Reload database" button.


New features:

 o Online manual.
 o Links to project homepage, mailing list, etc.
 o List of words with stats (it would have to be paged!) a la SpamSieve.


Code quality:

 o Cope with the email client timing out and closing the connection.


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
"""

import os, sys, re, errno, getopt, time, traceback
import socket
from thread import start_new_thread
from email.Header import Header

import spambayes.message
from spambayes import Dibbler
from spambayes import storage
from spambayes.FileCorpus import FileCorpus, ExpiryFileCorpus
from spambayes.FileCorpus import FileMessageFactory, GzipFileMessageFactory
from spambayes.Options import options
from spambayes.UserInterface import UserInterfaceServer
from spambayes.ProxyUI import ProxyUserInterface
from spambayes.Version import get_version_string

# Increase the stack size on MacOS X.  Stolen from Lib/test/regrtest.py
if sys.platform == 'darwin':
    try:
        import resource
    except ImportError:
        pass
    else:
        soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
        newsoft = min(hard, max(soft, 1024*2048))
        resource.setrlimit(resource.RLIMIT_STACK, (newsoft, hard))

# number to add to STAT length for each msg to fudge for spambayes headers
HEADER_SIZE_FUDGE_FACTOR = 512

class ServerLineReader(Dibbler.BrighterAsyncChat):
    """An async socket that reads lines from a remote server and
    simply calls a callback with the data.  The BayesProxy object
    can't connect to the real POP3 server and talk to it
    synchronously, because that would block the process."""

    lineCallback = None

    def __init__(self, serverName, serverPort, lineCallback):
        Dibbler.BrighterAsyncChat.__init__(self)
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


class POP3ProxyBase(Dibbler.BrighterAsyncChat):
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
        Dibbler.BrighterAsyncChat.__init__(self, clientSocket)
        self.request = ''
        self.response = ''
        self.set_terminator('\r\n')
        self.command = ''           # The POP3 command being processed...
        self.args = []              # ...and its arguments
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
        elif self.command in ['RETR', 'TOP', 'CAPA']:
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

    def collect_incoming_data(self, data):
        """Asynchat override."""
        self.request = self.request + data

    def found_terminator(self):
        """Asynchat override."""
        verb = self.request.strip().upper()
        if verb == 'KILL':
            self.socket.shutdown(2)
            self.close()
            raise SystemExit
        elif verb == 'CRASH':
            # For testing
            x = 0
            y = 1/x

        self.serverSocket.push(self.request + '\r\n')
        if self.request.strip() == '':
            # Someone just hit the Enter key.
            self.command = ''
            self.args = []
        else:
            # A proper command.
            splitCommand = self.request.strip().split()
            self.command = splitCommand[0].upper()
            self.args = splitCommand[1:]
            self.startTime = time.time()

        self.request = ''

    def onResponse(self):
        # We don't support pipelining, so if the command is CAPA and the
        # response includes PIPELINING, hack out that line of the response.
        if self.command == 'CAPA':
            pipelineRE = r'(?im)^PIPELINING[^\n]*\n'
            self.response = re.sub(pipelineRE, '', self.response)

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
        self.args = []
        self.isClosing = False
        self.seenAllHeaders = False


class BayesProxyListener(Dibbler.Listener):
    """Listens for incoming email client connections and spins off
    BayesProxy objects to serve them.
    """

    def __init__(self, serverName, serverPort, proxyPort):
        proxyArgs = (serverName, serverPort)
        Dibbler.Listener.__init__(self, proxyPort, BayesProxy, proxyArgs)
        print 'Listener on port %s is proxying %s:%d' % \
               (_addressPortStr(proxyPort), serverName, serverPort)


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

     o USER:
        o Does no processing based on the USER command itself, but
          expires any old messages in the three caches.
    """

    def __init__(self, clientSocket, serverName, serverPort):
        POP3ProxyBase.__init__(self, clientSocket, serverName, serverPort)
        self.handlers = {'STAT': self.onStat, 'LIST': self.onList,
                         'RETR': self.onRetr, 'TOP': self.onTop,
                         'USER': self.onUser}
        state.totalSessions += 1
        state.activeSessions += 1
        self.isClosed = False

    def send(self, data):
        """Logs the data to the log file."""
        if options["globals", "verbose"]:
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
        if options["globals", "verbose"]:
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
            size = int(match.group(2)) + HEADER_SIZE_FUDGE_FACTOR * count
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
                match = re.search(r'^(\d+)\s+(\d+)', line)
                if match:
                    number = int(match.group(1))
                    size = int(match.group(2)) + HEADER_SIZE_FUDGE_FACTOR
                    line = "%d %d" % (number, size)
                outputLines.append(line)
            return '\r\n'.join(outputLines)
        else:
            # Single line.
            match = re.search(r'^\+OK\s+(\d+)\s+(\d+)(.*)\r\n', response)
            if match:
                messageNumber = match.group(1)
                size = int(match.group(2)) + HEADER_SIZE_FUDGE_FACTOR
                trailer = match.group(3)
                return "+OK %s %s%s\r\n" % (messageNumber, size, trailer)
            else:
                return response

    def onRetr(self, command, args, response):
        """Adds the judgement header based on the raw headers and body
        of the message."""
        # Use '\n\r?\n' to detect the end of the headers in case of
        # broken emails that don't use the proper line separators.
        if re.search(r'\n\r?\n', response):
            # Remove the trailing .\r\n before passing to the email parser.
            # Thanks to Scott Schlesier for this fix.
            terminatingDotPresent = (response[-4:] == '\n.\r\n')
            if terminatingDotPresent:
                response = response[:-3]

            # Break off the first line, which will be '+OK'.
            ok, messageText = response.split('\n', 1)

            try:
                msg = spambayes.message.SBHeaderMessage()
                msg.setPayload(messageText)
                msg.setId(state.getNewMessageName())
                # Now find the spam disposition and add the header.
                (prob, clues) = state.bayes.spamprob(msg.asTokens(),\
                                 evidence=True)

                msg.addSBHeaders(prob, clues)

                # Check for "RETR" or "TOP N 99999999" - fetchmail without
                # the 'fetchall' option uses the latter to retrieve messages.
                if (command == 'RETR' or
                    (command == 'TOP' and
                     len(args) == 2 and args[1] == '99999999')):
                    cls = msg.GetClassification()
                    if cls == options["Hammie", "header_ham_string"]:
                        state.numHams += 1
                    elif cls == options["Hammie", "header_spam_string"]:
                        state.numSpams += 1
                    else:
                        state.numUnsure += 1

                    # Suppress caching of "Precedence: bulk" or
                    # "Precedence: list" ham if the options say so.
                    isSuppressedBulkHam = \
                        (cls == options["Hammie", "header_ham_string"] and
                         options["pop3proxy", "no_cache_bulk_ham"] and
                         msg.get('precedence') in ['bulk', 'list'])

                    # Cache the message.  Don't pollute the cache with test
                    # messages or suppressed bulk ham.
                    if (not state.isTest and
                        options["pop3proxy", "cache_messages"] and
                        not isSuppressedBulkHam):
                        # Write the message into the Unknown cache.
                        message = state.unknownCorpus.makeMessage(msg.getId())
                        message.setSubstance(msg.as_string())
                        state.unknownCorpus.addMessage(message)

                # We'll return the message with the headers added.  We take
                # all the headers from the SBHeaderMessage, but take the body
                # directly from the POP3 conversation, because the
                # SBHeaderMessage might have "fixed" a partial message by
                # appending a closing boundary separator.  Remember we can
                # be dealing with partial message here because of the timeout
                # code in onServerLine.
                headers = []
                for name, value in msg.items():
                    header = "%s: %s" % (name, value)
                    headers.append(re.sub(r'\r?\n', '\r\n', header))
                body = re.split(r'\n\r?\n', messageText, 1)[1]
                messageText = "\r\n".join(headers) + "\r\n\r\n" + body

            except:
                # Something nasty happened while parsing or classifying -
                # report the exception in a hand-appended header and recover.
                # This is one case where an unqualified 'except' is OK, 'cos
                # anything's better than destroying people's email...
                eType, eValue, eTraceback = sys.exc_info()
                headerName = 'X-Spambayes-Exception'
                file, line, func, code = traceback.extract_tb(eTraceback)[-1]

                # Build the header.
                details = "%s(%s) in %s() at %s line %d: %s" % \
                           (eType, eValue, func, file, line, code)
                header = Header(details, header_name=headerName,
                                         continuation_ws='\t')

                # Insert the header, converting email.Header's '\n' line
                # breaks to POP3's '\r\n'.
                headers, body = re.split(r'\n\r?\n', messageText, 1)
                header = re.sub(r'\r?\n', '\r\n', str(header))
                headers += "\n%s: %s\r\n\r\n" % (headerName, header)
                messageText = headers + body

                # Print the exception and a traceback.
                traceback.print_exc()

            # Restore the +OK and the POP3 .\r\n terminator if there was one.
            retval = ok + "\n" + messageText
            if terminatingDotPresent:
                retval += '.\r\n'
            return retval

        else:
            # Must be an error response.
            return response

    def onTop(self, command, args, response):
        """Adds the judgement header based on the raw headers and as
        much of the body as the TOP command retrieves."""
        # Easy (but see the caveat in BayesProxy.__doc__).
        return self.onRetr(command, args, response)

    def onUser(self, command, args, response):
        """Spins off three separate threads that expires any old messages
        in the three caches, but does not do any processing of the USER
        command itself."""
        start_new_thread(state.spamCorpus.removeExpiredMessages, ())
        start_new_thread(state.hamCorpus.removeExpiredMessages, ())
        start_new_thread(state.unknownCorpus.removeExpiredMessages, ())
        return response

    def onUnknown(self, command, args, response):
        """Default handler; returns the server's response verbatim."""
        return response


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
        if options["globals", "verbose"]:
            self.logFile = open('_pop3proxy.log', 'wb', 0)

        self.servers = []
        self.proxyPorts = []
        if options["pop3proxy", "servers"]:
            for server in options["pop3proxy", "servers"]:
                server = server.strip()
                if server.find(':') > -1:
                    server, port = server.split(':', 1)
                else:
                    port = '110'
                self.servers.append((server, int(port)))

        if options["pop3proxy", "ports"]:
            splitPorts = options["pop3proxy", "ports"]
            self.proxyPorts = map(_addressAndPort, splitPorts)

        if len(self.servers) != len(self.proxyPorts):
            print "pop3proxy_servers & pop3proxy_ports are different lengths!"
            sys.exit()

        # Load up the other settings from Option.py / bayescustomize.ini
        self.useDB = options["pop3proxy", "persistent_use_database"]
        self.uiPort = options["html_ui", "port"]
        self.launchUI = options["html_ui", "launch_browser"]
        self.gzipCache = options["pop3proxy", "cache_use_gzip"]
        self.cacheExpiryDays = options["pop3proxy", "cache_expiry_days"]
        self.runTestServer = False
        self.isTest = False

        # Set up the statistics.
        self.totalSessions = 0
        self.activeSessions = 0
        self.numSpams = 0
        self.numHams = 0
        self.numUnsure = 0

        # Unique names for cached messages - see `getNewMessageName()` below.
        self.lastBaseMessageName = ''
        self.uniquifier = 2

    def buildServerStrings(self):
        """After the server details have been set up, this creates string
        versions of the details, for display in the Status panel."""
        serverStrings = ["%s:%s" % (s, p) for s, p in self.servers]
        self.serversString = ', '.join(serverStrings)
        self.proxyPortsString = ', '.join(map(_addressPortStr, self.proxyPorts))

    def createWorkers(self):
        """Using the options that were initialised in __init__ and then
        possibly overridden by the driver code, create the Bayes object,
        the Corpuses, the Trainers and so on."""
        print "Loading database...",
        if self.isTest:
            self.useDB = True
            options["pop3proxy", "persistent_storage_file"] = \
                        '_pop3proxy_test.pickle'   # This is never saved.
        filename = options["pop3proxy", "persistent_storage_file"]
        filename = os.path.expanduser(filename)
        if self.useDB:
            self.bayes = storage.DBDictClassifier(filename)
        else:
            self.bayes = storage.PickledClassifier(filename)
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

            # Create/open the Corpuses.  Use small cache sizes to avoid hogging
            # lots of memory.
            map(ensureDir, [options["pop3proxy", "spam_cache"],
                            options["pop3proxy", "ham_cache"],
                            options["pop3proxy", "unknown_cache"]])
            if self.gzipCache:
                factory = GzipFileMessageFactory()
            else:
                factory = FileMessageFactory()
            age = options["pop3proxy", "cache_expiry_days"]*24*60*60
            self.spamCorpus = ExpiryFileCorpus(age, factory,
                                               options["pop3proxy",
                                                       "spam_cache"],
                                               '[0123456789\-]*',
                                               cacheSize=20)
            self.hamCorpus = ExpiryFileCorpus(age, factory,
                                              options["pop3proxy",
                                                      "ham_cache"],
                                              '[0123456789\-]*',
                                              cacheSize=20)
            self.unknownCorpus = ExpiryFileCorpus(age, factory,
                                            options["pop3proxy",
                                                    "unknown_cache"],
                                            '[0123456789\-]*',
                                                  cacheSize=20)

            # Given that (hopefully) users will get to the stage
            # where they do not need to do any more regular training to
            # be satisfied with spambayes' performance, we expire old
            # messages from not only the trained corpora, but the unknown
            # as well.
            self.spamCorpus.removeExpiredMessages()
            self.hamCorpus.removeExpiredMessages()
            self.unknownCorpus.removeExpiredMessages()

            # Create the Trainers.
            self.spamTrainer = storage.SpamTrainer(self.bayes)
            self.hamTrainer = storage.HamTrainer(self.bayes)
            self.spamCorpus.addObserver(self.spamTrainer)
            self.hamCorpus.addObserver(self.hamTrainer)

    def getNewMessageName(self):
        # The message name is the time it arrived, with a uniquifier
        # appended if two arrive within one clock tick of each other.
        messageName = "%10.10d" % long(time.time())
        if messageName == self.lastBaseMessageName:
            messageName = "%s-%d" % (messageName, self.uniquifier)
            self.uniquifier += 1
        else:
            self.lastBaseMessageName = messageName
            self.uniquifier = 2
        return messageName


# Option-parsing helper functions
def _addressAndPort(s):
    """Decode a string representing a port to bind to, with optional address."""
    s = s.strip()
    if ':' in s:
        addr, port = s.split(':')
        return addr, int(port)
    else:
        return '', int(s)

def _addressPortStr((addr, port)):
    """Encode a string representing a port to bind to, with optional address."""
    if not addr:
        return str(port)
    else:
        return '%s:%d' % (addr, port)


state = State()
proxyListeners = []
def _createProxies(servers, proxyPorts):
    """Create BayesProxyListeners for all the given servers."""
    for (server, serverPort), proxyPort in zip(servers, proxyPorts):
        listener = BayesProxyListener(server, serverPort, proxyPort)
        proxyListeners.append(listener)

def _recreateState():
    state = State()
    state.buildServerStrings()
    state.createWorkers()

    # Close the existing listeners and create new ones.  This won't
    # affect any running proxies - once a listener has created a proxy,
    # that proxy is then independent of it.
    for proxy in proxyListeners:
        proxy.close()
    del proxyListeners[:]
    _createProxies(state.servers, state.proxyPorts)
    return state

def main(servers, proxyPorts, uiPort, launchUI):
    """Runs the proxy forever or until a 'KILL' command is received or
    someone hits Ctrl+Break."""
    _createProxies(servers, proxyPorts)
    httpServer = UserInterfaceServer(uiPort)
    proxyUI = ProxyUserInterface(state, _recreateState)
    httpServer.register(proxyUI)
    Dibbler.run(launchBrowser=launchUI)


# ===================================================================
# __main__ driver.
# ===================================================================

def run():
    # Read the arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hbpsd:D:l:u:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    runSelfTest = False
    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-b':
            state.launchUI = True
        elif opt == '-d':   # dbm file
            state.useDB = True
            options["pop3proxy", "persistent_storage_file"] = arg
        elif opt == '-D':   # pickle file
            state.useDB = False
            options["pop3proxy", "persistent_storage_file"] = arg
        elif opt == '-p':   # dead option
            print >>sys.stderr, "-p option is no longer supported, use -D\n"
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-l':
            state.proxyPorts = [_addressAndPort(arg)]
        elif opt == '-u':
            state.uiPort = int(arg)

    # Let the user know what they are using...
    print get_version_string("POP3 Proxy")
    print "and engine %s.\n" % (get_version_string(),)

    # Do whatever we've been asked to do...
    state.createWorkers()

    # Launch any SMTP proxies.  This was once an option, but
    # is now always carried out - if the user hasn't specified any
    # SMTP proxy information in their configuration, then nothing
    # will happen anyway, and this is much clearer for documentation.
    from smtpproxy import LoadServerInfo, CreateProxies
    servers, proxyPorts = LoadServerInfo()
    CreateProxies(servers, proxyPorts, state)
    LoadServerInfo()

    if 0 <= len(args) <= 2:
        # Normal usage, with optional server name and port number.
        if len(args) == 1:
            state.servers = [(args[0], 110)]
        elif len(args) == 2:
            state.servers = [(args[0], int(args[1]))]

        state.buildServerStrings()
        main(state.servers, state.proxyPorts, state.uiPort, state.launchUI)

    else:
        print >>sys.stderr, __doc__

if __name__ == '__main__':
    run()
