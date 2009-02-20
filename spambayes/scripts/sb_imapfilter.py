#!/usr/bin/env python

"""An IMAP filter.  An IMAP message box is scanned and all non-scored
messages are scored and (where necessary) filtered.

Usage:
    sb_imapfilter [options]

        note: option values with spaces in them must be enclosed
              in double quotes

        options:
            -p  dbname  : pickled training database filename
            -d  dbname  : dbm training database filename
            -t          : train contents of spam folder and ham folder
            -c          : classify inbox
            -h          : display this message
            -v          : verbose mode
            -P          : security option to prompt for imap password,
                          rather than look in options["imap", "password"]
            -e y/n      : expunge/purge messages on exit (y) or not (n)
            -i debuglvl : a somewhat mysterious imaplib debugging level
                          (4 is a good level, and suitable for bug reports)
            -l minutes  : period of time between filtering operations
            -b          : Launch a web browser showing the user interface.
            -o section:option:value :
                          set [section, option] in the options database
                          to value

Examples:

    Classify inbox, with dbm database
        sb_imapfilter -c -d bayes.db

    Train Spam and Ham, then classify inbox, with dbm database
        sb_imapfilter -t -c -d bayes.db

    Train Spam and Ham only, with pickled database
        sb_imapfilter -t -p bayes.db

Warnings:
    o We never delete mail, unless you use the -e/purge option, but we do
      mark a lot as deleted, and your mail client might remove that for
      you.  We try to only mark as deleted once the moved/altered message
      is correctly saved, but things might go wrong.  We *strongly*
      recommend that you try this script out on mail that you can recover
      from somewhere else, at least at first.
"""

from __future__ import generators

todo = """
    o IMAP supports authentication via other methods than the plain-text
      password method that we are using at the moment.  Neither of the
      servers I have access to offer any alternative method, however.  If
      someone's does, then it would be nice to offer this.
      Thanks to #1169939 we now support CRAM_MD5 if available.  It'd still
      be good to support others, though.
    o Usernames should be able to be literals as well as quoted strings.
      This might help if the username/password has special characters like
      accented characters.
    o Suggestions?
"""

# This module is part of the SpamBayes project, which is Copyright 2002-2007
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>, Tim Stone"
__credits__ = "All the SpamBayes folk. The original filter design owed " \
              "much to isbg by Roger Binns (http://www.rogerbinns.com/isbg)."

# If we are running as a frozen application, then chances are that
# output is just lost.  We'd rather log this, like sb_server and Oulook
# log, so that the user can pull up the output if possible.  We could just
# rely on the user piping the output appropriately, but would rather have
# more control.  The sb_server tray application only does this if not
# running in a console window, but we do it whenever we are frozen.
import os
import sys
if hasattr(sys, "frozen"):
    # We want to move to logging module later, so for now, we
    # hack together a simple logging strategy.
    try:
        import win32api
    except ImportError:
        if sys.platform == "win32":
            # Fall back to CWD, but warn user.
            status = "Warning: your log is stored in the current " \
                     "working directory.  We recommend installing " \
                     "the pywin32 extensions, so that the log is " \
                     "stored in the Windows temp directory."
            temp_dir = os.getcwd()
        else:
            # Try for a /tmp directory.
            if os.path.isdir("/tmp"):
                temp_dir = "/tmp"
                status = "Log file opened in /tmp"
            else:
                status = "Warning: your log is stored in the current " \
                         "working directory.  If this does not suit you " \
                         "please let the spambayes@python.org crowd know " \
                         "so that an alternative can be arranged."
    else:
        temp_dir = win32api.GetTempPath()
        status = "Log file opened in " + temp_dir
    for i in range(3, 0, -1):
        try:
            os.unlink(os.path.join(temp_dir, "SpamBayesIMAP%d.log" % (i+1)))
        except os.error:
            pass
        try:
            os.rename(
                os.path.join(temp_dir, "SpamBayesIMAP%d.log" % i),
                os.path.join(temp_dir, "SpamBayesIMAP%d.log" % (i+1))
                )
        except os.error:
            pass
    # Open this log, as unbuffered, so crashes still get written.
    sys.stdout = open(os.path.join(temp_dir,"SpamBayesIMAP1.log"), "wt", 0)
    sys.stderr = sys.stdout

import socket
import re
import time
import getopt
import types
import thread
import email
import email.Parser
from getpass import getpass
from email.Utils import parsedate

from spambayes import Stats
from spambayes import message
from spambayes.Options import options, optionsPathname
from spambayes import storage, Dibbler
from spambayes.UserInterface import UserInterfaceServer
from spambayes.ImapUI import IMAPUserInterface, LoginFailure

from spambayes.Version import get_current_version

from imaplib import IMAP4
from imaplib import Time2Internaldate
try:
    if options["imap", "use_ssl"]:
        from imaplib import IMAP4_SSL as BaseIMAP
    else:
        from imaplib import IMAP4 as BaseIMAP
except ImportError:
    from imaplib import IMAP4 as BaseIMAP


class BadIMAPResponseError(Exception):
    """An IMAP command returned a non-"OK" response."""
    def __init__(self, command, response):
        self.command = command
        self.response = response
    def __str__(self):
        return "The command '%s' failed to give an OK response.\n%s" % \
               (self.command, self.response)


