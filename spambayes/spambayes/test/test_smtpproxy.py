#! /usr/bin/env python

"""Test that the SMTP proxy is working correctly.

When using the -z command line option, carries out various tests.

The -t option runs a fake SMTP server on port 8025.  This is the
same server that the testing option uses, and may be separately run for
other testing purposes.

Usage:

    test_smtpproxy.py [options]

        options:
            -t      : Runs a fake SMTP server on port 8025 (for testing).
            -h      : Displays this help message.

Any other options runs this in the standard Python unittest form.
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
__credits__ = "Richie Hindle, Mark Hammond, all the SpamBayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

# One example of spam and one of ham - both are used to train, and are
# then classified.  Not a good test of the classifier, but a perfectly
# good test of the SMTP proxy.  These are the same messages as in the
# POP3 proxy test (test_sb-server.py).

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

import re
import socket
import getopt
import asyncore
import operator
import unittest
import threading
import smtplib

# We need to import sb_server, but it may not be on the PYTHONPATH.
# Hack around this, so that if we are running in a cvs-like setup
# everything still works.
import os
import sys
try:
    this_file = __file__
except NameError:
    this_file = sys.argv[0]
sb_dir = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(this_file))))
if sb_dir not in sys.path:
    sys.path.append(sb_dir)
    sys.path.append(os.path.join(sb_dir, "scripts"))

from spambayes import Dibbler
from spambayes import tokenizer
from spambayes.Options import options
from sb_server import state, _recreateState
from spambayes.smtpproxy import BayesSMTPProxyListener
from spambayes.ProxyUI import ProxyUserInterface
from spambayes.UserInterface import UserInterfaceServer

class TestListener(Dibbler.Listener):
    """Listener for TestPOP3Server.  Works on port 8025, because 8025
    wouldn't work for Tony."""

    def __init__(self, socketMap=asyncore.socket_map):
        Dibbler.Listener.__init__(self, 8025, TestSMTPServer,
                              (socketMap,), socketMap=socketMap)


class TestSMTPServer(Dibbler.BrighterAsyncChat):
    """Minimal SMTP server, for testing purposes.  Understands
    "MAIL FROM", "RCPT TO", "DATA" and "QUIT".  All mail is
    simply discarded. Also understands the 'KILL' command, to
    kill it."""

    def __init__(self, clientSocket, socketMap):
        # Grumble: asynchat.__init__ doesn't take a 'map' argument,
        # hence the two-stage construction.
        Dibbler.BrighterAsyncChat.__init__(self)
        Dibbler.BrighterAsyncChat.set_socket(self, clientSocket, socketMap)
        self.set_terminator('\r\n')
        self.okCommands = ['MAIL FROM:', 'RCPT TO:', 'DATA', 'QUIT', 'KILL',]
        self.handlers = {'MAIL FROM:': self.onFrom,
                         'RCPT TO:': self.onTo,
                         'DATA': self.onData,
                         'QUIT': self.onQuit,
                         'KILL': self.onKill,
                         }
        self.push("220 SpamBayes test SMTP server ready\r\n")
        self.request = ''
        self.inData = False

    def collect_incoming_data(self, data):
        """Asynchat override."""
        self.request = self.request + data
        print "data", data

    def push(self, data):
        print "pushing", repr(data)
        Dibbler.BrighterAsyncChat.push(self, data)
        
    def recv(self, buffer_size):
        """Asynchat override."""
        try:
            return Dibbler.BrighterAsyncChat.recv(self, buffer_size)
        except socket.error, e:
            if e[0] == 10053:
                return ''
            raise

    def found_terminator(self):
        """Asynchat override."""
        if self.inData:
            # Just throw the data away, unless it is the terminator.
            if self.request.strip() == '.':
                self.inData = False
                self.push("250 Message accepted for delivery\r\n")
        else:
            self.request = self.request.upper()
            foundCmd = False
            for cmd in self.okCommands:
                if self.request.startswith(cmd):
                    handler = self.handlers[cmd]
                    cooked = handler(self.request[len(cmd):])
                    if cooked is not None:
                        self.push(cooked.strip())
                    foundCmd = True
                    break
            if not foundCmd:
                # Something we don't know about.  Assume that it is ok!
                self.push("250 Unknown command ok.\r\n")
        self.request = ''

    def onKill(self, args):
        self.push("221 Goodbye\n") # Why not be polite <wink>
        self.socket.shutdown(2)
        self.close()
        raise SystemExit

    def onQuit(self, args):
        self.push("221 Goodbye\r\n")
        self.close_when_done()

    def onFrom(self, args):
        # We don't care who it is from.
        return "250 %s... Sender ok\r\n" % (args.lower(),)

    def onTo(self, args):
        if args == options["smtpproxy", "ham_address"].upper():
            return "504 This command should not have got to the server\r\n"
        elif args == options["smtpproxy", "spam_address"].upper():
            return "504 This command should not have got to the server\r\n"
        return "250 %s... Recipient ok\r\n" % (args.lower(),)
    def onData(self, args):
        self.inData = True
        return '354 Enter mail, end with "." on a line by itself\r\n'


