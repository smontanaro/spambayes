#!/usr/bin/env python

"""A POP3 proxy that works with classifier.py, and adds a simple
X-Hammie-Disposition header (Yes or No) to each incoming email.
You point pop3proxy at your POP3 server, and configure your email
client to collect mail from the proxy then filter on the added
header.  Usage:

    pop3proxy.py [options] <server> [<server port>]
        <server> is the name of your real POP3 server
        <port>   is the port number of your real POP3 server, which
                 defaults to 110.

        options (the same as hammie):
            -p FILE : use the named data file
            -d      : the file is a DBM file rather than a pickle

    pop3proxy -t
        Runs a test POP3 server on port 8110; useful for testing.

    pop3proxy -h
        Displays this help message.

For safety, and to help debugging, the whole POP3 conversation is
written out to _pop3proxy.log for each run.
"""

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Richie Hindle <richie@entrian.com>"
__credits__ = "Tim Peters, Neale Pickett, all the spambayes contributors."


import sys, re, operator, errno, getopt, cPickle, time
import socket, asyncore, asynchat
import classifier, tokenizer, hammie
from Options import options

HEADER_FORMAT = '%s: %%s\r\n' % hammie.DISPHEADER
HEADER_EXAMPLE = '%s: Yes\r\n' % hammie.DISPHEADER


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
        self.bind(('', port))
        self.listen(5)

    def handle_accept(self):
        clientSocket, clientAddress = self.accept()
        args = [clientSocket] + list(self.factoryArgs)
        if self.socketMap != asyncore.socket_map:
            self.factory(*args, **{'socketMap': self.socketMap})
        else:
            self.factory(*args)