class IMAPSession(BaseIMAP):
    '''A class extending the IMAP4 class, with a few optimizations'''

    timeout = 60 # seconds
    def __init__(self, server, debug=0, do_expunge = options["imap", "expunge"] ):
        if ":" in server:
            server, port = server.split(':', 1)
            port = int(port)
        else:
            if options["imap", "use_ssl"]:
                port = 993
            else:
                port = 143

        # There's a tricky situation where if use_ssl is False, but we
        # try to connect to a IMAP over SSL server, we will just hang
        # forever, waiting for a response that will never come.  To
        # get past this, just for the welcome message, we install a
        # timeout on the connection.  Normal service is then returned.
        # This only applies when we are not using SSL.
        if not hasattr(self, "ssl"):
            readline = self.readline
            self.readline = self.readline_timeout
        try:
            BaseIMAP.__init__(self, server, port)
        except (BaseIMAP.error, socket.gaierror, socket.error):
            if options["globals", "verbose"]:
                print >> sys.stderr, "Cannot connect to server", server, "on port", port
                if not hasattr(self, "ssl"):
                    print >> sys.stderr, ("If you are connecting to an SSL server,"
                                          "please ensure that you\n"
                                          "have the 'Use SSL' option enabled.")
            self.connected = False
        else:
            self.connected = True
        if not hasattr(self, "ssl"):
            self.readline = readline
        self.debug = debug
        self.do_expunge = do_expunge
        self.server = server
        self.port = port
        self.logged_in = False

        # For efficiency, we remember which folder we are currently
        # in, and only send a select command to the IMAP server if
        # we want to *change* folders.  This functionality is used by
        # both IMAPMessage and IMAPFolder.
        self.current_folder = None

        # We override the base read so that we only read a certain amount
        # of data at a time.  OS X and Python has problems with getting 
        # large amounts of memory at a time, so maybe this will be a way we
        # can work around that (I don't know, and don't have a mac to test,
        # but we need to try something).
        self._read = self.read
        self.read = self.safe_read

    def readline_timeout(self):
        """Read line from remote, possibly timing out."""
        st_time = time.time()
        self.sock.setblocking(False)
        buffer = []
        while True:
            if (time.time() - st_time) > self.timeout:
                if options["globals", "verbose"]:
                    print >> sys.stderr, "IMAP Timing out"
                break
            try:
                data = self.sock.recv(1)
            except socket.error, e:
                if e[0] == 10035:
                    # Nothing to receive, keep going.
                    continue
                raise
            if not data:
                break
            if data == '\n':
                break
            buffer.append(data)
        self.sock.setblocking(True)
        return "".join(buffer)

    def login(self, username, pwd):
        """Log in to the IMAP server, catching invalid username/password."""
        assert self.connected, "Must be connected before logging in."
        if 'AUTH=CRAM-MD5' in self.capabilities:
            login_func = self.login_cram_md5
            args = (username, pwd)
            description = "MD5"
        else:
            login_func = BaseIMAP.login # superclass login
            args = (self, username, pwd)
            description = "plain-text"
        try:
            login_func(*args)
        except BaseIMAP.error, e:
            msg = "The username (%s) and/or password (sent in %s) may " \
                  "be incorrect." % (username, description)
            raise LoginFailure(msg)
        self.logged_in = True

    def logout(self):
        """Log off from the IMAP server, possibly expunging.

        Note that most, if not all, of the expunging is probably done in
        SelectFolder, rather than here, for purposes of speed."""
        # We may never have logged in, in which case we do nothing.
        if self.connected and self.logged_in and self.do_expunge:
            # Expunge messages from the ham, spam and unsure folders.
            for fol in ["spam_folder",
                        "unsure_folder",
                        "ham_folder"]:
                folder_name = options["imap", fol]
                if folder_name:
                    self.select(folder_name)
                    self.expunge()
            # Expunge messages from the ham and spam training folders.
            for fol_list in ["ham_train_folders",
                             "spam_train_folders",]:
                for fol in options["imap", fol_list]:
                    self.select(fol)
                    self.expunge()
        BaseIMAP.logout(self)  # superclass logout

    def check_response(self, command, IMAP_response):
        """A utility function to check the response from IMAP commands.

        Raises BadIMAPResponseError if the response is not OK.  Returns
        the data segment of the response otherwise."""
        response, data = IMAP_response
        if response != "OK":
            raise BadIMAPResponseError(command, IMAP_response)
        return data

    def SelectFolder(self, folder):
        """A method to point ensuing IMAP operations at a target folder.

        This is essentially a wrapper around the IMAP select command, which
        ignores the command if the folder is already selected."""
        if self.current_folder != folder:
            if self.current_folder != None and self.do_expunge:
                # It is faster to do close() than a single
                # expunge when we log out (because expunge returns
                # a list of all the deleted messages which we don't do
                # anything with).
                self.close()
                self.current_folder = None

            if folder == "":
                # This is Python bug #845560 - if the empty string is
                # passed, we get a traceback, not just an 'invalid folder'
                # error, so raise our own error.
                raise BadIMAPResponseError("select",
                                           "Cannot have empty string as "
                                           "folder name in select")

            # We *always* use SELECT and not EXAMINE, because this
            # speeds things up considerably.
            response = self.select(folder, None)
            data = self.check_response("select %s" % (folder,), response)
            self.current_folder = folder
            return data

    number_re = re.compile(r"{\d+}")
    folder_re = re.compile(r"\(([\w\\ ]*)\) ")
    def folder_list(self):
        """Return a alphabetical list of all folders available on the
        server."""
        response = self.list()
        try:
            all_folders = self.check_response("list", response)
        except BadIMAPResponseError:
            # We want to keep going, so just print out a warning, and
            # return an empty list.
            if options["globals", "verbose"]:
                print >> sys.stderr, "Could not retrieve folder list."
            return []
        folders = []
        for fol in all_folders:
            # Sigh.  Some servers may give us back the folder name as a
            # literal, so we need to crunch this out.
            if isinstance(fol, types.TupleType):
                m = self.number_re.search(fol[0])
                if not m:
                    # Something is wrong here!  Skip this folder.
                    continue
                fol = '%s"%s"' % (fol[0][:m.start()], fol[1])
            m = self.folder_re.search(fol)
            if not m:
                # Something is not good with this folder, so skip it.
                continue
            name_attributes = fol[:m.end()-1]

            # IMAP is a truly odd protocol.  The delimiter is
            # only the delimiter for this particular folder - each
            # folder *may* have a different delimiter
            self.folder_delimiter = fol[m.end()+1:m.end()+2]

            # A bit of a hack, but we really need to know if this is
            # the case.
            if self.folder_delimiter == ',':
                print >> sys.stderr, ("WARNING: Your imap server uses a comma as the "
                                      "folder delimiter.  This may cause unpredictable " \
                                      "errors.")
            folders.append(fol[m.end()+4:].strip('"'))
        folders.sort()
        return folders

    # A flag can have any character in the ascii range 32-126 except for
    # (){ %*"\
    FLAG_CHARS = ""
    for i in range(32, 127):
        if not chr(i) in ['(', ')', '{', ' ', '%', '*', '"', '\\']:
            FLAG_CHARS += chr(i)
    FLAG = r"\\?[" + re.escape(FLAG_CHARS) + r"]+"
    # The empty flag set "()" doesn't match, so that extract_fetch_data()
    # returns data["FLAGS"] == None
    FLAGS_RE = re.compile(r"(FLAGS) (\((" + FLAG + r" )*(" + FLAG + r")\))")
    INTERNALDATE_RE = re.compile(r"(INTERNALDATE) (\"\d{1,2}\-[A-Za-z]{3,3}\-" +
                                 r"\d{2,4} \d{2,2}\:\d{2,2}\:\d{2,2} " +
                                 r"[\+\-]\d{4,4}\")")
    RFC822_RE = re.compile(r"(RFC822) (\{[\d]+\})")
    BODY_PEEK_RE = re.compile(r"(BODY\[\]) (\{[\d]+\})")
    RFC822_HEADER_RE = re.compile(r"(RFC822.HEADER) (\{[\d]+\})")
    UID_RE = re.compile(r"(UID) ([\d]+)")
    UID_RE2 = re.compile(r" *(UID) ([\d]+)\)")
    FETCH_RESPONSE_RE = re.compile(r"([0-9]+) \(([" + \
                                   re.escape(FLAG_CHARS) + r"\"\{\}\(\)\\ ]*)\)?")
    LITERAL_RE = re.compile(r"^\{[\d]+\}$")
    def _extract_fetch_data(self, response):
        """This does the real work of extracting the data, for each message
        number.
        """
        # We support the following FETCH items:
        #  FLAGS
        #  INTERNALDATE
        #  RFC822
        #  UID
        #  RFC822.HEADER
        #  BODY.PEEK
        # All others are ignored.

        if isinstance(response, types.StringTypes):
            response = (response,)

        data = {}
        expected_literal = None
        if self.UID_RE2.match(response[-1]):
            response = response[:-1]
            
        for part in response:
            # We ignore parentheses by themselves, for convenience.
            if part == ')':
                continue
            if expected_literal:
                # This should be a literal of a certain size.
                key, expected_size = expected_literal
