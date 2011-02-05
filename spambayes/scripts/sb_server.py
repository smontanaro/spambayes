#!/usr/bin/env python

"""The primary server for SpamBayes.

Currently serves the web interface, and any configured POP3 and SMTP
proxies.

The POP3 proxy works with classifier.py, and adds a simple
X-Spambayes-Classification header (ham/spam/unsure) to each incoming
email.  You point the proxy at your POP3 server, and configure your
email client to collect mail from the proxy then filter on the added
header.  Usage:

    sb_server.py [options] [<server> [<server port>]]
        <server> is the name of your real POP3 server
        <port>   is the port number of your real POP3 server, which
                 defaults to 110.

        options:
            -h      : Displays this help message.
            -d FILE : use the named DBM database file
            -p FILE : the the named Pickle database file
            -l port : proxy listens on this port number (default 110)
            -u port : User interface listens on this port number
                      (default 8880; Browse http://localhost:8880/)
            -b      : Launch a web browser showing the user interface.

            -o section:option:value :
                      set [section, option] in the options database
                      to value

        All command line arguments and switches take their default
        values from the [pop3proxy] and [html_ui] sections of
        bayescustomize.ini.

For safety, and to help debugging, the whole POP3 conversation is
written out to _pop3proxy.log for each run, if
options["globals", "verbose"] is True.

To make rebuilding the database easier, uploaded messages are appended
to _pop3proxyham.mbox and _pop3proxyspam.mbox.
"""

# This module is part of the spambayes project, which is Copyright 2002-2007
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Richie Hindle <richie@entrian.com>"
__credits__ = "Tim Peters, Neale Pickett, Tim Stone, all the Spambayes folk."

todo = """

Web training interface:

User interface improvements:

 o Once the pieces are on separate pages, make the paste box bigger.
 o Deployment: Windows executable?  atlaxwin and ctypes?  Or just
   webbrowser?
 o "Reload database" button.


New features:

 o Online manual.
 o Links to project homepage, mailing list, etc.
 o List of words with stats (it would have to be paged!) a la SpamSieve.


Code quality:

 o Cope with the email client timing out and closing the connection.


Info:

 o Slightly-wordy index page; intro paragraph for each page.
 o In both stats and training results, report nham and nspam.
 o "Links" section (on homepage?) to project homepage, mailing list,
   etc.


Gimmicks:

 o Classify a web page given a URL.
 o Graphs.  Of something.  Who cares what?
 o NNTP proxy.
"""

import sys, re, getopt, time, socket, email
from thread import start_new_thread

import spambayes.message
from spambayes import i18n
from spambayes import Stats
from spambayes import Dibbler
from spambayes import storage
from spambayes.FileCorpus import ExpiryFileCorpus
from spambayes.FileCorpus import FileMessageFactory, GzipFileMessageFactory
from spambayes.Options import options, get_pathname_option, _
from spambayes.UserInterface import UserInterfaceServer
from spambayes.ProxyUI import ProxyUserInterface
from spambayes.Version import get_current_version


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

# exception may be raised if we are already running and check such things.
class AlreadyRunningException(Exception):
    pass

# number to add to STAT length for each msg to fudge for spambayes headers
HEADER_SIZE_FUDGE_FACTOR = 512

