# Test sb_imapfilter script.

# At the moment, the script needs to be provided with an IMAP server to
# use for the testing.  It would be nice if we provided a dummy server
# like test_sb-server.py does for POP, but this will do for the moment.

import sys
import time
import types
import socket
import thread
import imaplib
import unittest
import asyncore

import sb_test_support
sb_test_support.fix_sys_path()

from spambayes import Dibbler
from spambayes.Options import options
from sb_imapfilter import BadIMAPResponseError
from sb_imapfilter import IMAPSession, IMAPMessage, IMAPFolder

IMAP_PORT = 8143
IMAP_USERNAME = "testu"
IMAP_PASSWORD = "testp"
IMAP_FOLDER_LIST = ["INBOX", "unsure", "ham_to_train", "spam"]
# Key is UID.
IMAP_MESSAGES = {101 : """Subject: Test\r\n\r\nBody test.""",
                 102 : """Subject: Test2\r\n\r\nAnother body test."""}
# Map of ID -> UID
IMAP_UIDS = {1 : 101, 2: 102}

class TestListener(Dibbler.Listener):
    """Listener for TestIMAP4Server.  Works on port 8143, to co-exist
    with real IMAP4 servers."""
    def __init__(self, socketMap=asyncore.socket_map):
        Dibbler.Listener.__init__(self, IMAP_PORT, TestIMAP4Server,
                                  (socketMap,), socketMap=socketMap)


class TestIMAP4Server(Dibbler.BrighterAsyncChat):
    """Minimal IMAP4 server, for testing purposes.  Accepts a limited
    subset of commands, and also a KILL command, to terminate."""
    def __init__(self, clientSocket, socketMap):
        # Grumble: asynchat.__init__ doesn't take a 'map' argument,
        # hence the two-stage construction.
        Dibbler.BrighterAsyncChat.__init__(self)
        Dibbler.BrighterAsyncChat.set_socket(self, clientSocket, socketMap)
        self.set_terminator('\r\n')
        # okCommands are just ignored (we pass back a happy this-was-fine
        # answer, and do nothing.
        self.okCommands = ['NOOP', 'LOGOUT', 'CAPABILITY', 'KILL']
        # These commands actually result in something.
        self.handlers = {'LIST' : self.onList,
                         'LOGIN' : self.onLogin,
                         'SELECT' : self.onSelect,
                         'FETCH' : self.onFetch,
                         'UID' : self.onUID,
                         }
        self.push("* OK [CAPABILITY IMAP4REV1 AUTH=LOGIN] " \
                  "localhost IMAP4rev1\r\n")
        self.request = ''

    def collect_incoming_data(self, data):
        """Asynchat override."""
        self.request = self.request + data

    def found_terminator(self):
        """Asynchat override."""
        id, command = self.request.split(None, 1)
        if ' ' in command:
            command, args = command.split(None, 1)
        else:
            args = ''
        command = command.upper()
        if command in self.okCommands:
            self.push("%s OK (we hope)\r\n" % (id,))
            if command == 'LOGOUT':
                self.close_when_done()
            if command == 'KILL':
                self.socket.shutdown(2)
                self.close()
                raise SystemExit()
        else:
            handler = self.handlers.get(command, self.onUnknown)
            self.push(handler(id, command, args, False))  # Or push_slowly for testing
        self.request = ''

    def push_slowly(self, response):
        """Useful for testing."""
        for c in response:
            self.push(c)
            time.sleep(0.02)

    def onLogin(self, id, command, args, uid=False):
        """Log in to server."""
        username, password = args.split(None, 1)
        username = username.strip('"')
        password = password.strip('"')
        if username == IMAP_USERNAME and password == IMAP_PASSWORD:
            return "%s OK [CAPABILITY IMAP4REV1] User %s " \
                   "authenticated.\r\n" % (id, username)
        return "%s NO LOGIN failed\r\n" % (id,)

    def onList(self, id, command, args, uid=False):
        """Return list of folders."""
        base = '\r\n* LIST (\\NoInferiors \\UnMarked) "/" '
        return "%s%s\r\n%s OK LIST completed\r\n" % \
               (base[2:], base.join(IMAP_FOLDER_LIST), id)

    def onSelect(self, id, command, args, uid=False):
        exists = "* %d EXISTS" % (len(IMAP_MESSAGES),)
        recent = "* 0 RECENT"
        uidv = "* OK [UIDVALIDITY 1091599302] UID validity status"
        next_uid = "* OK [UIDNEXT 23] Predicted next UID"
        flags = "* FLAGS (\Answered \Flagged \Deleted \Draft \Seen)"
        perm_flags = "* OK [PERMANENTFLAGS (\* \Answered \Flagged " \
                     "\Deleted \Draft \Seen)] Permanent flags"
        complete = "%s OK [READ-WRITE] SELECT completed" % (id,)
        return "%s\r\n" % ("\r\n".join([exists, recent, uidv, next_uid,
                                        flags, perm_flags, complete]),)

    def onFetch(self, id, command, args, uid=False):
        msg_nums, msg_parts = args.split(None, 1)
        msg_nums = msg_nums.split()
        response = {}
        for msg in msg_nums:
            response[msg] = []
        if "UID" in msg_parts:
            if uid:
                for msg in msg_nums:
                    response[msg].append("FETCH (UID %s)" % (msg,))
            else:
                for msg in msg_nums:
                    response[msg].append("FETCH (UID %s)" %
                                         (IMAP_UIDS[int(msg)]))
        if "BODY.PEEK[]" in msg_parts:
            for msg in msg_nums:
                if uid:
                    msg_uid = int(msg)
                else:
                    msg_uid = IMAP_UIDS[int(msg)]
                response[msg].append(("FETCH (BODY[] {%s}" %
                                     (len(IMAP_MESSAGES[msg_uid])),
                                     IMAP_MESSAGES[msg_uid]))
        for msg in msg_nums:
            try:
                simple = " ".join(response[msg])
            except TypeError:
                simple = []
                for part in response[msg]:
                    if isinstance(part, types.StringTypes):
                        simple.append(part)
                    else:
                        simple.append('%s\r\n%s)' % (part[0], part[1]))
                simple = " ".join(simple)
            response[msg] = "* %s %s" % (msg, simple)
        response_text = "\r\n".join(response.values())
        return "%s\r\n%s OK FETCH completed\r\n" % (response_text, id)

    def onUID(self, id, command, args, uid=False):
        actual_command, args = args.split(None, 1)
        handler = self.handlers.get(actual_command, self.onUnknown)
        return handler(id, command, args, uid=True)

    def onUnknown(self, id, command, args, uid=False):
        """Unknown IMAP4 command."""
        return "%s BAD Command unrecognised: %s\r\n" % (id, repr(command))


