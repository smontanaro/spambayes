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

            -d FILE : use the named DBM database file
            -D FILE : the the named Pickle database file
            -l port : proxy listens on this port number (default 110)
            -u port : User interface listens on this port number
                      (default 8880; Browse http://localhost:8880/)
            -b      : Launch a web browser showing the user interface.
            -s      : Start a SMTPProxy server for training use.

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


User interface improvements:

 o Once the pieces are on separate pages, make the paste box bigger.
 o Deployment: Windows executable?  atlaxwin and ctypes?  Or just
   webbrowser?
 o Can it cleanly dynamically update its status display while having a
   POP3 conversation?  Hammering reload sucks.
 o Save the stats (num classified, etc.) between sessions.
 o "Reload database" button.


New features:

 o "Send me an email every [...] to remind me to train on new
   messages."
 o "Send me a status email every [...] telling how many mails have been
   classified, etc."
 o Remove any existing X-Spambayes-Classification header from incoming
   emails.
 o Whitelist.
 o Online manual.
 o Links to project homepage, mailing list, etc.
 o List of words with stats (it would have to be paged!) a la SpamSieve.


Code quality:

 o Move the UI into its own module.
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

import os, sys, re, operator, errno, getopt, time, bisect, binascii
import socket, asyncore, asynchat, cgi
import mailbox, email.Header
from email.Iterators import typed_subpart_iterator
import spambayes
from spambayes import storage, tokenizer, mboxutils, PyMeldLite, Dibbler
from spambayes.FileCorpus import FileCorpus, ExpiryFileCorpus
from spambayes.FileCorpus import FileMessageFactory, GzipFileMessageFactory
from spambayes.OptionConfig import OptionsConfigurator
from spambayes.Options import options

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


# HEADER_EXAMPLE is the longest possible header - the length of this one
# is added to the size of each message.
HEADER_FORMAT = '%s: %%s\r\n' % options.hammie_header_name
HEADER_EXAMPLE = '%s: xxxxxxxxxxxxxxxxxxxx\r\n' % options.hammie_header_name

IMAGES = ('helmet', 'status', 'config',
          'message', 'train', 'classify', 'query')

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
            self.command = self.args = ''
        else:
            # A proper command.
            splitCommand = self.request.strip().split(None, 1)
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
        self.args = ''
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
            (prob, clues) = state.bayes.spamprob\
                            (tokenizer.tokenize(messageText),
                             evidence=True)
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

            if options.pop3proxy_strip_incoming_mailids == True:
                s = re.compile(options.pop3proxy_mailid_header_name + \
                               ': [\d-]+[\\r]?[\\n]?')
                messageText = s.sub('', messageText)

            headers, body = re.split(r'\n\r?\n', messageText, 1)
            messageName = state.getNewMessageName()
            headers += '\r\n%s: %s\r\n' % (options.hammie_header_name,
                                           disposition)
            if command == 'RETR' and not state.isTest:
                if options.pop3proxy_add_mailid_to.find("header") != -1:
                    headers += options.pop3proxy_mailid_header_name \
                            + ": " + messageName + "\r\n"
                if options.pop3proxy_add_mailid_to.find("body") != -1:
                    body = body[:len(body)-3] + \
                           options.pop3proxy_mailid_header_name + ": " \
                            + messageName + "\r\n.\r\n"
            else:
                headers += options.hammie_header_name + "-ID: Test\r\n"

            if options.pop3proxy_include_prob:
                headers += '%s: %s\r\n' % (options.pop3proxy_prob_header_name,
                                           prob)
            if options.pop3proxy_include_thermostat:
                thermostat = '**********'
                headers += '%s: %s\r\n' % \
                          (options.pop3proxy_thermostat_header_name,
                           thermostat[int(prob*10):])
            if options.pop3proxy_include_evidence:
                headers += options.pop3proxy_evidence_header_name + ": "
                headers += "; ".join(["%r: %.2f" % (word, prob)
                         for word, score in clues
                         if (word[0] == '*' or
                             score <= options.clue_mailheader_cutoff or
                             score >= 1.0 - options.clue_mailheader_cutoff)])
            headers += "\r\n"
            
            if options.pop3proxy_notate_to \
                and disposition == options.header_spam_string:
                # add 'spam' as recip only if spam
                tore = re.compile("^To: ", re.IGNORECASE | re.MULTILINE)
                headers = re.sub(tore,"To: %s," % (disposition),
                     headers)
                
            if options.pop3proxy_notate_subject \
                and disposition == options.header_spam_string:
                # add 'spam' to subject if spam
                tore = re.compile("^Subject: ", re.IGNORECASE | re.MULTILINE)
                headers = re.sub(tore,"Subject: %s " % (disposition),
                     headers)
                
            messageText = headers + body

            # Cache the message; don't pollute the cache with test messages.
            if command == 'RETR' and not state.isTest \
                    and options.pop3proxy_cache_messages:
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


class UserInterfaceServer(Dibbler.HTTPServer):
    """Implements the web server component via a Dibbler plugin."""

    def __init__(self, uiPort):
        Dibbler.HTTPServer.__init__(self, uiPort)
        print 'User interface url is http://localhost:%d/' % (uiPort)


def readUIResources():
    """Returns ui.html and a dictionary of Gifs.  Used here and by
    OptionConfig"""

    # Using `exec` is nasty, but I couldn't figure out a way of making
    # `getattr` or `__import__` work with ResourcePackage.
    from spambayes.resources import ui_html
    images = {}
    for baseName in IMAGES:
        moduleName = '%s.%s_gif' % ('spambayes.resources', baseName)
        module = __import__(moduleName, {}, {}, ('spambayes', 'resources'))
        images[baseName] = module.data
    return ui_html.data, images


class UserInterface(Dibbler.HTTPPlugin):
    """Serves the HTML user interface of the proxy."""

    def __init__(self):
        """Load up the necessary resources: ui.html and helmet.gif."""
        Dibbler.HTTPPlugin.__init__(self)
        htmlSource, self._images = readUIResources()
        self.html = PyMeldLite.Meld(htmlSource, readonly=True)

    def onIncomingConnection(self, clientSocket):
        """Checks the security settings."""
        return options.html_ui_allow_remote_connections or \
               clientSocket.getpeername()[0] == clientSocket.getsockname()[0]

    def _writePreamble(self, name, parent=None, showImage=True):
        """Writes the HTML for the beginning of a page - time-consuming
        methlets use this and `_writePostamble` to write the page in
        pieces, including progress messages.  `parent` (if given) should
        be a pair: `(url, label)`, eg. `('review', 'Review')`."""

        # Take the whole palette and remove the content and the footer,
        # leaving the header and an empty body.
        html = self.html.clone()
        html.mainContent = " "
        del html.footer

        # Add in the name of the page and remove the link to Home if this
        # *is* Home.
        html.title = name
        if name == 'Home':
            del html.homelink
            html.pagename = "Home"
        elif parent:
            html.pagename = "> <a href='%s'>%s</a> > %s" % \
                            (parent[0], parent[1], name)
        else:
            html.pagename = "> " + name

        # Remove the helmet image if we're not showing it - this happens on
        # shutdown because the browser might ask for the image after we've
        # exited.
        if not showImage:
            del html.helmet

        # Strip the closing tags, so we push as far as the start of the main
        # content.  We'll push the closing tags at the end.
        self.writeOKHeaders('text/html')
        self.write(re.sub(r'</div>\s*</body>\s*</html>', '', str(html)))

    def _writePostamble(self):
        """Writes the end of time-consuming pages - see `_writePreamble`."""
        footer = self.html.footer.clone()
        footer.timestamp = time.asctime(time.localtime())
        self.write("</div>" + self.html.footer)
        self.write("</body></html>")

    def _trimHeader(self, field, limit, quote=False):
        """Trims a string, adding an ellipsis if necessary and HTML-quoting
        on request.  Also pumps it through email.Header.decode_header, which
        understands charset sections in email headers - I suspect this will
        only work for Latin character sets, but hey, it works for Francois
        Granger's name.  8-)"""

        try:
            sections = email.Header.decode_header(field)
        except (binascii.Error, email.Errors.HeaderParseError):
            sections = [(field, None)]
        field = ' '.join([text for text, unused in sections])
        if len(field) > limit:
            field = field[:limit-3] + "..."
        if quote:
            field = cgi.escape(field)
        return field

    def onHome(self):
        """Serve up the homepage."""
        stateDict = state.__dict__.copy()
        stateDict.update(state.bayes.__dict__)
        statusTable = self.html.statusTable.clone()
        if not state.servers:
            statusTable.proxyDetails = "No POP3 proxies running."
        content = (self._buildBox('Status and Configuration',
                                  'status.gif', statusTable % stateDict)+
                   self._buildBox('Train on proxied messages',
                                  'train.gif', self.html.reviewText) +
                   self._buildTrainBox() +
                   self._buildClassifyBox() +
                   self._buildBox('Word query', 'query.gif',
                                  self.html.wordQuery) +
                   self._buildBox('Find message', 'query.gif',
                                  self.html.findMessage)
                   )
        self._writePreamble("Home")
        self.write(content)
        self._writePostamble()

    def _doSave(self):
        """Saves the database."""
        self.write("<b>Saving... ")
        self.flush()
        state.bayes.store()
        self.write("Done</b>.\n")

    def onSave(self, how):
        """Command handler for "Save" and "Save & shutdown"."""
        isShutdown = how.lower().find('shutdown') >= 0
        self._writePreamble("Save", showImage=(not isShutdown))
        self._doSave()
        if isShutdown:
            self.write("<p>%s</p>" % self.html.shutdownMessage)
            self.write("</div></body></html>")
            self.flush()
            ## Is this still required?: self.shutdown(2)
            self.close()
            raise SystemExit
        self._writePostamble()

    def _convertUploadToMessageList(self, content):
        """Returns a list of raw messages extracted from uploaded content.
        You can upload either a single message or an mbox file."""
        if content.startswith('From '):
            # Get a list of raw messages from the mbox content.
            class SimpleMessage:
                def __init__(self, fp):
                    self.guts = fp.read()
            contentFile = StringIO.StringIO(content)
            mbox = mailbox.PortableUnixMailbox(contentFile, SimpleMessage)
            return map(lambda m: m.guts, mbox)
        else:
            # Just the one message.
            return [content]

    def onUpload(self, file):
        """Save a message for later training - used by Skip's proxytee.py."""
        # Convert platform-specific line endings into unix-style.
        file = file.replace('\r\n', '\n').replace('\r', '\n')

        # Get a message list from the upload and write it into the cache.
        messages = self._convertUploadToMessageList(file)
        for m in messages:
            messageName = state.getNewMessageName()
            message = state.unknownCorpus.makeMessage(messageName)
            message.setSubstance(m)
            state.unknownCorpus.addMessage(message)

        # Return a link Home.
        self.write("<p>OK. Return <a href='home'>Home</a>.</p>")

    def onTrain(self, file, text, which):
        """Train on an uploaded or pasted message."""
        self._writePreamble("Train")

        # Upload or paste?  Spam or ham?
        content = file or text
        isSpam = (which == 'Train as Spam')

        # Convert platform-specific line endings into unix-style.
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # The upload might be a single message or am mbox file.
        messages = self._convertUploadToMessageList(content)

        # Append the message(s) to a file, to make it easier to rebuild
        # the database later.   This is a temporary implementation -
        # it should keep a Corpus of trained messages.
        if isSpam:
            f = open("_pop3proxyspam.mbox", "a")
        else:
            f = open("_pop3proxyham.mbox", "a")

        # Train on the uploaded message(s).
        self.write("<b>Training...</b>\n")
        self.flush()
        for message in messages:
            tokens = tokenizer.tokenize(message)
            state.bayes.learn(tokens, isSpam)
            f.write("From pop3proxy@spambayes.org Sat Jan 31 00:00:00 2000\n")
            f.write(message)
            f.write("\n\n")

        # Save the database and return a link Home and another training form.
        f.close()
        self._doSave()
        self.write("<p>OK. Return <a href='home'>Home</a> or train again:</p>")
        self.write(self._buildTrainBox())
        self._writePostamble()

    def _keyToTimestamp(self, key):
        """Given a message key (as seen in a Corpus), returns the timestamp
        for that message.  This is the time that the message was received,
        not the Date header."""
        return long(key[:10])

    def _getTimeRange(self, timestamp):
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

    def _buildReviewKeys(self, timestamp):
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
                timestamp = self._keyToTimestamp(allKeys[-1])
            else:
                timestamp = time.time()
        start, end, date = self._getTimeRange(timestamp)

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
            prior = self._keyToTimestamp(allKeys[startKeyIndex-1])
        if endKeyIndex != len(allKeys):
            end = self._keyToTimestamp(allKeys[endKeyIndex])

        # Return the keys and their date.
        return keys, date, prior, start, end

    def _makeMessageInfo(self, message):
        """Given an email.Message, return an object with subjectHeader,
        fromHeader and bodySummary attributes.  These objects are passed into
        appendMessages by onReview - passing email.Message objects directly
        uses too much memory."""
        subjectHeader = message["Subject"] or "(none)"
        fromHeader = message["From"] or "(none)"
        try:
            part = typed_subpart_iterator(message, 'text', 'plain').next()
            text = part.get_payload()
        except StopIteration:
            try:
                part = typed_subpart_iterator(message, 'text', 'html').next()
                text = part.get_payload()
                text, unused = tokenizer.crack_html_style(text)
                text, unused = tokenizer.crack_html_comment(text)
                text = tokenizer.html_re.sub(' ', text)
                text = '(this message only has an HTML body)\n' + text
            except StopIteration:
                text = '(this message has no text body)'
        if type(text) == type([]):  # gotta be a 'right' way to do this
            text = "(this message is a digest of %s messages)" % (len(text))
        else:
            text = text.replace('&nbsp;', ' ')      # Else they'll be quoted
            text = re.sub(r'(\s)\s+', r'\1', text)  # Eg. multiple blank lines
            text = text.strip()

        class _MessageInfo:
            pass
        messageInfo = _MessageInfo()
        messageInfo.subjectHeader = self._trimHeader(subjectHeader, 50, True)
        messageInfo.fromHeader = self._trimHeader(fromHeader, 40, True)
        messageInfo.bodySummary = self._trimHeader(text, 200)
        return messageInfo

    def _appendMessages(self, table, keyedMessageInfo, label):
        """Appends the rows of a table of messages to 'table'."""
        stripe = 0
        for key, messageInfo in keyedMessageInfo:
            row = self.html.reviewRow.clone()
            if label == 'Spam':
                row.spam.checked = 1
            elif label == 'Ham':
                row.ham.checked = 1
            else:
                row.defer.checked = 1
            row.subject = messageInfo.subjectHeader
            row.subject.title = messageInfo.bodySummary
            row.subject.href="view?key=%s&corpus=%s" % (key, label)
            row.from_ = messageInfo.fromHeader
            setattr(row, 'class', ['stripe_on', 'stripe_off'][stripe]) # Grr!
            row = str(row).replace('TYPE', label).replace('KEY', key)
            table += row
            stripe = stripe ^ 1

    def onReview(self, **params):
        """Present a list of message for (re)training."""
        # Train/discard sumbitted messages.
        self._writePreamble("Review")
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
                    sourceCorpus = None
                    if state.unknownCorpus.get(id) is not None:
                        sourceCorpus = state.unknownCorpus
                    elif state.hamCorpus.get(id) is not None:
                        sourceCorpus = state.hamCorpus
                    elif state.spamCorpus.get(id) is not None:
                        sourceCorpus = state.spamCorpus
                    if sourceCorpus is not None:
                        try:
                            targetCorpus.takeMessage(id, sourceCorpus)
                            if numTrained == 0:
                                self.write("<p><b>Training... ")
                                self.flush()
                            numTrained += 1
                        except KeyError:
                            pass  # Must be a reload.

        # Report on any training, and save the database if there was any.
        if numTrained > 0:
            plural = ''
            if numTrained != 1:
                plural = 's'
            self.write("Trained on %d message%s. " % (numTrained, plural))
            self._doSave()
            self.write("<br>&nbsp;")

        title = ""
        keys = []
        sourceCorpus = state.unknownCorpus
        # If any messages were deferred, show the same page again.
        if numDeferred > 0:
            start = self._keyToTimestamp(id)

        # Else after submitting a whole page, display the prior page or the
        # next one.  Derive the day of the submitted page from the ID of the
        # last processed message.
        elif id:
            start = self._keyToTimestamp(id)
            unused, unused, prior, unused, next = self._buildReviewKeys(start)
            if prior:
                start = prior
            else:
                start = next

        # Else if they've hit Previous or Next, display that page.
        elif params.get('go') == 'Next day':
            start = self._keyToTimestamp(params['next'])
        elif params.get('go') == 'Previous day':
            start = self._keyToTimestamp(params['prior'])

        # Else if an id has been specified, just show that message
        elif params.get('find') is not None:
            key = params['find']
            error = False
            if key == "":
                error = True
                page = "<p>You must enter an id to find.</p>"
            elif state.unknownCorpus.get(key) == None:
                # maybe this message has been moved to the spam
                # or ham corpus
                if state.hamCorpus.get(key) != None:
                    sourceCorpus = state.hamCorpus
                elif state.spamCorpus.get(key) != None:
                    sourceCorpus = state.spamCorpus
                else:
                    error = True
                    page = "<p>Could not find message with id '"
                    page += key + "' - maybe it expired.</p>"
            if error == True:
                title = "Did not find message"
                box = self._buildBox(title, 'status.gif', page)
                self.write(box)
                self.write(self._buildBox('Find message', 'query.gif',
                                          self.html.findMessage))
                self._writePostamble()
                return
            keys.append(params['find'])
            prior = this = next = 0
            title = "Found message"

        # Else show the most recent day's page, as decided by _buildReviewKeys.
        else:
            start = 0

        # Build the lists of messages: spams, hams and unsure.
        if len(keys) == 0:
            keys, date, prior, this, next = self._buildReviewKeys(start)
        keyedMessageInfo = {options.header_spam_string: [],
                            options.header_ham_string: [],
                            options.header_unsure_string: []}
        for key in keys:
            # Parse the message, get the judgement header and build a message
            # info object for each message.
            cachedMessage = sourceCorpus[key]
            message = mboxutils.get_message(cachedMessage.getSubstance())
            judgement = message[options.hammie_header_name]
            if judgement is None:
                judgement = options.header_unsure_string
            else:
                judgement = judgement.split(';')[0].strip()
            messageInfo = self._makeMessageInfo(message)
            keyedMessageInfo[judgement].append((key, messageInfo))

        # Present the list of messages in their groups in reverse order of
        # appearance.
        if keys:
            page = self.html.reviewtable.clone()
            if prior:
                page.prior.value = prior
                del page.priorButton.disabled
            if next:
                page.next.value = next
                del page.nextButton.disabled
            templateRow = page.reviewRow.clone()
            page.table = ""  # To make way for the real rows.
            for header, label in ((options.header_spam_string, 'Spam'),
                                  (options.header_ham_string, 'Ham'),
                                  (options.header_unsure_string, 'Unsure')):
                messages = keyedMessageInfo[header]
                if messages:
                    subHeader = str(self.html.reviewSubHeader)
                    subHeader = subHeader.replace('TYPE', label)
                    page.table += self.html.blankRow
                    page.table += subHeader
                    self._appendMessages(page.table, messages, label)

            page.table += self.html.trainRow
            if title == "":
                title = "Untrained messages received on %s" % date
            box = self._buildBox(title, None, page)  # No icon, to save space.
        else:
            page = "<p>There are no untrained messages to display. "
            page += "Return <a href='home'>Home</a>.</p>"
            title = "No untrained messages"
            box = self._buildBox(title, 'status.gif', page)

        self.write(box)
        self._writePostamble()

    def onView(self, key, corpus):
        """View a message - linked from the Review page."""
        self._writePreamble("View message", parent=('review', 'Review'))
        message = state.unknownCorpus.get(key)
        if message:
            self.write("<pre>%s</pre>" % cgi.escape(message.getSubstance()))
        else:
            self.write("<p>Can't find message %r. Maybe it expired.</p>" % key)
        self._writePostamble()

    def onClassify(self, file, text, which):
        """Classify an uploaded or pasted message."""
        message = file or text
        message = message.replace('\r\n', '\n').replace('\r', '\n') # For Macs

        cluesTable = self.html.cluesTable.clone()
        cluesRow = cluesTable.cluesRow.clone()
        del cluesTable.cluesRow   # Delete dummy row to make way for real ones
        (probability, clues) = state.bayes.spamprob(tokenizer.tokenize(message),\
                                                    evidence=True)
        for word, wordProb in clues:
            cluesTable += cluesRow % (cgi.escape(word), wordProb)

        results = self.html.classifyResults.clone()
        results.probability = probability
        results.cluesBox = self._buildBox("Clues:", 'status.gif', cluesTable)
        results.classifyAnother = self._buildClassifyBox()
        self._writePreamble("Classify")
        self.write(results)
        self._writePostamble()

    def onWordquery(self, word):
        if word == "":
            stats = "You must enter a word."
        else:
            word = word.lower()
            wordinfo = state.bayes._wordinfoget(word)
            if wordinfo:
                stats = self.html.wordStats.clone()
                stats.spamcount = wordinfo.spamcount
                stats.hamcount = wordinfo.hamcount
                stats.spamprob = state.bayes.probability(wordinfo)
            else:
                stats = "%r does not exist in the database." % cgi.escape(word)

        query = self.html.wordQuery.clone()
        query.word.value = word
        statsBox = self._buildBox("Statistics for %r" % cgi.escape(word),
                                  'status.gif', stats)
        queryBox = self._buildBox("Word query", 'query.gif', query)
        self._writePreamble("Word query")
        self.write(statsBox + queryBox)
        self._writePostamble()

    def _writeImage(self, image):
        self.writeOKHeaders('image/gif')
        self.write(self._images[image])

    # If you are easily offended, look away now...
    for imageName in IMAGES:
        exec "def %s(self): self._writeImage('%s')" % \
             ("on%sGif" % imageName.capitalize(), imageName)

    def _buildBox(self, heading, icon, content):
        """Builds a yellow-headed HTML box."""
        box = self.html.headedBox.clone()
        box.heading = heading
        if icon:
            box.icon.src = icon
        else:
            del box.iconCell
        box.boxContent = content
        return box

    def _buildClassifyBox(self):
        """Returns a "Classify a message" box.  This is used on both the Home
        page and the classify results page.  The Classify form is based on the
        Upload form."""

        form = self.html.upload.clone()
        del form.or_mbox
        del form.submit_spam
        del form.submit_ham
        form.action = "classify"
        return self._buildBox("Classify a message", 'classify.gif', form)

    def _buildTrainBox(self):
        """Returns a "Train on a given message" box.  This is used on both
        the Home page and the training results page.  The Train form is
        based on the Upload form."""

        form = self.html.upload.clone()
        del form.submit_classify
        return self._buildBox("Train on a given message", 'message.gif', form)

    def reReadOptions(self):
        """Called by the config page when the user saves some new options, or
        restores the defaults."""
        # Reload the options.
        global state
        state.bayes.store()
        reload(spambayes.Options)
        global options
        from spambayes.Options import options

        # Recreate the state.
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
        self.servers = []
        self.proxyPorts = []
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
            for server in options.pop3proxy_servers.split(','):
                server = server.strip()
                if server.find(':') > -1:
                    server, port = server.split(':', 1)
                else:
                    port = '110'
                self.servers.append((server, int(port)))

        if options.pop3proxy_ports:
            splitPorts = options.pop3proxy_ports.split(',')
            self.proxyPorts = map(_addressAndPort, splitPorts)

        if len(self.servers) != len(self.proxyPorts):
            print "pop3proxy_servers & pop3proxy_ports are different lengths!"
            sys.exit()

        # Load up the other settings from Option.py / bayescustomize.ini
        self.useDB = options.pop3proxy_persistent_use_database
        self.uiPort = options.html_ui_port
        self.launchUI = options.html_ui_launch_browser
        self.gzipCache = options.pop3proxy_cache_use_gzip
        self.cacheExpiryDays = options.pop3proxy_cache_expiry_days
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
            options.pop3proxy_persistent_storage_file = \
                        '_pop3proxy_test.pickle'   # This is never saved.
        filename = options.pop3proxy_persistent_storage_file
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
            map(ensureDir, [options.pop3proxy_spam_cache,
                            options.pop3proxy_ham_cache,
                            options.pop3proxy_unknown_cache])
            if self.gzipCache:
                factory = GzipFileMessageFactory()
            else:
                factory = FileMessageFactory()
            age = options.pop3proxy_cache_expiry_days*24*60*60
            self.spamCorpus = ExpiryFileCorpus(age, factory,
                                               options.pop3proxy_spam_cache,
                                               '[0123456789]*', cacheSize=20)
            self.hamCorpus = ExpiryFileCorpus(age, factory,
                                              options.pop3proxy_ham_cache,
                                              '[0123456789]*', cacheSize=20)
            self.unknownCorpus = FileCorpus(factory,
                                            options.pop3proxy_unknown_cache,
                                            '[0123456789]*', cacheSize=20)

            # Expire old messages from the trained corpuses.
            self.spamCorpus.removeExpiredMessages()
            self.hamCorpus.removeExpiredMessages()

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

def main(servers, proxyPorts, uiPort, launchUI):
    """Runs the proxy forever or until a 'KILL' command is received or
    someone hits Ctrl+Break."""
    _createProxies(servers, proxyPorts)
    httpServer = UserInterfaceServer(uiPort)
    proxyUI = UserInterface()
    httpServer.register(proxyUI, OptionsConfigurator(proxyUI))
    Dibbler.run(launchBrowser=launchUI)


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

class TestListener(Dibbler.Listener):
    """Listener for TestPOP3Server.  Works on port 8110, to co-exist
    with real POP3 servers."""

    def __init__(self, socketMap=asyncore.socket_map):
        Dibbler.Listener.__init__(self, 8110, TestPOP3Server,
                                  (socketMap,), socketMap=socketMap)


class TestPOP3Server(Dibbler.BrighterAsyncChat):
    """Minimal POP3 server, for testing purposes.  Doesn't support
    UIDL.  USER, PASS, APOP, DELE and RSET simply return "+OK"
    without doing anything.  Also understands the 'KILL' command, to
    kill it.  The mail content is the example messages above.
    """

    def __init__(self, clientSocket, socketMap):
        # Grumble: asynchat.__init__ doesn't take a 'map' argument,
        # hence the two-stage construction.
        Dibbler.BrighterAsyncChat.__init__(self)
        Dibbler.BrighterAsyncChat.set_socket(self, clientSocket, socketMap)
        self.maildrop = [spam1, good1]
        self.set_terminator('\r\n')
        self.okCommands = ['USER', 'PASS', 'APOP', 'NOOP',
                           'DELE', 'RSET', 'QUIT', 'KILL']
        self.handlers = {'CAPA': self.onCapa,
                         'STAT': self.onStat,
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
                self.socket.shutdown(2)
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

    def onCapa(self, command, args):
        """POP3 CAPA command.  This lies about supporting pipelining for
        test purposes - the POP3 proxy *doesn't* support pipelining, and
        we test that it correctly filters out that capability from the
        proxied capability list."""
        lines = ["+OK Capability list follows",
                 "PIPELINING",
                 "TOP",
                 ".",
                 ""]
        return '\r\n'.join(lines)

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
    def runUIAndProxy():
        httpServer = UserInterfaceServer(8881)
        proxyUI = UserInterface()
        httpServer.register(proxyUI, OptionsConfigurator(proxyUI))
        BayesProxyListener('localhost', 8110, ('', 8111))
        state.bayes.learn(tokenizer.tokenize(spam1), True)
        state.bayes.learn(tokenizer.tokenize(good1), False)
        proxyReady.set()
        Dibbler.run()

    threading.Thread(target=runTestServer).start()
    testServerReady.wait()
    threading.Thread(target=runUIAndProxy).start()
    proxyReady.wait()

    # Connect to the proxy and the test server.
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy.connect(('localhost', 8111))
    response = proxy.recv(100)
    assert response == "+OK ready\r\n"
    pop3Server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pop3Server.connect(('localhost', 8110))
    response = pop3Server.recv(100)
    assert response == "+OK ready\r\n"

    # Verify that the test server claims to support pipelining.
    pop3Server.send("capa\r\n")
    response = pop3Server.recv(1000)
    assert response.find("PIPELINING") >= 0

    # Ask for the capabilities via the proxy, and verify that the proxy
    # is filtering out the PIPELINING capability.
    proxy.send("capa\r\n")
    response = proxy.recv(1000)
    assert response.find("PIPELINING") == -1

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
    pop3Server.sendall("kill\r\n")
    pop3Server.recv(100)


# ===================================================================
# __main__ driver.
# ===================================================================

def run():
    # Read the arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'htbzpsd:D:l:u:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    runSelfTest = False
    launchSMTPProxy = False
    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-t':
            state.isTest = True
            state.runTestServer = True
        elif opt == '-b':
            state.launchUI = True
        elif opt == '-s':
            launchSMTPProxy = True
        elif opt == '-d':   # dbm file
            state.useDB = True
            options.pop3proxy_persistent_storage_file = arg
        elif opt == '-D':   # pickle file
            state.useDB = False
            options.pop3proxy_persistent_storage_file = arg
        elif opt == '-p':   # dead option
            print >>sys.stderr, "-p option is no longer supported, use -D\n"
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-l':
            state.proxyPorts = [_addressAndPort(arg)]
        elif opt == '-u':
            state.uiPort = int(arg)
        elif opt == '-z':
            state.isTest = True
            runSelfTest = True

    # Do whatever we've been asked to do...
    state.createWorkers()

    if launchSMTPProxy:
        from smtpproxy import LoadServerInfo, CreateProxies
        servers, proxyPorts = LoadServerInfo()
        CreateProxies(servers, proxyPorts, state)
        LoadServerInfo()
    
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

        state.buildServerStrings()
        main(state.servers, state.proxyPorts, state.uiPort, state.launchUI)

    else:
        print >>sys.stderr, __doc__

if __name__ == '__main__':
    run()