##                if len(part) != expected_size:
##                    raise BadIMAPResponseError(\
##                        "FETCH response (wrong size literal %d != %d)" % \
##                        (len(part), expected_size), response)
                data[key] = part
                expected_literal = None
                continue
            # The first item will always be the message number.
            mo = self.FETCH_RESPONSE_RE.match(part)
            if mo:
                data["message_number"] = mo.group(1)
                rest = mo.group(2)
            else:
                raise BadIMAPResponseError("FETCH response", response)
            
            for r in [self.FLAGS_RE, self.INTERNALDATE_RE, self.RFC822_RE,
                      self.UID_RE, self.RFC822_HEADER_RE, self.BODY_PEEK_RE]:
                mo = r.search(rest)
                if mo is not None:
                    if self.LITERAL_RE.match(mo.group(2)):
                        # The next element will be a literal.
                        expected_literal = (mo.group(1),
                                            int(mo.group(2)[1:-1]))
                    else:
                        data[mo.group(1)] = mo.group(2)
        return data

    def extract_fetch_data(self, response):
        """Extract data from the response given to an IMAP FETCH command.

        The data is put into a dictionary, which is returned, where the
        keys are the fetch items.
        """
        # There may be more than one message number in the response, so
        # handle separately.
        if isinstance(response, types.StringTypes):
            response = (response,)

        data = {}
        for msg in response:
            msg_data = self._extract_fetch_data(msg)
            if msg_data:
                # Maybe there are two about the same message number!
                num = msg_data["message_number"]
                if num in data:
                    data[num].update(msg_data)
                else:
                    data[num] = msg_data
        return data

    # Maximum amount of data that will be read at any one time.
    MAXIMUM_SAFE_READ = 4096
    def safe_read(self, size):
        """Read data from remote, but in manageable sizes."""
        data = []
        while size > 0:
            if size < self.MAXIMUM_SAFE_READ:
                to_collect = size
            else:
                to_collect = self.MAXIMUM_SAFE_READ
            data.append(self._read(to_collect))
            size -= self.MAXIMUM_SAFE_READ
        return "".join(data)