class ServerLineReader(Dibbler.BrighterAsyncChat):
    """An async socket that reads lines from a remote server and
    simply calls a callback with the data.  The BayesProxy object
    can't connect to the real POP3 server and talk to it
    synchronously, because that would block the process."""

    def __init__(self, serverName, serverPort, lineCallback, ssl=False,
                 map=None):
        Dibbler.BrighterAsyncChat.__init__(self, map=map)
        self.lineCallback = lineCallback
        self.handled_exception = False
        self.request = ''
        self.set_terminator('\r\n')
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        # create_socket creates a non-blocking socket.  This is not great,
        # because then socket.connect() will return errno 10035, because
        # connect takes time.  We then don't know if the connect call
        # succeeded or not.  With Python 2.4, this means that we will move
        # into asyncore.loop(), and if the connect does fail, have a
        # loop something like 'while True: log(error)', which fills up
        # stdout very fast.  Non-blocking is also a problem for ssl sockets.
        self.socket.setblocking(1)
        try:
            self.connect((serverName, serverPort))
        except socket.error, e:
            error = "Can't connect to %s:%d: %s" % (serverName, serverPort, e)
            # Some people have their system setup to check mail very
            # frequently, but without being clever enough to check whether
            # the network is available.  If we continually print the
            # "can't connect" error, we use up lots of CPU and disk space.
            # To avoid this, if not verbose only print each distinct error
            # once per hour.
            # See also: [ 1113863 ] sb_tray eats all cpu time
            now = time.time()
            then = time.time() - 3600
            if error not in state.reported_errors or \
               options["globals", "verbose"] or \
               state.reported_errors[error] < then:
                print >>sys.stderr, error

                # Record this error in the list of ones we have seen this
                # session.
                state.reported_errors[error] = now

            self.lineCallback('-ERR %s\r\n' % error)
            self.lineCallback('')   # "The socket's been closed."
            self.close()
        else:
            if ssl:
                try:
                    self.ssl_socket = socket.ssl(self.socket)
                except socket.sslerror, why:
                    if why[0] == 1: # error:140770FC:SSL routines:SSL23_GET_SERVER_HELLO:unknown protocol'
                        # Probably not SSL after all.
                        print >> sys.stderr, "Can't use SSL"
                    else:
                        raise
                else:
                    self.send = self.send_ssl
                    self.recv = self.recv_ssl
            self.socket.setblocking(0)
            
    def send_ssl(self, data):
        return self.ssl_socket.write(data)

    def handle_expt(self):
        # Python 2.4's system of continuously pumping error messages
        # is stupid.  Print an error once, and then ignore.
        if not self.handled_exception:
            print >> sys.stderr, "Unhandled exception in ServerLineReader"
            self.handled_exception = True

    def recv_ssl(self, buffer_size):
        try:
            data = self.ssl_socket.read(buffer_size)
            if not data:
                # a closed connection is indicated by signaling
                # a read condition, and having recv() return 0.
                self.handle_close()
                return ''
            else:
                return data
        except socket.sslerror, why:
            if why[0] == 6: # 'TLS/SSL connection has been closed'
                self.handle_close()
                return ''
            elif why[0] == 2: # 'The operation did not complete (read)'
                return ''
            else:
                raise

    def collect_incoming_data(self, data):
        self.request = self.request + data

    def found_terminator(self):
        self.lineCallback(self.request + '\r\n')
        self.request = ''

    def handle_close(self):
        self.lineCallback('')
        self.close()
        try:
            del self.ssl_socket
        except AttributeError:
            pass


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

    def __init__(self, clientSocket, serverName, serverPort,
                 ssl=False, map=Dibbler._defaultContext._map):
        Dibbler.BrighterAsyncChat.__init__(self, clientSocket)
        self.request = ''
        self.response = ''
        self.set_terminator('\r\n')
        self.command = ''           # The POP3 command being processed...
        self.args = []              # ...and its arguments
        self.isClosing = False      # Has the server closed the socket?
        self.seenAllHeaders = False # For the current RETR or TOP
        self.startTime = 0          # (ditto)

        if not self.onIncomingConnection(clientSocket):
            # We must refuse this connection, so pass an error back
            # to the mail client.
            self.push("-ERR Connection not allowed\r\n")
            self.close_when_done()
            return

        self.serverSocket = ServerLineReader(serverName, serverPort,
                                             self.onServerLine, ssl, map)

    def onIncomingConnection(self, clientSocket):
        """Checks the security settings."""
        # Stolen from UserInterface.py

        remoteIP = clientSocket.getpeername()[0]
        trustedIPs = options["pop3proxy", "allow_remote_connections"]

        if trustedIPs == "*" or remoteIP == clientSocket.getsockname()[0]:
            return True

        trustedIPs = trustedIPs.replace('.', '\.').replace('*', '([01]?\d\d?|2[0-4]\d|25[0-5])')
        for trusted in trustedIPs.split(','):
            if re.search("^" + trusted + "$", remoteIP):
                return True

        return False

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

        # Time out after some seconds (30 by default) for message-retrieval
        # commands if all the headers are down.  The rest of the message
        # will proxy straight through.
        # See also [ 870524 ] Make the message-proxy timeout configurable
        if self.command in ['TOP', 'RETR'] and \
           self.seenAllHeaders and time.time() > \
           self.startTime + options["pop3proxy", "retrieval_timeout"]:
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
            raise ZeroDivisionError

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
        # There are some features, tested by clients using CAPA,
        # that we don't support.  We strip them from the CAPA
        # response here, so that the client won't use them.
        for unsupported in ['PIPELINING', 'STLS', ]:
            unsupportedLine = r'(?im)^%s[^\n]*\n' % (unsupported,)
            self.response = re.sub(unsupportedLine, '', self.response)

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

    def __init__(self, serverName, serverPort, proxyPort, ssl=False):
        proxyArgs = (serverName, serverPort, ssl)
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

    def __init__(self, clientSocket, serverName, serverPort, ssl=False):
        POP3ProxyBase.__init__(self, clientSocket, serverName, serverPort,
                               ssl)
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
        # Previously, we used '\n\r?\n' to detect the end of the headers in
        # case of broken emails that don't use the proper line separators,
        # and if we couldn't find it, then we assumed that the response was
        # and error response and passed it unfiltered.  However, if the
        # message doesn't contain the separator (malformed mail), then this
        # would mean the message was passed straight through the proxy.
        # Since all the content is then in the headers, this probably
        # doesn't do a spammer much good, but, just in case, we now just
        # check for "+OK" and assume no error response will be given if
        # that is (which seems reasonable).
        # Remove the trailing .\r\n before passing to the email parser.
        # Thanks to Scott Schlesier for this fix.
        terminatingDotPresent = (response[-4:] == '\n.\r\n')
        if terminatingDotPresent:
            response = response[:-3]

        # Break off the first line, which will be '+OK'.
        statusLine, messageText = response.split('\n', 1)
        statusData = statusLine.split()
        ok = statusData[0]
        if ok.strip().upper() != "+OK":
            # Must be an error response.  Return unproxied.
            return response

        try:
            msg = email.message_from_string(messageText,
                      _class=spambayes.message.SBHeaderMessage)
            msg.setId(state.getNewMessageName())
            # Now find the spam disposition and add the header.
            (prob, clues) = state.bayes.spamprob(msg.tokenize(),
                                                 evidence=True)

            msg.addSBHeaders(prob, clues)

            # Check for "RETR" or "TOP N 99999999" - fetchmail without
            # the 'fetchall' option uses the latter to retrieve messages.
            if (command == 'RETR' or
                (command == 'TOP' and
                 len(args) == 2 and args[1] == '99999999')):
                cls = msg.GetClassification()
                state.RecordClassification(cls, prob)

                # Suppress caching of "Precedence: bulk" or
                # "Precedence: list" ham if the options say so.
                isSuppressedBulkHam = \
                    (cls == options["Headers", "header_ham_string"] and
                     options["Storage", "no_cache_bulk_ham"] and
                     msg.get('precedence') in ['bulk', 'list'])

                # Suppress large messages if the options say so.
                size_limit = options["Storage",
                                     "no_cache_large_messages"]
                isTooBig = size_limit > 0 and \
                           len(messageText) > size_limit

                # Cache the message.  Don't pollute the cache with test
                # messages or suppressed bulk ham.
                if (not state.isTest and
                    options["Storage", "cache_messages"] and
                    not isSuppressedBulkHam and not isTooBig):
                    # Write the message into the Unknown cache.
                    makeMessage = state.unknownCorpus.makeMessage
                    message = makeMessage(msg.getId(), msg.as_string())
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
            try:
                body = re.split(r'\n\r?\n', messageText, 1)[1]
            except IndexError:
                # No separator, so no body.  Bad message, but proxy it
                # through anyway (adding the missing separator).
                messageText = "\r\n".join(headers) + "\r\n\r\n"
            else:
                messageText = "\r\n".join(headers) + "\r\n\r\n" + body
        except:
            # Something nasty happened while parsing or classifying -
            # report the exception in a hand-appended header and recover.
            # This is one case where an unqualified 'except' is OK, 'cos
            # anything's better than destroying people's email...
            messageText, details = spambayes.message.\
                                   insert_exception_header(messageText)

            # Print the exception and a traceback.
            print >> sys.stderr, details

        # Restore the +OK and the POP3 .\r\n terminator if there was one.
        retval = ok + "\n" + messageText
        if terminatingDotPresent:
            retval += '.\r\n'
        return retval

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

