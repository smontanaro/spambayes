#!/usr/bin/env python

"""An IMAP filter.  An IMAP message box is scanned and all non-scored
messages are scored and (where necessary) filtered.

The original filter design owed much to isbg by Roger Binns
(http://www.rogerbinns.com/isbg).

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
                          (If not specified, and neither the -c or -t
                          options are used, then this will default to the
                          value in your configuration file).
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
    o This is alpha software!  The filter is currently being developed and
      tested.  We do *not* recommend using it on a production system unless
      you are confident that you can get your mail back if you lose it.  On
      the other hand, we do recommend that you test it for us and let us
      know if anything does go wrong.
    o By default, the filter does *not* delete, modify or move any of your
      mail.  Due to quirks in how imap works, new versions of your mail are
      modified and placed in new folders, but the originals are still
      available.  These are flagged with the /Deleted flag so that you know
      that they can be removed.  Your mailer may not show these messages
      by default, but there should be an option to do so.  *However*, if
      your mailer automatically purges/expunges (i.e. permanently deletes)
      mail flagged as such, *or* if you set the imap_expunge option to
      True, then this mail will be irretrievably lost.
"""

todo = """
To Do:
    o IMAPMessage and IMAPFolder currently carry out very simple checks
      of responses received from IMAP commands, but if the response is not
      "OK", then the filter terminates.  Handling of these errors could be
      much nicer.
    o IMAP over SSL is relatively untested.
    o Develop a test script, like spambayes/test/test_pop3proxy.py that
      runs through some tests (perhaps with a *real* imap server, rather
      than a dummy one).  This would make it easier to carry out the tests
      against each server whenever a change is made.
    o IMAP supports authentication via other methods than the plain-text
      password method that we are using at the moment.  Neither of the
      servers I have access to offer any alternative method, however.  If
      someone's does, then it would be nice to offer this.
    o Usernames should be able to be literals as well as quoted strings.
      This might help if the username/password has special characters like
      accented characters.
    o Suggestions?
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>, Tim Stone"
__credits__ = "All the Spambayes folk."

from __future__ import generators

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

import socket
import os
import re
import time
import sys
import getopt
import types
import traceback
import email
import email.Parser
from getpass import getpass
from email.Header import Header
from email.Utils import parsedate
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

from spambayes.Options import options, get_pathname_option
from spambayes import tokenizer, storage, message, Dibbler
from spambayes.UserInterface import UserInterfaceServer
from spambayes.ImapUI import IMAPUserInterface
from spambayes.Version import get_version_string

from imaplib import IMAP4
from imaplib import Time2Internaldate
try:
    if options["imap", "use_ssl"]:
        from imaplib import IMAP4_SSL as BaseIMAP
    else:
        from imaplib import IMAP4 as BaseIMAP
except ImportError:
    from imaplib import IMAP4 as BaseIMAP

# global IMAPlib object
global imap
imap = None

# A flag can have any character in the ascii range 32-126
# except for (){ %*"\
FLAG_CHARS = ""
for i in range(32, 127):
    if not chr(i) in ['(', ')', '{', ' ', '%', '*', '"', '\\']:
        FLAG_CHARS += chr(i)
FLAG = r"\\?[" + re.escape(FLAG_CHARS) + r"]+"
# The empty flag set "()" doesn't match, so that extract returns
# data["FLAGS"] == None
FLAGS_RE = re.compile(r"(FLAGS) (\((" + FLAG + r" )*(" + FLAG + r")\))")
INTERNALDATE_RE = re.compile(r"(INTERNALDATE) (\"\d{1,2}\-[A-Za-z]{3,3}\-" +
                             r"\d{2,4} \d{2,2}\:\d{2,2}\:\d{2,2} " +
                             r"[\+\-]\d{4,4}\")")
RFC822_RE = re.compile(r"(RFC822) (\{[\d]+\})")
BODY_PEEK_RE = re.compile(r"(BODY\[\]) (\{[\d]+\})")
RFC822_HEADER_RE = re.compile(r"(RFC822.HEADER) (\{[\d]+\})")
UID_RE = re.compile(r"(UID) ([\d]+)")
FETCH_RESPONSE_RE = re.compile(r"([0-9]+) \(([" + \
                               re.escape(FLAG_CHARS) + r"\"\{\}\(\)\\ ]*)\)?")
LITERAL_RE = re.compile(r"^\{[\d]+\}$")

def _extract_fetch_data(response):
    '''Extract data from the response given to an IMAP FETCH command.'''
    # Response might be a tuple containing literal data
    # At the moment, we only handle one literal per response.  This
    # may need to be improved if our code ever asks for something
    # more complicated (like RFC822.Header and RFC822.Body)
    if type(response) == types.TupleType:
        literal = response[1]
        response = response[0]
    else:
        literal = None
    # the first item will always be the message number
    mo = FETCH_RESPONSE_RE.match(response)
    data = {}
    if mo is None:
        print """IMAP server gave strange fetch response.  Please
        report this as a bug."""
        print response
    else:
        data["message_number"] = mo.group(1)
        response = mo.group(2)
    # We support the following FETCH items:
    #  FLAGS
    #  INTERNALDATE
    #  RFC822
    #  UID
    #  RFC822.HEADER
    #  BODY.PEEK
    # All others are ignored.
    for r in [FLAGS_RE, INTERNALDATE_RE, RFC822_RE, UID_RE,
              RFC822_HEADER_RE, BODY_PEEK_RE]:
        mo = r.search(response)
        if mo is not None:
            if LITERAL_RE.match(mo.group(2)):
                data[mo.group(1)] = literal
            else:
                data[mo.group(1)] = mo.group(2)
    return data

class IMAPSession(BaseIMAP):
    '''A class extending the IMAP4 class, with a few optimizations'''

    def __init__(self, server, port, debug=0, do_expunge=False):
        try:
            BaseIMAP.__init__(self, server, port)
        except:
            # A more specific except would be good here, but I get
            # (in Python 2.2) a generic 'error' and a 'gaierror'
            # if I pass a valid domain that isn't an IMAP server
            # or invalid domain (respectively)
            print "Invalid server or port, please check these settings."
            sys.exit(-1)
        self.debug = debug
        # For efficiency, we remember which folder we are currently
        # in, and only send a select command to the IMAP server if
        # we want to *change* folders.  This function is used by
        # both IMAPMessage and IMAPFolder.
        self.current_folder = None
        self.do_expunge = do_expunge
        self.logged_in = False

    def login(self, username, pwd):
        try:
            BaseIMAP.login(self, username, pwd)  # superclass login
        except BaseIMAP.error, e:
            if str(e) == "permission denied":
                print "There was an error logging in to the IMAP server."
                print "The userid and/or password may be incorrect."
                sys.exit()
            else:
                raise
        self.logged_in = True

    def logout(self):
        # sign off
        if self.do_expunge:
            # we may never have logged in, in which case we do nothing
            if self.logged_in:
                # expunge messages from the spam and unsure folders
                for fol in ["spam_folder",
                            "unsure_folder",]:
                    self.select(options["imap", fol])
                    self.expunge()
                # expunge messages from the ham and spam training folders
                for fol_list in ["ham_train_folders",
                                 "spam_train_folders",]:
                    for fol in options["imap", fol_list]:
                        self.select(fol)
                        self.expunge()
        BaseIMAP.logout(self)  # superclass logout

    def SelectFolder(self, folder):
        '''A method to point ensuing imap operations at a target folder'''
        if self.current_folder != folder:
            if self.current_folder != None:
                if self.do_expunge:
                    # It is faster to do close() than a single
                    # expunge when we log out (because expunge returns
                    # a list of all the deleted messages which we don't do
                    # anything with)
                    imap.close()
            # We *always* use SELECT and not EXAMINE, because this
            # speeds things up considerably.
            if folder == "":
                # This is Python bug #845560 - if the empty string is
                # passed, we get a traceback, not just an 'invalid folder'
                # error, so print out a warning and exit.
                print "Tried to select an invalid folder"
                sys.exit(-1)
            response = self.select(folder, None)
            if response[0] != "OK":
                print "Invalid response to select %s:\n%s" % (folder,
                                                              response)
                sys.exit(-1)
            self.current_folder = folder
            return response

    def folder_list(self):
        '''Return a alphabetical list of all folders available on the
        server'''
        response = self.list()
        if response[0] != "OK":
            return []
        all_folders = response[1]
        folders = []
        for fol in all_folders:
            # Sigh.  Some servers may give us back the folder name as a
            # literal, so we need to crunch this out.
            if isinstance(fol, ()):
                r = re.compile(r"{\d+}")
                m = r.search(fol[0])
                if not m:
                    # Something is wrong here!  Skip this folder
                    continue
                fol = '%s"%s"' % (fol[0][:m.start()], fol[1])
            r = re.compile(r"\(([\w\\ ]*)\) ")
            m = r.search(fol)
            if not m:
                # Something is not good with this folder, so skip it.
                continue
            name_attributes = fol[:m.end()-1]
            # IMAP is a truly odd protocol.  The delimiter is
            # only the delimiter for this particular folder - each
            # folder *may* have a different delimiter
            self.folder_delimiter = fol[m.end()+1:m.end()+2]
            # a bit of a hack, but we really need to know if this is
            # the case
            if self.folder_delimiter == ',':
                print "WARNING: Your imap server uses a comma as the " \
                      "folder delimiter.  This may cause unpredictable " \
                      "errors."
            folders.append(fol[m.end()+4:].strip('"'))
        folders.sort()
        return folders

    def FindMessage(self, id):
        '''A (potentially very expensive) method to find a message with
        a given spambayes id (header), and return a message object (no
        substance).'''
        # If efficiency becomes a concern, what we could do is store a
        # dict of key-to-folder, and look in that folder first.  (It might
        # have moved independantly of us, so we would still have to search
        # if we didn't find it).  For the moment, we do an search through
        # all folders, alphabetically.
        for folder_name in self.folder_list():
            fol = IMAPFolder(folder_name)
            for msg in fol:
                if msg.id == id:
                    return msg
        return None

class IMAPMessage(message.SBHeaderMessage):
    def __init__(self):
        message.Message.__init__(self)
        self.folder = None
        self.previous_folder = None
        self.rfc822_command = "(BODY.PEEK[])"
        self.rfc822_key = "BODY[]"
        self.got_substance = False
        self.invalid = False
        self.could_not_retrieve = False

    def setFolder(self, folder):
        self.folder = folder

    def _check(self, response, command):
        if response[0] != "OK":
            print "Invalid response to %s:\n%s" % (command, response)
            sys.exit(-1)

    def extractTime(self):
        # When we create a new copy of a message, we need to specify
        # a timestamp for the message.  If the message has a valid date
        # header we use that.  Otherwise, we use the current time.
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

    def get_substance(self):
        '''Retrieve the RFC822 message from the IMAP server and set as the
        substance of this message.'''
        if self.got_substance:
            return
        assert(self.id, "Cannot get substance of message without an id")
        assert(self.uid, "Cannot get substance of message without an UID")
        imap.SelectFolder(self.folder.name)
        try:
            try:
                response = imap.uid("FETCH", self.uid, self.rfc822_command)
            except IMAP4.error:
                self.rfc822_command = "RFC822"
                self.rfc822_key = "RFC822"
                response = imap.uid("FETCH", self.uid, self.rfc822_command)
            if response[0] != "OK":
                self.rfc822_command = "RFC822"
                self.rfc822_key = "RFC822"
                response = imap.uid("FETCH", self.uid, self.rfc822_command)
        except MemoryError:
            # Really big messages can trigger a MemoryError here.
            # The problem seems to be line 311 (Python 2.3) of socket.py,
            # which has "return "".join(buffers)".
            # We want to handle this gracefully, although we can't really
            # do what we do later, and rewrite the message, since we can't
            # load it in the first place.  Maybe an elegant solution would
            # be to get the message in parts, or just use the first X
            # characters for classification.  For now, we just carry on,
            # warning the user and ignoring the message.
            self.could_not_retrieve = True
            print >>sys.stderr, "MemoryError with message %s (uid %s)" % \
                  (self.id, self.uid)
            # We could print the traceback, too, but don't for the moment.
            #traceback.print_exc(None, stream)
            return
            
        self._check(response, "uid fetch")
        data = _extract_fetch_data(response[1][0])
        # Annoyingly, we can't just pass over the RFC822 message to an
        # existing message object (like self) and have it parse it. So
        # we go through the hoops of creating a new message, and then
        # copying over all its internals.
        try:
            new_msg = email.Parser.Parser().parsestr(data[self.rfc822_key])
        # We use a general 'except' because the email package doesn't
        # always return email.Errors (it can return a TypeError, for
        # example) if the email is invalid.  In any case, we want
        # to keep going, and not crash, because we might leave the
        # user's mailbox in a bad state if we do.  Better to soldier
        # on.
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

            # This is nicked from sb_server - thanks Richie!
            stream = StringIO.StringIO()
            traceback.print_exc(None, stream)
            details = stream.getvalue()

            # Build the header.  This will strip leading whitespace from
            # the lines, so we add a leading dot to maintain indentation.
            detailLines = details.strip().split('\n')
            dottedDetails = '\n.'.join(detailLines)
            headerName = 'X-Spambayes-Exception'
            header = Header(dottedDetails, header_name=headerName)

            # Insert the header, converting email.Header's '\n' line
            # breaks to IMAP4's '\r\n'.
            # (Also insert the id header, otherwise we'll keep doing
            # this message over and over again).
            headers, body = re.split(r'\n\r?\n', data["RFC822"], 1)
            header = re.sub(r'\r?\n', '\r\n', str(header))
            headers += "\n%s: %s\r\n%s: %s\r\n\r\n" % \
                       (headerName, header,
                        options["Headers", "mailid_header_name"], self.id)
            self.invalid_content = headers + body

            # Print the exception and a traceback.
            print >>sys.stderr, details
        else:
            self._headers = new_msg._headers
            self._unixfrom = new_msg._unixfrom
            self._payload = new_msg._payload
            self._charset = new_msg._charset
            self.preamble = new_msg.preamble
            self.epilogue = new_msg.epilogue
            self._default_type = new_msg._default_type
            if not self.has_key(options["Headers", "mailid_header_name"]):
                self[options["Headers", "mailid_header_name"]] = self.id
        self.got_substance = True
        if options["globals", "verbose"]:
            sys.stdout.write(chr(8) + "*")

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
        if self.invalid:
            return self._force_CRLF(self.invalid_content)
        else:
            return message.SBHeaderMessage.as_string(self, unixfrom)

    def Save(self):
        '''Save message to imap server.'''
        # we can't actually update the message with IMAP
        # so what we do is create a new message and delete the old one
        assert(self.folder is not None,
               "Can't save a message that doesn't have a folder.")
        assert(self.id, "Can't save a message that doesn't have an id.")
        response = imap.uid("FETCH", self.uid, "(FLAGS INTERNALDATE)")
        self._check(response, 'fetch (flags internaldate)')
        data = _extract_fetch_data(response[1][0])
        if data.has_key("INTERNALDATE"):
            msg_time = data["INTERNALDATE"]
        else:
            msg_time = self.extractTime()
        if data.has_key("FLAGS"):
            flags = data["FLAGS"]
            # The \Recent flag can be fetched, but cannot be stored
            # We must remove it from the list if it is there.
            flags = re.sub(r"\\Recent ?| ?\\Recent", "", flags)
        else:
            flags = None

        for flgs, tme in [(flags, msg_time),
                          (None, msg_time),
                          (flags, Time2Internaldate(time.time())),
                          (None, Time2Internaldate(time.time()))]:
            response = imap.append(self.folder.name, flgs, tme,
                                   self.as_string())
            if response[0] == "OK":
                break
        self._check(response, 'append')

        if self.previous_folder is None:
            imap.SelectFolder(self.folder.name)
        else:
            imap.SelectFolder(self.previous_folder.name)
            self.previous_folder = None
        response = imap.uid("STORE", self.uid, "+FLAGS.SILENT", "(\\Deleted \\Seen)")
        self._check(response, 'store')
        # Not all IMAP servers immediately offer the new message
        # (stupidly), but we need to find it.  Generally a 'no-op' will
        # allow the server time to handle it, so do that.
        # See [ 941596 ] sb_imapfilter.py not adding headers / moving messages
        imap.noop()

        # We need to update the uid, as it will have changed.
        # Although we don't use the UID to keep track of messages, we do
        # have to use it for IMAP operations.
        imap.SelectFolder(self.folder.name)
        response = imap.uid("SEARCH", "(UNDELETED HEADER " + \
                            options["Headers", "mailid_header_name"] + \
                            " " + self.id + ")")
        self._check(response, 'search')
        new_id = response[1][0]

        # See [ 870799 ] imap trying to fetch invalid message UID
        # It seems that although the save gave a "NO" response to the
        # first save, the message was still saved (without the flags,
        # probably).  This isn't really good behaviour on the server's
        # part, but, as usual, we try and deal with it.  So, if we get
        # more than one undeleted message with the same SpamBayes id,
        # delete all of them apart from the last one, and use that.
        multiple_ids = new_id.split()
        for id_to_remove in multiple_ids[:-1]:
            response = imap.uid("STORE", id_to_remove, "+FLAGS.SILENT",
                                "(\\Deleted \\Seen)")
            self._check(response, 'store')
        if multiple_ids:
            new_id = multiple_ids[-1]
        else:
            # Let's hope it doesn't, but, just in case, if the search
            # turns up empty, we make the assumption that the new
            # message is the last one with a recent flag
            response = imap.uid("SEARCH", "RECENT")
            new_id = response[1][0]
            if new_id.find(' ') > -1:
                ids = new_id.split(' ')
                new_id = ids[-1]
            # Ok, now we're in trouble if we still haven't found it.
            # We make a huge assumption that the new message is the one
            # with the highest UID (they are sequential, so this will be
            # ok as long as another message hasn't also arrived)
            if new_id == "":
                response = imap.uid("SEARCH", "ALL")
                new_id = response[1][0]
                if new_id.find(' ') > -1:
                    ids = new_id.split(' ')
                    new_id = ids[-1]
        self.uid = new_id

# This performs a similar function to email.message_from_string()
def imapmessage_from_string(s, _class=IMAPMessage, strict=False):
    return email.message_from_string(s, _class, strict)


class IMAPFolder(object):
    def __init__(self, folder_name):
        self.name = folder_name
        # Unique names for cached messages - see _generate_id below.
        self.lastBaseMessageName = ''
        self.uniquifier = 2

    def __cmp__(self, obj):
        '''Two folders are equal if their names are equal'''
        if obj is None:
            return False
        return cmp(self.name, obj.name)

    def _check(self, response, command):
        if response[0] != "OK":
            print "Invalid response to %s:\n%s" % (command, response)
            sys.exit(-1)

    def __iter__(self):
        '''IMAPFolder is iterable'''
        for key in self.keys():
            try:
                yield self[key]
            except KeyError:
                pass

    def recent_uids(self):
        '''Returns uids for all the messages in the folder that
        are flagged as recent, but not flagged as deleted.'''
        imap.SelectFolder(self.name, True)
        response = imap.uid("SEARCH", "RECENT UNDELETED")
        self._check(response, "SEARCH RECENT UNDELETED")
        return response[1][0].split(' ')

    def keys(self):
        '''Returns *uids* for all the messages in the folder not
        marked as deleted.'''
        imap.SelectFolder(self.name)
        response = imap.uid("SEARCH", "UNDELETED")
        self._check(response, "SEARCH UNDELETED")
        if response[1][0]:
            return response[1][0].split(' ')
        else:
            return []

    def __getitem__(self, key):
        '''Return message (no substance) matching the given *uid*.'''
        # We don't retrieve the substances of the message here - you need
        # to call msg.get_substance() to do that.
        imap.SelectFolder(self.name)
        # Using RFC822.HEADER.LINES would be better here, but it seems
        # that not all servers accept it, even though it is in the RFC
        response = imap.uid("FETCH", key, "RFC822.HEADER")
        self._check(response, "uid fetch header")
        data = _extract_fetch_data(response[1][0])

        msg = IMAPMessage()
        msg.setFolder(self)
        msg.uid = key
        r = re.compile(re.escape(options["Headers",
                                         "mailid_header_name"]) + \
                       "\:\s*(\d+(\-\d)?)")
        mo = r.search(data["RFC822.HEADER"])
        if mo is None:
            msg.setId(self._generate_id())
            # Unfortunately, we now have to re-save this message, so that
            # our id is stored on the IMAP server.  Before anyone suggests
            # it, we can't store it as a flag, because user-defined flags
            # aren't supported by all IMAP servers.
            # This will need to be done once per message.
            msg.get_substance()
            msg.Save()
        else:
            msg.setId(mo.group(1))

        if options["globals", "verbose"]:
            sys.stdout.write(".")
        return msg

    # Lifted straight from pop3proxy.py (under the name getNewMessageName)
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
        '''Train folder as spam/ham'''
        num_trained = 0
        for msg in self:
            if msg.could_not_retrieve:
                # Something went wrong, and we couldn't even get
                # an invalid message, so just skip this one.
                # Annoyinly, we'll try to do it every time the
                # script runs, but hopefully the user will notice
                # the errors and move it soon enough.
                continue
            if msg.GetTrained() == (not isSpam):
                msg.get_substance()
                msg.delSBHeaders()
                classifier.unlearn(msg.asTokens(), not isSpam)
                # Once the message has been untrained, it's training memory
                # should reflect that on the off chance that for some reason
                # the training breaks, which happens on occasion (the
                # tokenizer is not yet perfect)
                msg.RememberTrained(None)

            if msg.GetTrained() is None:
                msg.get_substance()
                saved_headers = msg.currentSBHeaders()
                msg.delSBHeaders()
                classifier.learn(msg.asTokens(), isSpam)
                num_trained += 1
                msg.RememberTrained(isSpam)
                if isSpam:
                    move_opt_name = "move_trained_spam_to_folder"
                else:
                    move_opt_name = "move_trained_ham_to_folder"
                if options["imap", move_opt_name] != "":
                    # We need to restore the SpamBayes headers.
                    for header, value in saved_headers.items():
                        msg[header] = value
                    msg.MoveTo(IMAPFolder(options["imap",
                                                  move_opt_name]))
                    msg.Save()
        return num_trained

    def Filter(self, classifier, spamfolder, unsurefolder):
        count = {}
        count["ham"] = 0
        count["spam"] = 0
        count["unsure"] = 0
        for msg in self:
            if msg.could_not_retrieve:
                # Something went wrong, and we couldn't even get
                # an invalid message, so just skip this one.
                # Annoyinly, we'll try to do it every time the
                # script runs, but hopefully the user will notice
                # the errors and move it soon enough.
                continue
            if msg.GetClassification() is None:
                msg.get_substance()
                (prob, clues) = classifier.spamprob(msg.asTokens(),
                                                    evidence=True)
                # add headers and remember classification
                msg.delSBHeaders()
                msg.addSBHeaders(prob, clues)

                cls = msg.GetClassification()
                if cls == options["Headers", "header_ham_string"]:
                    # we leave ham alone
                    count["ham"] += 1
                elif cls == options["Headers", "header_spam_string"]:
                    msg.MoveTo(spamfolder)
                    count["spam"] += 1
                else:
                    msg.MoveTo(unsurefolder)
                    count["unsure"] += 1
                msg.Save()
        return count


class IMAPFilter(object):
    def __init__(self, classifier):
        self.spam_folder = IMAPFolder(options["imap", "spam_folder"])
        self.unsure_folder = IMAPFolder(options["imap", "unsure_folder"])
        self.classifier = classifier

    def Train(self):
        if options["globals", "verbose"]:
            t = time.time()

        total_ham_trained = 0
        total_spam_trained = 0

        if options["imap", "ham_train_folders"] != "":
            ham_training_folders = options["imap", "ham_train_folders"]
            for fol in ham_training_folders:
                # Select the folder to make sure it exists
                imap.SelectFolder(fol)
                if options['globals', 'verbose']:
                    print "   Training ham folder %s" % (fol)
                folder = IMAPFolder(fol)
                num_ham_trained = folder.Train(self.classifier, False)
                total_ham_trained += num_ham_trained
                if options['globals', 'verbose']:
                    print "\n       %s trained." % (num_ham_trained)

        if options["imap", "spam_train_folders"] != "":
            spam_training_folders = options["imap", "spam_train_folders"]
            for fol in spam_training_folders:
                # Select the folder to make sure it exists
                imap.SelectFolder(fol)
                if options['globals', 'verbose']:
                    print "   Training spam folder %s" % (fol)
                folder = IMAPFolder(fol)
                num_spam_trained = folder.Train(self.classifier, True)
                total_spam_trained += num_spam_trained
                if options['globals', 'verbose']:
                    print "\n       %s trained." % (num_spam_trained)

        if total_ham_trained or total_spam_trained:
            self.classifier.store()

        if options["globals", "verbose"]:
            print "Training took %.4f seconds, %s messages were trained" \
                  % (time.time() - t, total_ham_trained + total_spam_trained)

    def Filter(self):
        if options["globals", "verbose"]:
            t = time.time()
        count = {}
        count["ham"] = 0
        count["spam"] = 0
        count["unsure"] = 0

        # Select the spam folder and unsure folder to make sure they exist
        imap.SelectFolder(self.spam_folder.name)
        imap.SelectFolder(self.unsure_folder.name)

        for filter_folder in options["imap", "filter_folders"]:
            # Select the folder to make sure it exists
            imap.SelectFolder(filter_folder)
            folder = IMAPFolder(filter_folder)
            subcount = folder.Filter(self.classifier, self.spam_folder,
                          self.unsure_folder)
            for key in count.keys():
                count[key] += subcount.get(key, 0)

        if options["globals", "verbose"]:
            if count is not None:
                print "\nClassified %s ham, %s spam, and %s unsure." % \
                      (count["ham"], count["spam"], count["unsure"])
            print "Classifying took %.4f seconds." % (time.time() - t,)


def run():
    global imap
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hbPtcvl:e:i:d:p:o:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    doTrain = False
    doClassify = False
    doExpunge = options["imap", "expunge"]
    imapDebug = 0
    sleepTime = 0
    promptForPass = False
    launchUI = False
    server = ""
    username = ""

    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == "-b":
            launchUI = True
        elif opt == '-t':
            doTrain = True
        elif opt == '-P':
            promptForPass = True
        elif opt == '-c':
            doClassify = True
        elif opt == '-v':
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
    print get_version_string("IMAP Filter")
    print "and engine %s.\n" % (get_version_string(),)

    if (launchUI and (doClassify or doTrain)):
        print """-b option is exclusive with -c and -t options.