class BaseIMAPFilterTest(unittest.TestCase):
    def setUp(self):
        self.imap = IMAPSession("localhost", IMAP_PORT)

    def tearDown(self):
        try:
            self.imap.logout()
        except imaplib.error:
            pass


class IMAPSessionTest(BaseIMAPFilterTest):
    def testGoodLogin(self):
        self.imap.login(IMAP_USERNAME, IMAP_PASSWORD)
        self.assert_(self.imap.logged_in)

    def testBadLogin(self):
        self.assertRaises(SystemExit, self.imap.login, IMAP_USERNAME,
                          "wrong password")

    def test_check_response(self):
        test_data = "IMAP response data"
        response = ("OK", test_data)
        data = self.imap.check_response("", response)
        self.assertEqual(data, test_data)
        response = ("NO", test_data)
        self.assertRaises(BadIMAPResponseError, self.imap.check_response,
                          "", response)

    def testSelectFolder(self):
        # This test will fail if testGoodLogin fails.
        self.imap.login(IMAP_USERNAME, IMAP_PASSWORD)
        
        # Check handling of Python (not SpamBayes) bug #845560.
        self.assertRaises(BadIMAPResponseError, self.imap.SelectFolder, "")

        # Check selection.
        self.imap.SelectFolder("Inbox")
        response = self.imap.response('OK')
        self.assert_(response[0] == "OK")
        self.assert_(response[1] != [None])

        # Check that we don't reselect if we are already in that folder.
        self.imap.SelectFolder("Inbox")
        response = self.imap.response('OK')
        self.assert_(response[0] == "OK")
        self.assert_(response[1] == [None])

    def test_folder_list(self):
        # This test will fail if testGoodLogin fails.
        self.imap.login(IMAP_USERNAME, IMAP_PASSWORD)
        
        # If we had more control over what the IMAP server returned
        # (say we had our own one, as suggested above), then we could
        # test returning literals, getting an error, and a bad literal,
        # but since we don't, just do a simple test for now.

        folders = self.imap.folder_list()
        correct = IMAP_FOLDER_LIST[:]
        correct.sort()
        self.assertEqual(folders, correct)

    def test_extract_fetch_data(self):
        response = "bad response"
        self.assertRaises(BadIMAPResponseError,
                          self.imap.extract_fetch_data, response)

        # Check UID and message_number.
        message_number = "123"
        uid = "5432"
        response = "%s (UID %s)" % (message_number, uid)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["message_number"], message_number)
        self.assertEqual(data["UID"], uid)

        # Check INTERNALDATE, FLAGS.
        flags = r"(\Seen \Deleted)"
        date = '"27-Jul-2004 13:11:56 +1200"'
        response = "%s (FLAGS %s INTERNALDATE %s)" % \
                   (message_number, flags, date)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["FLAGS"], flags)
        self.assertEqual(data["INTERNALDATE"], date)

        # Check RFC822 and literals.
        rfc = "Subject: Test\r\n\r\nThis is a test message."
        response = ("%s (RFC822 {%s}" % (message_number, len(rfc)), rfc)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["message_number"], message_number)
        self.assertEqual(data["RFC822"], rfc)

        # Check RFC822.HEADER.
        headers = "Subject: Foo\r\nX-SpamBayes-ID: 1231-1\r\n"
        response = ("%s (RFC822.HEADER {%s}" % (message_number,
                                                len(headers)), headers)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["RFC822.HEADER"], headers)

        # Check BODY.PEEK.
        peek = "Subject: Test2\r\n\r\nThis is another test message."
        response = ("%s (BODY[] {%s}" % (message_number, len(peek)),
                    peek)
        data = self.imap.extract_fetch_data(response)
        self.assertEqual(data["BODY[]"], peek)