class IMAPMessage(message.SBHeaderMessage):
    def __init__(self):
        message.SBHeaderMessage.__init__(self)
        self.folder = None
        self.previous_folder = None
        self.rfc822_command = "(BODY.PEEK[])"
        self.rfc822_key = "BODY[]"
        self.got_substance = False
        self.invalid = False
        self.could_not_retrieve = False
        self.imap_server = None

    def extractTime(self):
        """When we create a new copy of a message, we need to specify
        a timestamp for the message, if we can't get the information
        from the IMAP server itself.  If the message has a valid date
        header we use that.  Otherwise, we use the current time."""
        message_date = self["Date"]
        if message_date is not None:
            parsed_date = parsedate(message_date)
            if parsed_date is not None:
                try:
                    return Time2Internaldate(time.mktime(parsed_date))
                except ValueError:
                    # Invalid dates can cause mktime() to raise a
                    # ValueError, for example:
                    #   >>> time.mktime(parsedate("Mon, 06 May 0102 10:51:16 -0100"))
                    #   Traceback (most recent call last):
                    #     File "<interactive input>", line 1, in ?
                    #   ValueError: year out of range
                    # (Why this person is getting mail from almost two
                    # thousand years ago is another question <wink>).
                    # In any case, we just pass and use the current date.
                    pass
                except OverflowError:
                    pass
        return Time2Internaldate(time.time())

    def get_full_message(self):
        """Retrieve the RFC822 message from the IMAP server and return a
        new IMAPMessage object that has the same details as this message,
        but also has the substance."""
        if self.got_substance:
            return self

        assert self.id, "Cannot get substance of message without an id"
        assert self.uid, "Cannot get substance of message without an UID"
        assert self.imap_server, "Cannot do anything without IMAP connection"

        # First, try to select the folder that the message is in.
        try:
            self.imap_server.SelectFolder(self.folder.name)
        except BadIMAPResponseError:
            # Can't select the folder, so getting the substance will not
            # work.
            self.could_not_retrieve = True
            print >> sys.stderr, "Could not select folder %s for message " \
                  "%s (uid %s)" % (self.folder.name, self.id, self.uid)
            return self

        # Now try to fetch the substance of the message.
        try:
            response = self.imap_server.uid("FETCH", self.uid,
                                            self.rfc822_command)
        except MemoryError:
            # Really big messages can trigger a MemoryError here.
            # The problem seems to be line 311 (Python 2.3) of socket.py,
            # which has "return "".join(buffers)".  This has also caused
            # problems with Mac OS X 10.3, which apparently is very stingy
            # with memory (the malloc calls fail!).  The problem then is
            # line 301 of socket.py which does
            # "data = self._sock.recv(recv_size)".
            # We want to handle this gracefully, although we can't really
            # do what we do later, and rewrite the message, since we can't
            # load it in the first place.  Maybe an elegant solution would
            # be to get the message in parts, or just use the first X
            # characters for classification.  For now, we just carry on,
            # warning the user and ignoring the message.
            self.could_not_retrieve = True
            print >> sys.stderr, "MemoryError with message %s (uid %s)" % \
                  (self.id, self.uid)
            return self

        command = "uid fetch %s" % (self.uid,)
        response_data = self.imap_server.check_response(command, response)
        data = self.imap_server.extract_fetch_data(response_data)
        # The data will be a dictionary - hopefully with only one element,
        # but maybe more than one.  The key is the message number, which we
        # do not have (we use the UID instead).  So we look through the
        # message and use the first data of the right type we find.
        rfc822_data = None
        for msg_data in data.itervalues():
            if self.rfc822_key in msg_data:
                rfc822_data = msg_data[self.rfc822_key]
                break
        if rfc822_data is None:
            raise BadIMAPResponseError("FETCH response", response_data)

        try:
            new_msg = email.message_from_string(rfc822_data, IMAPMessage)
        # We use a general 'except' because the email package doesn't
        # always return email.Errors (it can return a TypeError, for
        # example) if the email is invalid.  In any case, we want
        # to keep going, and not crash, because we might leave the
        # user's mailbox in a bad state if we do.  Better to soldier on.
        except:
            # Yikes!  Barry set this to return at this point, which
            # would work ok for training (IIRC, that's all he's
            # using it for), but for filtering, what happens is that
            # the message ends up blank, but ok, so the original is
            # flagged to be deleted, and a new (almost certainly
            # unsure) message, *with only the spambayes headers* is
            # created.  The nice solution is still to do what sb_server
            # does and have a X-Spambayes-Exception header with the
            # exception data and then the original message.
            self.invalid = True
            text, details = message.insert_exception_header(
                rfc822_data, self.id)
            self.invalid_content = text
            self.got_substance = True

            # Print the exception and a traceback.
            print >> sys.stderr, details

            return self            

        new_msg.folder = self.folder
        new_msg.previous_folder = self.previous_folder
        new_msg.rfc822_command = self.rfc822_command
        new_msg.rfc822_key = self.rfc822_key
        new_msg.imap_server = self.imap_server
        new_msg.uid = self.uid
        new_msg.setId(self.id)
        new_msg.got_substance = True

        if not new_msg.has_key(options["Headers", "mailid_header_name"]):
            new_msg[options["Headers", "mailid_header_name"]] = self.id

        if options["globals", "verbose"]:
            sys.stdout.write(chr(8) + "*")
        return new_msg

    def MoveTo(self, dest):
        '''Note that message should move to another folder.  No move is
        carried out until Save() is called, for efficiency.'''
        if self.previous_folder is None:
            self.previous_folder = self.folder
        self.folder = dest

    def as_string(self, unixfrom=False):
        # Basically the same as the parent class's except that we handle
        # the case where the data was unparsable, so we haven't done any
        # filtering, and we are not actually a proper email.Message object.
        # We also don't mangle the from line; the server must take care of
        # this.
        if self.invalid:
            return self._force_CRLF(self.invalid_content)
        else:
            return message.SBHeaderMessage.as_string(self, unixfrom,
                                                     mangle_from_=False)

    recent_re = re.compile(r"\\Recent ?| ?\\Recent")
    def Save(self):
        """Save message to IMAP server.

        We can't actually update the message with IMAP, so what we do is
        create a new message and delete the old one."""

        assert self.folder is not None, \
               "Can't save a message that doesn't have a folder."
        assert self.id, "Can't save a message that doesn't have an id."
        assert self.imap_server, "Can't do anything without IMAP connection."

        response = self.imap_server.uid("FETCH", self.uid,
                                        "(FLAGS INTERNALDATE)")
        command = "fetch %s (flags internaldate)" % (self.uid,)
        response_data = self.imap_server.check_response(command, response)
        data = self.imap_server.extract_fetch_data(response_data)
        # The data will be a dictionary - hopefully with only one element,
        # but maybe more than one.  The key is the message number, which we
        # do not have (we use the UID instead).  So we look through the
        # message and use the last data of the right type we find.
        msg_time = self.extractTime()
        flags = None
        for msg_data in data.itervalues():
            if "INTERNALDATE" in msg_data:
                msg_time = msg_data["INTERNALDATE"]
            if "FLAGS" in msg_data:
                flags = msg_data["FLAGS"]
                # The \Recent flag can be fetched, but cannot be stored
                # We must remove it from the list if it is there.
                flags = self.recent_re.sub("", flags)
                
        # We try to save with flags and time, then with just the
        # time, then with the flags and the current time, then with just
        # the current time.  The first should work, but the first three
        # sometimes (due to the quirky IMAP server) fail.
        for flgs, tme in [(flags, msg_time),
                          (None, msg_time),
                          (flags, Time2Internaldate(time.time())),
                          (None, Time2Internaldate(time.time()))]:
            try:
                response = self.imap_server.append(self.folder.name, flgs, tme,
                                                   self.as_string())
            except BaseIMAP.error:
                continue
            try:
                self.imap_server.check_response("", response)
            except BadIMAPResponseError:
                pass
            else:
                break
        else:
            command = "append %s %s %s %s" % (self.folder.name, flgs, tme,
                                              self.as_string)
            raise BadIMAPResponseError(command)

        if self.previous_folder is None:
            self.imap_server.SelectFolder(self.folder.name)
        else:
            self.imap_server.SelectFolder(self.previous_folder.name)
            self.previous_folder = None
        response = self.imap_server.uid("STORE", self.uid, "+FLAGS.SILENT",
                                        "(\\Deleted \\Seen)")
        command = "set %s to be deleted and seen" % (self.uid,)
        self.imap_server.check_response(command, response)

        # Not all IMAP servers immediately offer the new message, but
        # we need to find it to get the new UID.  We need to wait until
        # the server offers up an EXISTS command, so we no-op until that
        # is the case.
        # See [ 941596 ] sb_imapfilter.py not adding headers / moving messages
        # We use the recent() function, which no-ops if necessary.  We try
        # 100 times, and then give up.  If a message arrives independantly,
        # and we are told about it before our message, then this could
        # cause trouble, but that would be one weird server.
        for i in xrange(100):
            response = self.imap_server.recent()
            data = self.imap_server.check_response("recent", response)
            if data[0] is not None:
                if options["globals", "verbose"]:
                    print >> sys.stderr, "[imapfilter] found saved message", self.uid,
                    print >> sys.stderr, "in iteration", i
                break
        else:
            if options["globals", "verbose"]:
                print >> sys.stderr, ("[imapfilter] can't find saved message after"
                                      "100 iterations:"), self.uid
            # raise BadIMAPResponseError("recent", "Cannot find saved message")

        # We need to update the UID, as it will have changed.
        # Although we don't use the UID to keep track of messages, we do
        # have to use it for IMAP operations.
        self.imap_server.SelectFolder(self.folder.name)
        search_string = "(UNDELETED HEADER %s \"%s\")" % \
                        (options["Headers", "mailid_header_name"],
                         self.id.replace('\\',r'\\').replace('"',r'\"'))
        response = self.imap_server.uid("SEARCH", search_string)
        data = self.imap_server.check_response("search " + search_string,
                                               response)
        new_id = data[0]

        # See [ 870799 ] imap trying to fetch invalid message UID
        # It seems that although the save gave a "NO" response to the
        # first save, the message was still saved (without the flags,
        # probably).  This really isn't good behaviour on the server's
        # part, but, as usual, we try and deal with it.  So, if we get
        # more than one undeleted message with the same SpamBayes id,
        # delete all of them apart from the last one, and use that.
        multiple_ids = new_id.split()
        for id_to_remove in multiple_ids[:-1]:
            response = self.imap_server.uid("STORE", id_to_remove,
                                            "+FLAGS.SILENT",
                                            "(\\Deleted \\Seen)")
            command = "silently delete and make seen %s" % (id_to_remove,)
            self.imap_server.check_response(command, response)

        if multiple_ids:
            new_id = multiple_ids[-1]
        else:
            # Let's hope it doesn't, but, just in case, if the search
            # turns up empty, we make the assumption that the new message
            # is the last one with a recent flag.
            response = self.imap_server.uid("SEARCH", "RECENT")
            data = self.imap_server.check_response("search recent",
                                                   response)
            new_id = data[0]
            if new_id.find(' ') > -1:
                ids = new_id.split(' ')
                new_id = ids[-1]

            # Ok, now we're in trouble if we still haven't found it.
            # We make a huge assumption that the new message is the one
            # with the highest UID (they are sequential, so this will be
            # ok as long as another message hasn't also arrived).
            if new_id == "":
                response = self.imap_server.uid("SEARCH", "ALL")
                data = self.imap_server.check_response("search all",
                                                       response)
                new_id = data[0]
                if new_id.find(' ') > -1:
                    ids = new_id.split(' ')
                    new_id = ids[-1]
        self.uid = new_id


