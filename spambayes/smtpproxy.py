#!/usr/bin/env python

"""A SMTP proxy that works with pop3proxy.py, and monitors mail
sent to two particular addresses.  Mail to these addresses is blocked,
a spambayes id is extracted from them, and the original messages are
trained on (from the Corpus cache).  You point smtpproxy at your SMTP
server, and configure your email client to send mail through the proxy
then forward/bounce any incorrectly classified messages to the ham/spam
training address. To use, run pop3proxy.py with the switch '-s'.

All options are found in the [pop3proxy] and [smtpproxy] sections of the
.ini file.
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
__credits__ = "Tim Stone, all the Spambayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


todo = """
It would be nice if spam/ham could be bulk forwarded to the proxy,
rather than one by one.  This would require separating the different
messages and extracting the correct ids.  Simply changing to find
*all* the ids in a message, rather than stopping after one *might*
work, but I don't really know.  Richie Hindle suggested something along
these lines back in September '02.

Testing:

 o Test with as many clients as possible to check that the
   id is correctly extracted from the forwarded/bounced message.

MUA information:
A '*' in the Header column signifies that the smtpproxy can extract
the id from the headers only.  A '*' in the Body column signifies that
the smtpproxy can extract the id from the body of the message, if it
is there.
                                                        Header	Body
*** Windows 2000 MUAs ***
Eudora 5.2 Forward                                         *     *
Eudora 5.2 Redirect                                              *
Netscape Messenger (4.7) Forward (inline)                  *     *
Netscape Messenger (4.7) Forward (quoted) Plain      	         *
Netscape Messenger (4.7) Forward (quoted) HTML      	         *
Netscape Messenger (4.7) Forward (quoted) Plain & HTML       	 *       
Netscape Messenger (4.7) Forward (attachment) Plain 	   *     *	 
Netscape Messenger (4.7) Forward (attachment) HTML  	   *	 *
Netscape Messenger (4.7) Forward (attachment) Plain & HTML *  	 *
Outlook Express 6 Forward HTML (Base64)                          *
Outlook Express 6 Forward HTML (None)                            *
Outlook Express 6 Forward HTML (QP)                              *
Outlook Express 6 Forward Plain (Base64)                         *
Outlook Express 6 Forward Plain (None)                           *
Outlook Express 6 Forward Plain (QP)                             *
Outlook Express 6 Forward Plain (uuencoded)                      *
http://www.endymion.com/products/mailman Forward	             *
M2 (Opera Mailer 7.01) Forward                                   *
M2 (Opera Mailer 7.01) Redirect                            *     *
The Bat! 1.62i Forward (RFC Headers not visible)                 *
The Bat! 1.62i Forward (RFC Headers visible)               *     *
The Bat! 1.62i Redirect                                          *
The Bat! 1.62i Alternative Forward                         *     *
The Bat! 1.62i Custom Template                             *     *
AllegroMail 2.5.0.2 Forward                                      *
AllegroMail 2.5.0.2 Redirect                                     *
PocoMail 2.6.3 Bounce                                            *
PocoMail 2.6.3 Bounce                                            *
Pegasus Mail 4.02 Forward (all headers option set)         *     *
Pegasus Mail 4.02 Forward (all headers option not set)           *
Calypso 3 Forward                                                *
Calypso 3 Redirect                                         *     *
Becky! 2.05.10 Forward                                           *
Becky! 2.05.10 Redirect                                          *
Becky! 2.05.10 Redirect as attachment                      *     *
Mozilla Mail 1.2.1 Forward (attachment)                    *     *
Mozilla Mail 1.2.1 Forward (inline, plain)                 *1    *
Mozilla Mail 1.2.1 Forward (inline, plain & html)          *1    *
Mozilla Mail 1.2.1 Forward (inline, html)                  *1    *