class IMAPMessageTest(BaseIMAPFilterTest):
    def setUp(self):
        BaseIMAPFilterTest.setUp(self)
        self.msg = IMAPMessage()
        self.msg.imap_server = self.imap

    # These tests might fail if more than one second passes
    # between the call and the assert.  We could make it more robust,
    # or you could just run this on a faster machine, like me <wink>.
    def test_extract_time_no_date(self):
        date = self.msg.extractTime()
        self.assertEqual(date, imaplib.Time2Internaldate(time.time()))
    def test_extract_time_date(self):
        self.msg["Date"] = "Wed, 19 May 2004 20:05:15 +1200"
        date = self.msg.extractTime()
        self.assertEqual(date, '"19-May-2004 20:05:15 +1200"')
    def test_extract_time_bad_date(self):
        self.msg["Date"] = "Mon, 06 May 0102 10:51:16 -0100"
        date = self.msg.extractTime()
        self.assertEqual(date, imaplib.Time2Internaldate(time.time()))

    def test_as_string_invalid(self):
        content = "This is example content.\nThis is more\r\n"
        self.msg.invalid = True
        self.msg.invalid_content = content
        as_string = self.msg.as_string()
        self.assertEqual(self.msg._force_CRLF(content), as_string)

    def testMoveTo(self):
        fol1 = "Folder1"
        fol2 = "Folder2"
        self.msg.MoveTo(fol1)
        self.assertEqual(self.msg.folder, fol1)
        self.msg.MoveTo(fol2)
        self.assertEqual(self.msg.previous_folder, fol1)
        self.assertEqual(self.msg.folder, fol2)

    def test_get_full_message(self):
        self.assertRaises(AssertionError, self.msg.get_full_message)
        self.msg.id = "unittest"
        self.assertRaises(AttributeError, self.msg.get_full_message)

        self.msg.imap_server.login(IMAP_USERNAME, IMAP_PASSWORD)
        self.msg.imap_server.select()
        response = self.msg.imap_server.fetch(1, "UID")
        self.assertEqual(response[0], "OK")
        self.msg.uid = response[1][0][7:-1]
        self.msg.folder = IMAPFolder("Inbox", self.msg.imap_server)

        # When we have a dummy server, check for MemoryError here.
        # And also an unparseable message (for Python < 2.4).

        new_msg = self.msg.get_full_message()
        self.assertEqual(new_msg.folder, self.msg.folder)
        self.assertEqual(new_msg.previous_folder, self.msg.previous_folder)
        self.assertEqual(new_msg.uid, self.msg.uid)
        self.assertEqual(new_msg.id, self.msg.id)
        self.assertEqual(new_msg.rfc822_key, self.msg.rfc822_key)
        self.assertEqual(new_msg.rfc822_command, self.msg.rfc822_command)
        self.assertEqual(new_msg.imap_server, self.msg.imap_server)
        id_header = options["Headers", "mailid_header_name"]
        self.assertEqual(new_msg[id_header], self.msg.id)

        new_msg2 = new_msg.get_full_message()
        # These should be the same object, not just equal.
        self.assert_(new_msg is new_msg2)


def suite():
    suite = unittest.TestSuite()
    for cls in (IMAPSessionTest,
                IMAPMessageTest,
               ):
        suite.addTest(unittest.makeSuite(cls))
    return suite

if __name__=='__main__':
    def runTestServer():
        TestListener()
        asyncore.loop()
    thread.start_new_thread(runTestServer, ())
    sb_test_support.unittest_main(argv=sys.argv + ['suite'])