The user interface will be launched, but no classification
or training will be performed.
"""

    if options["globals", "verbose"]:
        print "Loading database %s..." % (bdbname),

    classifier = storage.open_storage(bdbname, useDBM)

    if options["globals", "verbose"]:
        print "Done."

    if options["imap", "server"]:
        # The options class is ahead of us here:
        #   it knows that imap:server will eventually be able to have
        #   multiple values, but for the moment, we just use the first one
        server = options["imap", "server"]
        if len(server) > 0:
            server = server[0]
        username = options["imap", "username"]
        if len(username) > 0:
            username = username[0]
        if not promptForPass:
            pwd = options["imap", "password"]
            if len(pwd) > 0:
                pwd = pwd[0]
    else:
        pwd = None
        if not launchUI:
            print "You need to specify both a server and a username."
            sys.exit()

    if promptForPass:
        pwd = getpass()

    if server.find(':') > -1:
        server, port = server.split(':', 1)
        port = int(port)
    else:
        if options["imap", "use_ssl"]:
            port = 993
        else:
            port = 143

    imap_filter = IMAPFilter(classifier)

    # Web interface
    if not (doClassify or doTrain):
        if server != "":
            imap = IMAPSession(server, port, imapDebug, doExpunge)
        httpServer = UserInterfaceServer(options["html_ui", "port"])
        httpServer.register(IMAPUserInterface(classifier, imap, pwd,
                                              IMAPSession))
        Dibbler.run(launchBrowser=launchUI or options["html_ui",
                                                      "launch_browser"])
    else:
        while True:
            imap = IMAPSession(server, port, imapDebug, doExpunge)
            imap.login(username, pwd)

            if doTrain:
                if options["globals", "verbose"]:
                    print "Training"
                imap_filter.Train()
            if doClassify:
                if options["globals", "verbose"]:
                    print "Classifying"
                imap_filter.Filter()

            imap.logout()

            if sleepTime:
                time.sleep(sleepTime)
            else:
                break

if __name__ == '__main__':
    run()