class IMAPFolder(object):
    def __init__(self, folder_name, imap_server, stats):
        self.name = folder_name
        self.imap_server = imap_server
        self.stats = stats

        # Unique names for cached messages - see _generate_id below.
        self.lastBaseMessageName = ''
        self.uniquifier = 2

    def __cmp__(self, obj):
        """Two folders are equal if their names are equal."""
        if obj is None:
            return False
        return cmp(self.name, obj.name)

    def __iter__(self):
        """Iterate through the messages in this IMAP folder."""
        for key in self.keys():
            yield self[key]

    def keys(self):
        '''Returns *uids* for all the messages in the folder not
        marked as deleted.'''
        self.imap_server.SelectFolder(self.name)
        response = self.imap_server.uid("SEARCH", "UNDELETED")
        data = self.imap_server.check_response("search undeleted", response)
        if data[0]:
            return data[0].split(' ')
        else:
            return []

    custom_header_id_re = re.compile(re.escape(\
        options["Headers", "mailid_header_name"]) + "\:\s*(\d+(?:\-\d)?)",
                                     re.IGNORECASE)
    message_id_re = re.compile("Message-ID\: ?\<([^\n\>]+)\>",
                               re.IGNORECASE)
    def __getitem__(self, key):
        """Return message matching the given *uid*.

        The messages returned have no substance (so this should be
        reasonably quick, even with large messages).  You need to call
        get_full_message() on the returned message to get the substance of
        the message from the server."""
        self.imap_server.SelectFolder(self.name)

        # Using RFC822.HEADER.LINES would be better here, but it seems
        # that not all servers accept it, even though it is in the RFC
        response = self.imap_server.uid("FETCH", key, "RFC822.HEADER")
        response_data = self.imap_server.check_response(\
            "fetch %s rfc822.header" % (key,), response)
        data = self.imap_server.extract_fetch_data(response_data)
        # The data will be a dictionary - hopefully with only one element,
        # but maybe more than one.  The key is the message number, which we
        # do not have (we use the UID instead).  So we look through the
        # message and use the first data of the right type we find.
        headers = None
        for msg_data in data.itervalues():
            if "RFC822.HEADER" in msg_data:
                headers = msg_data["RFC822.HEADER"]
                break
        if headers is None:
            raise BadIMAPResponseError("FETCH response", response_data)

        # Create a new IMAPMessage object, which will be the return value.
        msg = IMAPMessage()
        msg.folder = self
        msg.uid = key
        msg.imap_server = self.imap_server

        # We use the MessageID header as the ID for the message, as long
        # as it is available, and if not, we add our own.
        # Search for our custom id first, for backwards compatibility.
        for id_header_re in [self.custom_header_id_re, self.message_id_re]:
            mo = id_header_re.search(headers)
            if mo:
                msg.setId(mo.group(1))
                break
        else:
            newid = self._generate_id()
            if options["globals", "verbose"]:
                print >> sys.stderr, "[imapfilter] saving", msg.uid, "with new id:", newid
            msg.setId(newid)
            # Unfortunately, we now have to re-save this message, so that
            # our id is stored on the IMAP server.  The vast majority of
            # messages have Message-ID headers, from what I can tell, so
            # we should only rarely have to do this.  It's less often than
            # with the previous solution, anyway!
            # msg = msg.get_full_message()
            # msg.Save()

        if options["globals", "verbose"]:
            sys.stdout.write(".")
        return msg

    # Lifted straight from sb_server.py (under the name getNewMessageName)
    def _generate_id(self):
        # The message id is the time it arrived, with a uniquifier
        # appended if two arrive within one clock tick of each other.
        messageName = "%10.10d" % long(time.time())
        if messageName == self.lastBaseMessageName:
            messageName = "%s-%d" % (messageName, self.uniquifier)
            self.uniquifier += 1
        else:
            self.lastBaseMessageName = messageName
            self.uniquifier = 2
        return messageName

    def Train(self, classifier, isSpam):
        """Train folder as spam/ham."""
        num_trained = 0
        for msg in self:
            if msg.GetTrained() == (not isSpam):
                msg = msg.get_full_message()
                if msg.could_not_retrieve:
                    # Something went wrong, and we couldn't even get
                    # an invalid message, so just skip this one.
                    # Annoyingly, we'll try to do it every time the
                    # script runs, but hopefully the user will notice
                    # the errors and move it soon enough.
                    continue
                msg.delSBHeaders()
                classifier.unlearn(msg.tokenize(), not isSpam)
                if isSpam:
                    old_class = options["Headers", "header_ham_string"]
                else:
                    old_class = options["Headers", "header_spam_string"]

                # Once the message has been untrained, it's training memory
                # should reflect that on the off chance that for some
                # reason the training breaks.
                msg.RememberTrained(None)
            else:
                old_class = None

            if msg.GetTrained() is None:
                msg = msg.get_full_message()
                if msg.could_not_retrieve:
                    continue
                saved_headers = msg.currentSBHeaders()
                msg.delSBHeaders()
                classifier.learn(msg.tokenize(), isSpam)
                num_trained += 1
                msg.RememberTrained(isSpam)
                self.stats.RecordTraining(not isSpam, old_class=old_class)
                if isSpam:
                    move_opt_name = "move_trained_spam_to_folder"
                else:
                    move_opt_name = "move_trained_ham_to_folder"
                if options["imap", move_opt_name] != "":
                    # We need to restore the SpamBayes headers.
                    for header, value in saved_headers.items():
                        msg[header] = value
                    msg.MoveTo(IMAPFolder(options["imap", move_opt_name],
                                           self.imap_server, self.stats))
                    msg.Save()
        return num_trained

    def Filter(self, classifier, spamfolder, unsurefolder, hamfolder):
        count = {}
        count["ham"] = 0
        count["spam"] = 0
        count["unsure"] = 0
        for msg in self:
            cls = msg.GetClassification()
            if cls is None or hamfolder is not None:
                if options["globals", "verbose"]:
                    print >> sys.stderr, "[imapfilter] classified as %s:" % cls, msg.uid
                
                msg = msg.get_full_message()
                if msg.could_not_retrieve:
                    # Something went wrong, and we couldn't even get
                    # an invalid message, so just skip this one.
                    # Annoyingly, we'll try to do it every time the
                    # script runs, but hopefully the user will notice
                    # the errors and move it soon enough.

                    if options["globals", "verbose"]:
                        print >> sys.stderr, "[imapfilter] could not retrieve:", msg.uid
                    continue
                
                (prob, clues) = classifier.spamprob(msg.tokenize(),
                                                    evidence=True)
                # Add headers and remember classification.
                msg.delSBHeaders()
                msg.addSBHeaders(prob, clues)
                self.stats.RecordClassification(prob)

                cls = msg.GetClassification()
                if cls == options["Headers", "header_ham_string"]:
                    if hamfolder:
                        if options["globals", "verbose"]:
                            print >> sys.stderr, "[imapfilter] moving to ham folder:",
                            print >> sys.stderr, msg.uid
                        msg.MoveTo(hamfolder)
                    # Otherwise, we leave ham alone.
                    count["ham"] += 1
                elif cls == options["Headers", "header_spam_string"]:
                    if options["globals", "verbose"]:
                        print >> sys.stderr, "[imapfilter] moving to spam folder:",
                        print >> sys.stderr, msg.uid
                    msg.MoveTo(spamfolder)
                    count["spam"] += 1
                else:
                    if options["globals", "verbose"]:
                        print >> sys.stderr, "[imapfilter] moving to unsure folder:", msg.uid
                    msg.MoveTo(unsurefolder)
                    count["unsure"] += 1
                msg.Save()
            else:
                if options["globals", "verbose"]:
                    print >> sys.stderr, "[imapfilter] already classified:", msg.uid
                
        return count