# Implementations of a mutex or other resource which can prevent
# multiple servers starting at once.  Platform specific as no reasonable
# cross-platform solution exists (however, an old trick is to use a
# directory for a mutex, as a "create/test" atomic API generally exists).
# Will return a handle to be later closed, or may throw AlreadyRunningException
def open_platform_mutex(mutex_name="SpamBayesServer"):
    if sys.platform.startswith("win"):
        try:
            import win32event, win32api, winerror, win32con
            import pywintypes, ntsecuritycon
            # ideally, the mutex name could include either the username,
            # or the munged path to the INI file - this would mean we
            # would allow multiple starts so long as they weren't for
            # the same user.  However, as of now, the service version
            # is likely to start as a different user, so a single mutex
            # is best for now.
            # XXX - even if we do get clever with another mutex name, we
            # should consider still creating a non-exclusive
            # "SpamBayesServer" mutex, if for no better reason than so
            # an installer can check if we are running
            try:
                hmutex = win32event.CreateMutex(None, True, mutex_name)
            except win32event.error, details:
                # If another user has the mutex open, we get an "access denied"
                # error - this is still telling us what we need to know.
                if details[0] != winerror.ERROR_ACCESS_DENIED:
                    raise
                raise AlreadyRunningException
            # mutex opened - now check if we actually created it.
            if win32api.GetLastError()==winerror.ERROR_ALREADY_EXISTS:
                win32api.CloseHandle(hmutex)
                raise AlreadyRunningException
            return hmutex
        except ImportError:
            # no win32all - no worries, just start
            pass
    return None