class SMTPProxyTest(unittest.TestCase):
    """Runs a self-test using TestSMTPServer, a minimal SMTP server
    that receives mail and discards it."""
    def setUp(self):
        # Run a proxy and a test server in separate threads with separate
        # asyncore environments.  Don't bother with the UI.
        state.isTest = True
        testServerReady = threading.Event()
        def runTestServer():
            testSocketMap = {}
            #TestListener(socketMap=testSocketMap)
            testServerReady.set()
            #asyncore.loop(map=testSocketMap)

        proxyReady = threading.Event()
        def runProxy():
            trainer = None
            BayesSMTPProxyListener('localhost', 8025, ('', 8026), trainer)
            proxyReady.set()
            Dibbler.run()

        serverThread = threading.Thread(target=runTestServer)
        serverThread.setDaemon(True)
        serverThread.start()
        testServerReady.wait()
        proxyThread = threading.Thread(target=runProxy)
        proxyThread.setDaemon(True)
        proxyThread.start()
        proxyReady.wait()

    def tearDown(self):
        return
        # Kill the proxy and the test server.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('localhost', 8025))
        s.send("kill\r\n")

    def test_direct_connection(self):
        # Connect to the test server.
        smtpServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        smtpServer.connect(('localhost', 8025))
        try:
            response = smtpServer.recv(100)
        except socket.error, e:
            if e[0] == 10035:
                # non-blocking socket so that the recognition
                # can proceed, so this doesn't mean much
                pass
            else:
                raise
        self.assertEqual(response, "220 SpamBayes test SMTP server ready\r\n",
                         "Couldn't connect to test SMTP server")
        smtpServer.send('quit\r\n')

    def test_proxy_connection(self):
        # Connect to the proxy server.
        proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        proxy.connect(('localhost', 8026))
        try:
            response = proxy.recv(100)
        except socket.error, e:
            if e[0] == 10035:
                # non-blocking socket so that the recognition
                # can proceed, so this doesn't mean much
                pass
            else:
                raise
        self.assertEqual(response, "220 SpamBayes test SMTP server ready\r\n",
                         "Couldn't connect to proxy server")
        proxy.send('quit\r\n')

    def qtest_disconnection(self):
        proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        proxy.connect(('localhost', 8025))
        try:
            response = proxy.recv(100)
        except socket.error, e:
            if e[0] == 10035:
                # non-blocking socket so that the recognition
                # can proceed, so this doesn't mean much
                pass
            else:
                raise
        proxy.send("quit\r\n")
        try:
            response = proxy.recv(100)
        except socket.error, e:
            if e[0] == 10035:
                # non-blocking socket so that the recognition
                # can proceed, so this doesn't mean much
                pass
            else:
                raise
        self.assertEqual(response, "221 Goodbye\r\n",
                         "Couldn't disconnect from SMTP server")

    def test_sendmessage(self):
        try:
            s = smtplib.SMTP('localhost', 8026)
            s.sendmail("ta-meyer@ihug.co.nz", "ta-meyer@ihug.co.nz", good1)
            s.quit()
        except:
            self.fail("Couldn't send a message through.")

def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SMTPProxyTest))
    return suite

def run():
    # Read the arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'htz')
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
        elif opt == '-z':
            state.isTest = True
            runSelfTest = True

    state.createWorkers()

    if state.runTestServer:
        print "Running a test SMTP server on port 8025..."
        TestListener()
        asyncore.loop()
    else:
        state.buildServerStrings()
        unittest.main(argv=sys.argv + ['suite'])

if __name__ == '__main__':
    run()