*1 The header method will only work if auto-include original message
is set, and if view all headers is true.
"""

from spambayes import Dibbler
from spambayes.tokenizer import get_message, textparts
from spambayes.tokenizer import try_to_repair_damaged_base64
from spambayes.Options import options
from pop3proxy import _addressPortStr, ServerLineReader
from pop3proxy import _addressAndPort, proxyListeners
import string, re
import socket, asyncore, asynchat

class SMTPProxyBase(Dibbler.BrighterAsyncChat):
    """An async dispatcher that understands SMTP and proxies to a SMTP
    server, calling `self.onTransaction(command, args)` for each
    transaction.  self.onTransaction() should
    return the command to pass to the proxied server - the command
    can be the verbatim command or a processed version of it.  The
    special command 'KILL' kills it (passing a 'QUIT' command to the
    server).
    """

    def __init__(self, clientSocket, serverName, serverPort):
        Dibbler.BrighterAsyncChat.__init__(self, clientSocket)
        self.request = ''
        self.set_terminator('\r\n')
        self.command = ''           # The SMTP command being processed...
        self.args = ''              # ...and its arguments
        self.isClosing = False      # Has the server closed the socket?
        self.inData = False
        self.data = ""
        self.blockData = False
        self.serverSocket = ServerLineReader(serverName, serverPort,
                                             self.onServerLine)

    def onTransaction(self, command, args):
        """Overide this.  Takes the raw command and
        returns the (possibly processed) command to pass to the
        email client.
        """
        raise NotImplementedError

    def onProcessData(self, data):
        """Overide this.  Takes the raw data and
        returns the (possibly processed) data to pass back to the
        email client.
        """
        raise NotImplementedError

    def onServerLine(self, line):
        """A line of response has been received from the SMTP server."""
        # Has the server closed its end of the socket?
        if not line:
            self.isClosing = True

        # We don't process the return, just echo the response.
        self.push(line)
        self.onResponse()

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

        if self.request.strip() == '':
            # Someone just hit the Enter key.
            self.command = self.args = ''
        else:
            # A proper command.
            # some commands (MAIL FROM and RCPT TO) split on ':'
            # others (HELO, RSET, ...) split on ' '
            # is there a nicer way of doing this?
            if self.request[:10].upper() == "MAIL FROM:":
                splitCommand = self.request.strip().split(":", 1)
            elif self.request[:8].upper() == "RCPT TO:":
                splitCommand = self.request.strip().split(":", 1)
            else:
                splitCommand = self.request.strip().split(None, 1)
            self.command = splitCommand[0].upper()
            self.args = splitCommand[1:]

        if self.inData == True:
            self.data += self.request + '\r\n'
            if self.request == ".":
                self.inData = False
                cooked = self.onProcessData(self.data)
                self.data = ""
                if self.blockData == False:
                    self.serverSocket.push(cooked + '\r\n')
                else:
                    self.push("250 OK\r\n")
        else:
            cooked = self.onTransaction(self.command, self.args)
            if cooked is not None:
                self.serverSocket.push(cooked + '\r\n')
        self.command = self.args = self.request = ''

    def onResponse(self):
        # If onServerLine() decided that the server has closed its
        # socket, close this one when the response has been sent.
        if self.isClosing:
            self.close_when_done()

        # Reset.
        self.command = ''
        self.args = ''
        self.isClosing = False


class BayesSMTPProxyListener(Dibbler.Listener):
    """Listens for incoming email client connections and spins off
    BayesSMTPProxy objects to serve them.
    """

    def __init__(self, serverName, serverPort, proxyPort, state):
        proxyArgs = (serverName, serverPort, state)
        Dibbler.Listener.__init__(self, proxyPort, BayesSMTPProxy, proxyArgs)
        print 'SMTP Listener on port %s is proxying %s:%d' % \
               (_addressPortStr(proxyPort), serverName, serverPort)


class BayesSMTPProxy(SMTPProxyBase):
    """Proxies between an email client and a SMTP server, inserting
    judgement headers.  It acts on the following SMTP commands:

     o HELO:
     o MAIL FROM:
     o RSET:
     o QUIT:
        o These all just forward the verbatim command to the proxied
          server for processing.
     
    o RCPT TO:
        o Checks if the recipient address matches the key ham, spam
          or shutdown addresses, and if so notes this and does not
          forward a command to the proxied server.  In all other cases
          simply passes on the verbatim command.

     o DATA:
        o Notes that we are in the data section.  If (from the RCPT TO
          information) we are receiving a ham/spam message to train on,
          then do not forward the command on.  Otherwise forward
          verbatim.
    """

    def __init__(self, clientSocket, serverName, serverPort, state):
        SMTPProxyBase.__init__(self, clientSocket, serverName, serverPort)
        self.handlers = {'HELO': self.onHelo, 'RCPT TO': self.onRcptTo,
                         'MAIL FROM': self.onMailFrom, 'RSET': self.onRset,
                         'QUIT': self.onQuit, 'DATA': self.onData}
        self.state = state
        self.state.totalSessions += 1
        self.state.activeSessions += 1
        self.isClosed = False
        self.train_as_ham = False
        self.train_as_spam = False

    def send(self, data):
        try:
            return SMTPProxyBase.send(self, data)
        except socket.error:
            # The email client has closed the connection - 40tude Dialog
            # does this immediately after issuing a QUIT command,
            # without waiting for the response.
            self.close()

    def recv(self, size):
        data = SMTPProxyBase.recv(self, size)
        return data

    def close(self):
        # This can be called multiple times by async.
        if not self.isClosed:
            self.isClosed = True
            self.state.activeSessions -= 1
            SMTPProxyBase.close(self)

    def stripAddress(self, address):
        """
        Strip the leading & trailing <> from an address.  Handy for
        getting FROM: addresses.
        """
        start = string.index(address, '<') + 1
        end = string.index(address, '>')
        return address[start:end]

    def splitTo(self, address):
        """
        Return 'address' as undressed (host, fulladdress) tuple.
        Handy for use with TO: addresses.
        """
        start = string.index(address, '<') + 1
        sep = string.index(address, '@') + 1
        end = string.index(address, '>')
        return (address[sep:end], address[start:end],)

    def onTransaction(self, command, args):
        handler = self.handlers.get(command, self.onUnknown)
        return handler(command, args)

    def onProcessData(self, data):
        if self.train_as_spam:
            self.train(data, True)
            return ""
        elif self.train_as_ham:
            self.train(data, False)
            return ""
        return data

    def onHelo(self, command, args):
        rv = command
        for arg in args:
            rv += ' ' + arg
        return rv

    def onMailFrom(self, command, args):
        rv = command + ':'
        for arg in args:
            rv += ' ' + arg
        return rv

    def onRcptTo(self, command, args):
        toHost, toFull = self.splitTo(args[0])
        if toFull == options.smtpproxy_shutdown_address:
            self.push("421 Closing on user request\r\n")
            self.socket.shutdown(2)
            self.close()
            raise SystemExit
            return None
        elif toFull == options.smtpproxy_spam_address:
            self.train_as_spam = True
            self.blockData = True
            self.push("250 OK\r\n")
            return None
        elif toFull == options.smtpproxy_ham_address:
            self.train_as_ham = True
            self.blockData = True
            self.push("250 OK\r\n")
            return None
        else:
            self.blockData = False
        rv = command + ':'
        for arg in args:
            rv += ' ' + arg
        return rv
        
    def onData(self, command, args):
        self.inData = True
        if self.train_as_ham == True or self.train_as_spam == True:
            self.push("250 OK\r\n")
            return None
        rv = command
        for arg in args:
            rv += ' ' + arg
        return rv

    def onRset(self, command, args):
        rv = command
        for arg in args:
            rv += ' ' + arg
        return rv

    def onQuit(self, command, args):
        rv = command
        for arg in args:
            rv += ' ' + arg
        return rv

    def onUnknown(self, command, args):
        """Default handler."""
        rv = command
        for arg in args:
            rv += ' ' + arg
        return rv

    def extractSpambayesID(self, data):
        msg = get_message(data)

        # the nicest MUA is one that forwards the header intact
        id = msg.get(options.pop3proxy_mailid_header_name)
        if id is not None:
            return id

        # some MUAs will put it in the body somewhere
        # other MUAs will put it in an attached MIME message
        id = self._find_id_in_text(str(msg))
        if id is not None:
            return id

        # the message might be encoded
        for part in textparts(msg):
            # Decode, or take it as-is if decoding fails.
            try:
                text = part.get_payload(decode=True)
            except:
                text = part.get_payload(decode=False)
                if text is not None:
                    text = try_to_repair_damaged_base64(text)
            if text is not None:
                id = self._find_id_in_text(text)
                return id
        return None

    def _find_id_in_text(self, text):
        id_location = text.find(options.pop3proxy_mailid_header_name)
        if id_location == -1:
            return None
        else:
            # A MUA might enclose the id in a table
            # (Mozilla Mail does this with inline html)
            s = re.compile(options.pop3proxy_mailid_header_name + \
                           ':[\s]*</th>[\s]*<td>[\s]*')
            if s.search(text[id_location:]) is not None:
                id_location += s.search(text[id_location:]).end()
                s = re.compile('[\d-]+</td>')
                id_end = s.search(text[id_location:]).end() + id_location
            else:
                id_location += len(options.pop3proxy_mailid_header_name) + 2
                s = re.compile('[\w -]+[\\r]?\\n')
                id_end = s.search(text[id_location:]).end() + id_location
            id = text[id_location:id_end]
            s = re.compile('</td>')
            if s.search(id) is not None:
                id = s.split(id)[0]
            s = re.compile('[\\r]?\\n')
            if s.search(id) is not None:
                id = s.split(id)[0]
            return id

    def train(self, msg, isSpam):
        id = self.extractSpambayesID(msg)
        if id is None:
            print "Could not extract id"
            return
        if options.verbose:
            if isSpam == True:
                print "Training %s as spam" % id
            else:
                print "Training %s as ham" % id
        if self.state.unknownCorpus.get(id) is not None:
            sourceCorpus = self.state.unknownCorpus
        elif self.state.hamCorpus.get(id) is not None:
            sourceCorpus = self.state.hamCorpus
        elif self.state.spamCorpus.get(id) is not None:
            sourceCorpus = self.state.spamCorpus
        else:
            # message doesn't exist in any corpus
            print "Non-existant message"
            return
        if isSpam == True:
            targetCorpus = self.state.spamCorpus
        else:
            targetCorpus = self.state.hamCorpus
        targetCorpus.takeMessage(id, sourceCorpus)
        self.state.bayes.store()

def LoadServerInfo():
    # Load the proxy settings
    servers = []
    proxyPorts = []
    if options.smtpproxy_servers:
        for server in options.smtpproxy_servers.split(','):
            server = server.strip()
            if server.find(':') > -1:
                server, port = server.split(':', 1)
            else:
                port = '25'
            servers.append((server, int(port)))
    if options.smtpproxy_ports:
        splitPorts = options.smtpproxy_ports.split(',')
        proxyPorts = map(_addressAndPort, splitPorts)
    if len(servers) != len(proxyPorts):
        print "smtpproxy_servers & smtpproxy_ports are different lengths!"
        sys.exit()
    return servers, proxyPorts    

def CreateProxies(servers, proxyPorts, state):
    """Create BayesSMTPProxyListeners for all the given servers."""
    for (server, serverPort), proxyPort in zip(servers, proxyPorts):
        listener = BayesSMTPProxyListener(server, serverPort, proxyPort, state)
        proxyListeners.append(listener)

def main():
    """Runs the proxy forever or until a 'KILL' command is received or
    someone hits Ctrl+Break."""
    from pop3proxy import state
    servers, proxyPorts = LoadServerInfo()
    CreateProxies(servers, proxyPorts, state)
    Dibbler.run()

if __name__ == '__main__':
    main()
    