def close_platform_mutex(mutex):
    if sys.platform.startswith("win"):
        if mutex is not None:
            mutex.Close()

# This keeps the global state of the module - the command-line options,
# statistics like how many mails have been classified, the handle of the
# log file, the Classifier and FileCorpus objects, and so on.
class State:
    def __init__(self):
        """Initialises the State object that holds the state of the app.
        The default settings are read from Options.py and bayescustomize.ini
        and are then overridden by the command-line processing code in the
        __main__ code below."""
        self.logFile = None
        self.bayes = None
        self.platform_mutex = None
        self.prepared = False
        self.can_stop = True
        self.init()

        # Load up the other settings from Option.py / bayescustomize.ini
        self.uiPort = options["html_ui", "port"]
        self.launchUI = options["html_ui", "launch_browser"]
        self.gzipCache = options["Storage", "cache_use_gzip"]
        self.cacheExpiryDays = options["Storage", "cache_expiry_days"]
        self.runTestServer = False
        self.isTest = False

    def init(self):
        assert not self.prepared, "init after prepare, but before close"
        # Load the environment for translation.
        self.lang_manager = i18n.LanguageManager()
        # Set the system user default language.
        self.lang_manager.set_language(\
            self.lang_manager.locale_default_lang())
        # Set interface to use the user language in the configuration file.
        for language in reversed(options["globals", "language"]):
            # We leave the default in there as the last option, to fall
            # back on if necessary.
            self.lang_manager.add_language(language)
        if options["globals", "verbose"]:
            print "Asked to add languages: " + \
                  ", ".join(options["globals", "language"])
            print "Set language to " + \
                  str(self.lang_manager.current_langs_codes)

        # Open the log file.
        if options["globals", "verbose"]:
            self.logFile = open('_pop3proxy.log', 'wb', 0)

        if not hasattr(self, "servers"):
            # Could have already been set via the command line.
            self.servers = []
            if options["pop3proxy", "remote_servers"]:
                for server in options["pop3proxy", "remote_servers"]:
                    server = server.strip()
                    if server.find(':') > -1:
                        server, port = server.split(':', 1)
                    else:
                        port = '110'
                    self.servers.append((server, int(port)))

        if not hasattr(self, "proxyPorts"):
            # Could have already been set via the command line.
            self.proxyPorts = []
            if options["pop3proxy", "listen_ports"]:
                splitPorts = options["pop3proxy", "listen_ports"]
                self.proxyPorts = map(_addressAndPort, splitPorts)

        if len(self.servers) != len(self.proxyPorts):
            print "pop3proxy_servers & pop3proxy_ports are different lengths!"
            sys.exit()

        # Remember reported errors.
        self.reported_errors = {}

        # Set up the statistics.
        self.totalSessions = 0
        self.activeSessions = 0
        self.numSpams = 0
        self.numHams = 0
        self.numUnsure = 0

        # Unique names for cached messages - see `getNewMessageName()` below.
        self.lastBaseMessageName = ''
        self.uniquifier = 2

    def close(self):
        assert self.prepared, "closed without being prepared!"
        self.servers = None
        if self.bayes is not None:
            # Only store a non-empty db.
            if self.bayes.nham != 0 and self.bayes.nspam != 0:
                state.bayes.store()
            self.bayes.close()
            self.bayes = None
        if self.mdb is not None:
            self.mdb.store()
            self.mdb.close()
            self.mdb = None
            spambayes.message.Message().message_info_db = None

        self.spamCorpus = self.hamCorpus = self.unknownCorpus = None
        self.spamTrainer = self.hamTrainer = None

        self.prepared = False
        close_platform_mutex(self.platform_mutex)
        self.platform_mutex = None

    def prepare(self, can_stop=True):
        """Do whatever needs to be done to prepare for running.  If
        can_stop is False, then we may not let the user shut down the
        proxy - for example, running as a Windows service this should
        be the case."""
        # If we can, prevent multiple servers from running at the same time.
        assert self.platform_mutex is None, "Should not already have the mutex"
        self.platform_mutex = open_platform_mutex()

        self.can_stop = can_stop

        # Do whatever we've been asked to do...
        self.createWorkers()
        self.prepared = True

    def buildServerStrings(self):
        """After the server details have been set up, this creates string
        versions of the details, for display in the Status panel."""
        serverStrings = ["%s:%s" % (s, p) for s, p in self.servers]
        self.serversString = ', '.join(serverStrings)
        self.proxyPortsString = ', '.join(map(_addressPortStr, self.proxyPorts))

    def buildStatusStrings(self):
        """Build the status message(s) to display on the home page of the
        web interface."""
        nspam = self.bayes.nspam
        nham = self.bayes.nham
        if nspam > 10 and nham > 10:
            db_ratio = nham/float(nspam)
            if db_ratio > 5.0:
                self.warning = _("Warning: you have much more ham than " \
                                 "spam - SpamBayes works best with " \
                                 "approximately even numbers of ham and " \
                                 "spam.")
            elif db_ratio < (1/5.0):
                self.warning = _("Warning: you have much more spam than " \
                                 "ham - SpamBayes works best with " \
                                 "approximately even numbers of ham and " \
                                 "spam.")
            else:
                self.warning = ""
        elif nspam > 0 or nham > 0:
            self.warning = _("Database only has %d good and %d spam - " \
                             "you should consider performing additional " \
                             "training.") % (nham, nspam)
        else:
            self.warning = _("Database has no training information.  " \
                             "SpamBayes will classify all messages as " \
                             "'unsure', ready for you to train.")
        # Add an additional warning message if the user's thresholds are
        # truly odd.
        spam_cut = options["Categorization", "spam_cutoff"]
        ham_cut = options["Categorization", "ham_cutoff"]
        if spam_cut < 0.5:
            self.warning += _("<br/>Warning: we do not recommend " \
                              "setting the spam threshold less than 0.5.")
        if ham_cut > 0.5:
            self.warning += _("<br/>Warning: we do not recommend " \
                              "setting the ham threshold greater than 0.5.")
        if ham_cut > spam_cut:
            self.warning += _("<br/>Warning: your ham threshold is " \
                              "<b>higher</b> than your spam threshold. " \
                              "Results are unpredictable.")

    def createWorkers(self):
        """Using the options that were initialised in __init__ and then
        possibly overridden by the driver code, create the Bayes object,
        the Corpuses, the Trainers and so on."""
        print "Loading database...",
        if self.isTest:
            self.useDB = "pickle"
            self.DBName = '_pop3proxy_test.pickle'   # This is never saved.
        if not hasattr(self, "DBName"):
            self.DBName, self.useDB = storage.database_type([])
        self.bayes = storage.open_storage(self.DBName, self.useDB)
        self.mdb = spambayes.message.Message().message_info_db

        # Load stats manager.
        self.stats = Stats.Stats(options, self.mdb)

        self.buildStatusStrings()

        # Don't set up the caches and training objects when running the self-test,
        # so as not to clutter the filesystem.
        if not self.isTest:
            # Create/open the Corpuses.  Use small cache sizes to avoid hogging
            # lots of memory.
            sc = get_pathname_option("Storage", "spam_cache")
            hc = get_pathname_option("Storage", "ham_cache")
            uc = get_pathname_option("Storage", "unknown_cache")
            map(storage.ensureDir, [sc, hc, uc])
            if self.gzipCache:
                factory = GzipFileMessageFactory()
            else:
                factory = FileMessageFactory()
            age = options["Storage", "cache_expiry_days"]*24*60*60
            self.spamCorpus = ExpiryFileCorpus(age, factory, sc,
                                               '[0123456789\-]*',
                                               cacheSize=20)
            self.hamCorpus = ExpiryFileCorpus(age, factory, hc,
                                              '[0123456789\-]*',
                                              cacheSize=20)
            self.unknownCorpus = ExpiryFileCorpus(age, factory, uc,
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

    def RecordClassification(self, cls, score):
        """Record the classification in the session statistics.

        cls should match one of the options["Headers", "header_*_string"]
        values.

        score is the score the message received.        
        """
        if cls == options["Headers", "header_ham_string"]:
            self.numHams += 1
        elif cls == options["Headers", "header_spam_string"]:
            self.numSpams += 1
        else:
            self.numUnsure += 1
        self.stats.RecordClassification(score)


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
        ssl = options["pop3proxy", "use_ssl"]
        if ssl == "automatic":
            ssl = serverPort == 995
        listener = BayesProxyListener(server, serverPort, proxyPort, ssl)
        proxyListeners.append(listener)

def _recreateState():
    # Close the existing listeners and create new ones.  This won't
    # affect any running proxies - once a listener has created a proxy,
    # that proxy is then independent of it.
    # (but won't closing the database screw them?)
    global state
    for proxy in proxyListeners:
        proxy.close()
    del proxyListeners[:]

    if state.prepared:    
        # Close the state (which saves if necessary)
        state.close()
    # And get a new one going.
    state = State()

    prepare()
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

def prepare(can_stop=True):
    state.init()
    state.prepare(can_stop)
    # Launch any SMTP proxies.  Note that if the user hasn't specified any
    # SMTP proxy information in their configuration, then nothing will
    # happen.
    from spambayes import smtpproxy
    servers, proxyPorts = smtpproxy.LoadServerInfo()
    proxyListeners.extend(smtpproxy.CreateProxies(servers, proxyPorts,
                                                  smtpproxy.SMTPTrainer(state.bayes, state)))

    # setup info for the web interface
    state.buildServerStrings()

def start():
    # kick everything off
    assert state.prepared, "starting before preparing state"
    try:
        main(state.servers, state.proxyPorts, state.uiPort, state.launchUI)
    finally:
        state.close()

def stop():
    # Shutdown as though through the web UI.  This will save the DB, allow
    # any open proxy connections to complete, etc.
    from urllib import urlopen, urlencode
    urlopen('http://localhost:%d/save' % state.uiPort,
            urlencode({'how': _('Save & shutdown')})).read()


# ===================================================================
# __main__ driver.
# ===================================================================

def run():
    global state
    # Read the arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hbd:p:l:u:o:')
    except getopt.error, msg:
        print >> sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    for opt, arg in opts:
        if opt == '-h':
            print >> sys.stderr, __doc__
            sys.exit()
        elif opt == '-b':
            state.launchUI = True
        # '-p' and '-d' are handled by the storage.database_type call
        # below, in case you are wondering why they are missing.
        elif opt == '-l':
            state.proxyPorts = [_addressAndPort(a) for a in arg.split(',')]
        elif opt == '-u':
            state.uiPort = int(arg)
        elif opt == '-o':
            options.set_from_cmdline(arg, sys.stderr)

    state.DBName, state.useDB = storage.database_type(opts)

    # Let the user know what they are using...
    v = get_current_version()
    print "%s\n" % (v.get_long_version("SpamBayes POP3 Proxy"),)

    if 0 <= len(args) <= 2:
        # Normal usage, with optional server name and port number.
        if len(args) == 1:
            state.servers = [(args[0], 110)]
        elif len(args) == 2:
            state.servers = [(args[0], int(args[1]))]

        # Default to listening on port 110 for command-line-specified servers.
        if len(args) > 0 and state.proxyPorts == []:
            state.proxyPorts = [('', 110)]

        try:
            prepare()
        except AlreadyRunningException:
            print  >> sys.stderr, \
                   "ERROR: The proxy is already running on this machine."
            print  >> sys.stderr, "Please stop the existing proxy and try again"
            return
        start()

    else:
        print >> sys.stderr, __doc__

if __name__ == '__main__':
    run()