class IMAPFilter(object):
    def __init__(self, classifier, stats):
        self.spam_folder = None
        self.unsure_folder = None
        self.ham_folder = None
        self.classifier = classifier
        self.imap_server = None
        self.stats = stats

    def Train(self):
        assert self.imap_server, "Cannot do anything without IMAP server."
        
        if options["globals", "verbose"]:
            t = time.time()

        total_trained = 0
        for is_spam, option_name in [(False, "ham_train_folders"),
                                     (True, "spam_train_folders")]:
            training_folders = options["imap", option_name]
            for fol in training_folders:
                # Select the folder to make sure it exists
                try:
                    self.imap_server.SelectFolder(fol)
                except BadIMAPResponseError:
                    print >> sys.stderr, "Skipping", fol, "as it cannot be selected."
                    continue

                if options['globals', 'verbose']:
                    print >> sys.stderr, ("   Training %s folder %s" %
                                          (["ham", "spam"][is_spam], fol))
                folder = IMAPFolder(fol, self.imap_server, self.stats)
                num_trained = folder.Train(self.classifier, is_spam)
                total_trained += num_trained
                if options['globals', 'verbose']:
                    print >> sys.stderr, "\n      ", num_trained, "trained."

        if total_trained:
            self.classifier.store()

        if options["globals", "verbose"]:
            print >> sys.stderr, ("Training took %.4f seconds, %s messages were trained."
                                  % (time.time() - t, total_trained))

    def Filter(self):
        assert self.imap_server, "Cannot do anything without IMAP server."
        if not self.spam_folder:
            spam_folder_name = options["imap", "spam_folder"]
            if options["globals", "verbose"]:
                print >> sys.stderr, "[imapfilter] spam folder:", spam_folder_name
            self.spam_folder = IMAPFolder(
                spam_folder_name, self.imap_server, self.stats)
            
        if not self.unsure_folder:
            unsure_folder_name = options["imap", "unsure_folder"]
            if options["globals", "verbose"]:
                print >> sys.stderr, "[imapfilter] unsure folder:", unsure_folder_name
            self.unsure_folder = IMAPFolder(
                unsure_folder_name, self.imap_server, self.stats)

        ham_folder_name = options["imap", "ham_folder"]
        if options["globals", "verbose"]:
            print >> sys.stderr, "[imapfilter] ham folder:", ham_folder_name
            
        if ham_folder_name and not self.ham_folder:
            self.ham_folder = IMAPFolder(ham_folder_name, self.imap_server,
                                         self.stats)

        if options["globals", "verbose"]:
            t = time.time()

        count = {}
        count["ham"] = 0
        count["spam"] = 0
        count["unsure"] = 0

        # Select the ham, spam and unsure folders to make sure they exist.
        try:
            self.imap_server.SelectFolder(self.spam_folder.name)
        except BadIMAPResponseError:
            print >> sys.stderr, "Cannot select spam folder.  Please check configuration."
            sys.exit(-1)
        try:
            self.imap_server.SelectFolder(self.unsure_folder.name)
        except BadIMAPResponseError:
            print >> sys.stderr, "Cannot select unsure folder.  Please check configuration."
            sys.exit(-1)
        if self.ham_folder:
            try:
                self.imap_server.SelectFolder(self.ham_folder.name)
            except BadIMAPResponseError:
                print >> sys.stderr, "Cannot select ham folder.  Please check configuration."
                sys.exit(-1)
                
        for filter_folder in options["imap", "filter_folders"]:
            # Select the folder to make sure it exists.
            try:
                self.imap_server.SelectFolder(filter_folder)
            except BadIMAPResponseError:
                print >> sys.stderr, "Cannot select", filter_folder, "... skipping." 
                continue

            folder = IMAPFolder(filter_folder, self.imap_server, self.stats)
            subcount = folder.Filter(self.classifier, self.spam_folder,
                                     self.unsure_folder, self.ham_folder)
            for key in count.keys():
                count[key] += subcount.get(key, 0)

        if options["globals", "verbose"]:
            if count is not None:
                print >> sys.stderr, ("\nClassified %s ham, %s spam, and %s unsure." %
                                      (count["ham"], count["spam"], count["unsure"]))
            print >> sys.stderr, "Classifying took %.4f seconds." % (time.time() - t,)