class POP3ProxyBase(asynchat.async_chat):
    """An async dispatcher that understands POP3 and proxies to a POP3
    server, calling `self.onTransaction( request, response )` for each
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
        asynchat.async_chat.__init__(self, clientSocket)
        self.request = ''
        self.set_terminator('\r\n')
        serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serverSocket.connect((serverName, serverPort))
        self.serverFile = serverSocket.makefile()
        self.push(self.serverFile.readline())

    def handle_connect(self):
        """Suppress the asyncore "unhandled connect event" warning."""
        pass

    def onTransaction(self, command, args, response):
        """Overide this.  Takes the raw request and the response, and
        returns the (possibly processed) response to pass back to the
        email client.
        """
        raise NotImplementedError

    def isMultiline(self, command, args):
        """Returns True if the given request should get a multiline
        response (assuming the response is positive).
        """
        if command in ['USER', 'PASS', 'APOP', 'QUIT',
                       'STAT', 'DELE', 'NOOP', 'RSET', 'KILL']:
            return False
        elif command in ['RETR', 'TOP']:
            return True
        elif command in ['LIST', 'UIDL']:
            return len(args) == 0
        else:
            # Assume that an unknown command will get a single-line
            # response.  This should work for errors and for POP-AUTH.
            return False

    def readResponse(self, command, args):
        """Reads the POP3 server's response and returns a tuple of
        (response, isClosing, timedOut).  isClosing is True if the
        server closes the socket, which tells found_terminator() to
        close when the response has been sent.  timedOut is set if a
        TOP or RETR request was still arriving after 30 seconds, and
        tells found_terminator() to proxy the remainder of the response.
        """
        responseLines = []
        startTime = time.time()
        isMulti = self.isMultiline(command, args)
        isClosing = False
        timedOut = False
        isFirstLine = True
        seenAllHeaders = False
        while True:
            line = self.serverFile.readline()
            if not line:
                # The socket's been closed by the server, probably by QUIT.
                isClosing = True
                break
            elif not isMulti or (isFirstLine and line.startswith('-ERR')):
                # A single-line response.
                responseLines.append(line)
                break
            elif line == '.\r\n':
                # The termination line.
                responseLines.append(line)
                break
            else:
                # A normal line - append it to the response and carry on.
                responseLines.append(line)
                seenAllHeaders = seenAllHeaders or line in ['\r\n', '\n']

            # Time out after 30 seconds for message-retrieval commands
            # if all the headers are down - found_terminator() knows how
            # to deal with this.
            if command in ['TOP', 'RETR'] and \
               seenAllHeaders and time.time() > startTime + 30:
                timedOut = True
                break

            isFirstLine = False

        return ''.join(responseLines), isClosing, timedOut

    def collect_incoming_data(self, data):
        """Asynchat override."""
        self.request = self.request + data

    def found_terminator(self):
        """Asynchat override."""
        # Send the request to the server and read the reply.
        if self.request.strip().upper() == 'KILL':
            self.serverFile.write('QUIT\r\n')
            self.serverFile.flush()
            self.send("+OK, dying.\r\n")
            self.shutdown(2)
            self.close()
            raise SystemExit
        self.serverFile.write(self.request + '\r\n')
        self.serverFile.flush()
        if self.request.strip() == '':
            # Someone just hit the Enter key.
            command, args = ('', '')
        else:
            splitCommand = self.request.strip().split(None, 1)
            command = splitCommand[0].upper()
            args = splitCommand[1:]
        rawResponse, isClosing, timedOut = self.readResponse(command, args)

        # Pass the request and the raw response to the subclass and
        # send back the cooked response.
        cookedResponse = self.onTransaction(command, args, rawResponse)
        self.push(cookedResponse)
        self.request = ''

        # If readResponse() timed out, we still need to read and proxy
        # the rest of the message.
        if timedOut:
            while True:
                line = self.serverFile.readline()
                if not line:
                    # The socket's been closed by the server.
                    isClosing = True
                    break
                elif line == '.\r\n':
                    # The termination line.
                    self.push(line)
                    break
                else:
                    # A normal line.
                    self.push(line)

        # If readResponse() or the loop above decided that the server
        # has closed its socket, close this one when the response has
        # been sent.
        if isClosing:
            self.close_when_done()

    def handle_error(self):
        """Let SystemExit cause an exit."""
        type, v, t = sys.exc_info()
        if type == SystemExit:
            raise
        else:
            asynchat.async_chat.handle_error(self)


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

    def send(self, data):
        """Logs the data to the log file."""
        self.logFile.write(data)
        self.logFile.flush()
        return POP3ProxyBase.send(self, data)

    def recv(self, size):
        """Logs the data to the log file."""
        data = POP3ProxyBase.recv(self, size)
        self.logFile.write(data)
        self.logFile.flush()
        return data

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

            # Now find the spam disposition and add the header.  The
            # trailing space in "No " ensures consistent lengths - this
            # is required because POP3 commands like 'STAT' and 'LIST'
            # need to be able to report the size of a message before
            # it's been classified.
            prob = self.bayes.spamprob(tokenizer.tokenize(message))
            if prob > options.spam_cutoff:
                disposition = "Yes"
            else:
                disposition = "No "
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


def main(serverName, serverPort, proxyPort, pickleName, useDB):
    """Runs the proxy forever or until a 'KILL' command is received or
    someone hits Ctrl+Break."""
    print "Loading database...",
    bayes = hammie.createbayes(pickleName, useDB)
    print "Done."
    BayesProxyListener(serverName, serverPort, proxyPort, bayes)
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


class TestPOP3Server(asynchat.async_chat):
    """Minimal POP3 server, for testing purposes.  Doesn't support TOP
    or UIDL.  USER, PASS, APOP, DELE and RSET simply return "+OK"
    without doing anything.  Also understands the 'KILL' command, to
    kill it.  The mail content is the example messages above.
    """

    def __init__(self, clientSocket, socketMap=asyncore.socket_map):
        # Grumble: asynchat.__init__ doesn't take a 'map' argument,
        # hence the two-stage construction.
        asynchat.async_chat.__init__(self)
        asynchat.async_chat.set_socket(self, clientSocket, socketMap)
        self.maildrop = [spam1, good1]
        self.set_terminator('\r\n')
        self.okCommands = ['USER', 'PASS', 'APOP', 'NOOP',
                           'DELE', 'RSET', 'QUIT', 'KILL']
        self.handlers = {'STAT': self.onStat,
                         'LIST': self.onList,
                         'RETR': self.onRetr}
        self.push("+OK ready\r\n")
        self.request = ''

    def handle_connect(self):
        """Suppress the asyncore "unhandled connect event" warning."""
        pass

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
                raise SystemExit
        else:
            handler = self.handlers.get(command, self.onUnknown)
            self.push(handler(command, args))
        self.request = ''

    def handle_error(self):
        """Let SystemExit cause an exit."""
        type, v, t = sys.exc_info()
        if type == SystemExit:
            raise
        else:
            asynchat.async_chat.handle_error(self)

    def onStat(self, command, args):
        """POP3 STAT command."""
        maildropSize = reduce(operator.add, map(len, self.maildrop))
        maildropSize += len(self.maildrop) * len(HEADER_EXAMPLE)
        return "+OK %d %d\r\n" % (len(self.maildrop), maildropSize)

    def onList(self, command, args):
        """POP3 LIST command, with optional message number argument."""
        if args:
            number = int(args)
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

    def onRetr(self, command, args):
        """POP3 RETR command."""
        number = int(args)
        if 0 < number <= len(self.maildrop):
            message = self.maildrop[number-1]
            return "+OK\r\n%s\r\n.\r\n" % message
        else:
            return "-ERR no such message\r\n"

    def onUnknown(self, command, args):
        """Unknown POP3 command."""
        return "-ERR Unknown command: '%s'\r\n" % command


def test():
    """Runs a self-test using TestPOP3Server, a minimal POP3 server
    that serves the example emails above.
    """
    # Run a proxy and a test server in separate threads with separate
    # asyncore environments.
    import threading
    testServerReady = threading.Event()
    def runTestServer():
        testSocketMap = {}
        TestListener(socketMap=testSocketMap)
        testServerReady.set()
        asyncore.loop(map=testSocketMap)

    def runProxy():
        # Name the database in case it ever gets auto-flushed to disk.
        bayes = hammie.createbayes('_pop3proxy.db')
        BayesProxyListener('localhost', 8110, 8111, bayes)
        bayes.learn(tokenizer.tokenize(spam1), True)
        bayes.learn(tokenizer.tokenize(good1), False)
        asyncore.loop()

    threading.Thread(target=runTestServer).start()
    testServerReady.wait()
    threading.Thread(target=runProxy).start()

    # Connect to the proxy.
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy.connect(('localhost', 8111))
    assert proxy.recv(100) == "+OK ready\r\n"

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
        assert response.find(hammie.DISPHEADER) != -1

    # Kill the proxy and the test server.
    proxy.sendall("kill\r\n")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.connect(('localhost', 8110))
    server.sendall("kill\r\n")


# ===================================================================
# __main__ driver.
# ===================================================================

if __name__ == '__main__':
    # Read the arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'htdp:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    pickleName = hammie.DEFAULTDB
    useDB = False
    runTestServer = False
    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-t':
            runTestServer = True
        elif opt == '-d':
            useDB = True
        elif opt == '-p':
            pickleName = arg

    # Do whatever we've been asked to do...
    if not opts and not args:
        print "Running a self-test (use 'pop3proxy -h' for help)"
        test()
        print "Self-test passed."   # ...else it would have asserted.

    elif runTestServer:
        print "Running a test POP3 server on port 8110..."
        TestListener()
        asyncore.loop()

    elif len(args) == 1:
        # Named POP3 server, default port.
        main(args[0], 110, 110, pickleName, useDB)

    elif len(args) == 2:
        # Named POP3 server, named port.
        main(args[0], int(args[1]), 110, pickleName, useDB)

    else:
        print >>sys.stderr, __doc__