def servers(promptForPass = False):
    """Returns a list containing a tuple (server,user,passwd) for each IMAP server in options.

If promptForPass is True or at least on password is missing from options,
prompts the user for each server's password.
"""
    
    servers = options["imap", "server"]
    usernames = options["imap", "username"]
    pwds = options["imap", "password"]

    if promptForPass or len(pwds) < len(usernames):
        pwds = []
        for u in usernames:
            pwds.append(getpass("Enter password for %s:" % (u,)))
            
    return zip(servers, usernames, pwds)
            
def run(force_UI=False):
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hbPtcvl:e:i:d:p:o:',
                                   ["verbose"])
    except getopt.error, msg:
        print >> sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    doTrain = False
    doClassify = False
    doExpunge = options["imap", "expunge"]
    imapDebug = 0
    sleepTime = 0
    promptForPass = False
    launchUI = False

    for opt, arg in opts:
        if opt == '-h':
            print >> sys.stderr, __doc__
            sys.exit()
        elif opt == "-b":
            launchUI = True
        elif opt == '-t':
            doTrain = True
        elif opt == '-P':
            promptForPass = True
        elif opt == '-c':
            doClassify = True
        elif opt in ('-v', '--verbose'):
            options["globals", "verbose"] = True
        elif opt == '-e':
            if arg == 'y':
                doExpunge = True
            else:
                doExpunge = False
        elif opt == '-i':
            imapDebug = int(arg)
        elif opt == '-l':
            sleepTime = int(arg) * 60
        elif opt == '-o':
            options.set_from_cmdline(arg, sys.stderr)
    bdbname, useDBM = storage.database_type(opts)

    # Let the user know what they are using...
    v = get_current_version();
    print "%s.\n" % (v.get_long_version("SpamBayes IMAP Filter"),)

    if options["globals", "verbose"]:
        print "Loading database %s..." % (bdbname),

    classifier = storage.open_storage(bdbname, useDBM)
    message_db = message.Message().message_info_db

    if options["globals", "verbose"]:
        print "Done."

    if not ( launchUI or force_UI or options["imap", "server"] ):
        print "You need to specify both a server and a username."
        sys.exit()

    servers_data = servers(promptForPass)
    
    # Load stats manager.
    stats = Stats.Stats(options, message_db)
    
    imap_filter = IMAPFilter(classifier, stats)

    # Web interface.  We have changed the rules about this many times.
    # With 1.0.x, the rule is that the interface is served if we are
    # not classifying or training.  However, this runs into the problem
    # that if we run with -l, we might still want to edit the options,
    # and we don't want to start a separate instance, because then the
    # database is accessed from two processes.
    # With 1.1.x, the rule is that the interface is also served if the
    # -l option is used, which means it is only not served if we are
    # doing a one-off classification/train.  In that case, there would
    # probably not be enough time to get to the interface and interact
    # with it (and we don't want it to die halfway through!), and we
    # don't want to slow classification/training down, either.
    if sleepTime or not (doClassify or doTrain):
        imaps = []
        for server, username, password in servers_data:
            if server == "":
                imaps.append(None)
            else:
                imaps.append(IMAPSession(server, imapDebug, doExpunge))

        def close_db():
            message_db.store()
            message_db.close()
            message.Message().message_info_db.store()
            message.Message().message_info_db.close()
            message.Message.message_info_db = None
            classifier.store()
            classifier.close()

        def change_db():
            classifier = storage.open_storage(*storage.database_type(opts))
            message.Message.message_info_db = message_db
            imap_filter = IMAPFilter(classifier, message_db)

        httpServer = UserInterfaceServer(options["html_ui", "port"])
        pwds = [ x[2] for x in servers_data ]
        httpServer.register(IMAPUserInterface(classifier, imaps, pwds,
                                              IMAPSession, stats=stats,
                                              close_db=close_db,
                                              change_db=change_db))
        launchBrowser = launchUI or options["html_ui", "launch_browser"]
        if sleepTime:
            # Run in a separate thread, as we have more work to do.
            thread.start_new_thread(Dibbler.run, (),
                                    {"launchBrowser":launchBrowser})
        else:
            Dibbler.run(launchBrowser=launchBrowser)
    if doClassify or doTrain:
        imaps = []
        for server, username, password in servers_data:
            imaps.append(((server, imapDebug, doExpunge),
                          username, password))

        # In order to make working with multiple servers easier, we
        # allow the user to have separate configuration files for each
        # server.  These may specify different folders to watch, different
        # spam/unsure folders, or any other options (e.g. thresholds).
        # For each server we use the default (global) options, and load
        # the specific options on top.  To facilitate this, we use a
        # restore point for the options with just the default (global)
        # options.
        # XXX What about when we are running with -l and change options
        # XXX via the web interface?  We need to handle that, really.
        options.set_restore_point()
        while True:
            for (server, imapDebug, doExpunge), username, password in imaps:
                imap = IMAPSession(server, imapDebug, doExpunge)
                if options["globals", "verbose"]:
                    print "Account: %s:%s" % (imap.server, imap.port)
                if imap.connected:
                    # As above, we load a separate configuration file
                    # for each server, if it exists.  We look for a
                    # file in the optionsPathname directory, with the
                    # name server.name.ini or .spambayes_server_name_rc
                    # XXX While 1.1 is in alpha these names can be
                    # XXX changed if desired.  Please let Tony know!
                    basedir = os.path.dirname(optionsPathname)
                    fn1 = os.path.join(basedir, imap.server + ".ini")
                    fn2 = os.path.join(basedir,
                                       imap.server.replace(".", "_") + \
                                       "_rc")
                    for fn in (fn1, fn2):
                        if os.path.exists(fn):
                            options.merge_file(fn)

                    try:                    
                        imap.login(username, password)
                    except LoginFailure, e:
                        print str(e)
                        continue
                    imap_filter.imap_server = imap

                    if doTrain:
                        if options["globals", "verbose"]:
                            print "Training"
                        imap_filter.Train()
                    if doClassify:
                        if options["globals", "verbose"]:
                            print "Classifying"
                        imap_filter.Filter()

                    imap.logout()
                    options.revert_to_restore_point()
                else:
                    # Failed to connect.  This may be a temporary problem,
                    # so just continue on and try again.  If we are only
                    # running once we will end, otherwise we'll try again
                    # in sleepTime seconds.
                    # XXX Maybe we should log this error message?
                    pass

            if sleepTime:
                time.sleep(sleepTime)
            else:
                break

if __name__ == '__main__':
    run()
