#!/usr/bin/env python

"""An IMAP filter.  An IMAP message box is scanned and all non-scored
messages are scored and (where necessary) filtered.

The original filter design owed much to isbg by Roger Binns
(http://www.rogerbinns.com/isbg).

Usage:
    imapfilter [options]

	note: option values with spaces in them must be enclosed
	      in double quotes

        options:
            -d  dbname  : pickled training database filename
            -D  dbname  : dbm training database filename
            -t          : train contents of spam folder and ham folder
            -c          : classify inbox
            -h          : help
            -v          : verbose mode
            -p          : security option to prompt for imap password,
                          rather than look in options["imap", "password"]
            -e y/n      : expunge/purge messages on exit (y) or not (n)
            -i debuglvl : a somewhat mysterious imaplib debugging level
            -l minutes  : period of time between filtering operations
            -b          : Launch a web browser showing the user interface.

Examples:

    Classify inbox, with dbm database
        imapfilter -c -D bayes.db
        
    Train Spam and Ham, then classify inbox, with dbm database
        imapfilter -t -c -D bayes.db

    Train Spam and Ham only, with pickled database
        imapfilter -t -d bayes.db

Warnings:
    o This is very alpha.  The filter is currently being developed and
      tested.  We do *not* recommend using it on a production system unless
      you are confident that you can get your mail back if you lose it.  On
      the other hand, we do recommend that you test it for us and let us
      know if anything does go wrong.  Once this appears in a release,
      rather than just cvs, you can feel a *little* <wink> more confident
      about using it.
    o By default, the filter does *not* delete, modify or move any of your
      mail.  Due to quirks in how imap works, new versions of your mail are
      modified and placed in new folders, but the originals are still
      available.  These are flagged with the /Deleted flag so that you know
      that they can be removed.  Your mailer may not show these messages
      by default, but there should be an option to do so.  *However*, if
      your mailer automatically purges/expunges (i.e. permanently deletes)
      mail flagged as such, *or* if you set the imap_expunge option to
      True, then this mail will be irretrievably lost.
    
To Do:
    o Find a better way to remove old msg from info database when saving
      modified messages
    o IMAPMessage and IMAPFolder currently carry out very simple checks
      of responses received from IMAP commands, but if the response is not
      "OK", then the filter terminates.  Handling of these errors could be
      much nicer.
    o IMAP over SSL would be nice.  imaplib in Python 2.3 has an SSL class
      that we could inherit from.  This idea would be that SSL is available
      if the SSL class is available (so those using Python 2.2 can't use
      imapfilter with SSL, but 2.3ers can).  It's easy enough to do the
      enabling/disabling of the options (don't forget to wipe it from the
      UI list), but I'm not quite sure how to handle the inheritance.  We
      don't actually use the IMAP4 class, we use our own class that inherits
      from that.  How can we dynamically select which class to inherit from?
      (This is probably where my lack of Python expertise shows up...)
    o Develop a test script, like testtools/pop3proxytest.py that runs
      through some tests (perhaps with a *real* imap server, rather than
      a dummy one).  This would make it easier to carry out the tests
      against each server whenever a change is made.
    o The RFC says that "unique identifiers persist across sessions", but
      also that "[i]f unique identifiers from an earlier session fail to
      persist to this session...".  This strikes me as fairly inconsistent.
      If the uid does not persist, then we will end up re-training/filtering
      the message, but I'm not sure what can be done about that.  There is
      mention of the UID validity value, which each folder has.  If the uids
      fail to persist, then this value will increase.  The RFC doesn't say
      if this is the *only* time it will increase, though.  I'm not sure
      if this value is of any use to us or not; it's worth keeping in mind,
      though.
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
import imaplib
import os
import re
import time
import sys
import getopt
import types
import email
from getpass import getpass
from email.Utils import parsedate

from spambayes.Options import options
from spambayes import tokenizer, storage, message, Dibbler
from spambayes.UserInterface import UserInterfaceServer
from spambayes.ImapUI import IMAPUserInterface

# global IMAPlib object
global imap
imap = None

CRLF_RE = re.compile(r'\r\n|\r|\n')

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
UID_RE = re.compile(r"(UID) ([\d]+)")
FETCH_RESPONSE_RE = re.compile(r"([0-9]+) \(([" + \
                               re.escape(FLAG_CHARS) + r"\"\{\}\(\)\\ ]*)\)?")
LITERAL_RE = re.compile(r"^\{[\d]+\}$")

def _extract_fetch_data(response):
    '''Extract data from the response given to an IMAP FETCH command.'''
    # response might be a tuple containing literal data
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
    # All others are ignored.
    for r in [FLAGS_RE, INTERNALDATE_RE, RFC822_RE, UID_RE]:
        mo = r.search(response)
        if mo is not None:
            if LITERAL_RE.match(mo.group(2)):
                data[mo.group(1)] = literal
            else:
                data[mo.group(1)] = mo.group(2)
    return data

class IMAPSession(imaplib.IMAP4):
    '''A class extending the IMAP4 class, with a few optimizations'''
    
    def __init__(self, server, port, debug=0, do_expunge=False):
        imaplib.Debug = debug  # this is a global in the imaplib module
        imaplib.IMAP4.__init__(self, server, port)
        # XXX We should check here to see if the server/port were valid
        # For efficiency, we remember which folder we are currently
        # in, and only send a select command to the IMAP server if
        # we want to *change* folders.  This function is used by
        # both IMAPMessage and IMAPFolder.
        self.current_folder = None
        self.do_expunge = do_expunge

    def login(self, uid, pw):
        try:
            imaplib.IMAP4.login(self, uid, pw)  # superclass login
        except imaplib.IMAP4.error, e:
            if str(e) == "permission denied":
                print "There was an error logging in to the IMAP server."
                print "The userid and/or password may be incorrect."
                sys.exit()
            else:
                raise
    
    def logout(self):
        # sign off
        if self.do_expunge:
            self.expunge()
        imaplib.IMAP4.logout(self)  # superclass logout
        
    def SelectFolder(self, folder):
        '''A method to point ensuing imap operations at a target folder'''
        if self.current_folder != None:
            if self.current_folder != folder:
                if self.do_expunge:
                    # It is faster to do close() than a single
                    # expunge when we log out (because expunge returns
                    # a list of all the deleted messages, that we don't do
                    # anything with)
                    imap.close()
            # We *always* use SELECT and not EXAMINE, because this
            # speeds things up considerably.
            response = self.select(folder, False)
            if response[0] != "OK":
                print "Invalid response to select %s:\n%s" % (folder,
                                                              response)
                sys.exit(-1)
            self.current_folder = folder
            return response

class IMAPMessage(message.SBHeaderMessage):
    def __init__(self):
        message.Message.__init__(self)
        self.folder = None
        self.previous_folder = None

    def setFolder(self, folder):
        self.folder = folder

    def _check(self, response, command):
        if response[0] != "OK":
            print "Invalid response to %s:\n%s" % (command, response)
            sys.exit(-1)

    def _force_CRLF(self, data):
        """Make sure data uses CRLF for line termination.
        """
        return CRLF_RE.sub('\r\n', data)

    def as_string(self):
        # The email package stores line endings in the "internal" Python
        # format ('\n').  It is up to whoever transmits that information to
        # convert to appropriate line endings (according to RFC822, that is
        # \r\n *only*).  imaplib *should* take care of this for us (in the
        # append function), but does not, so we do it here
        return self._force_CRLF(message.SBHeaderMessage.as_string(self))
        
    def extractTime(self):
        # When we create a new copy of a message, we need to specify
        # a timestamp for the message.  If the message has a date header
        # we use that.  Otherwise, we use the current time.
        message_date = self["Date"]
        if message_date is not None:
            parsed_date = parsedate(message_date)
            if parsed_date is not None:
                return imaplib.Time2Internaldate(time.mktime(parsed_date))
        else:
            return imaplib.Time2Internaldate(time.time())

    def MoveTo(self, dest):
        '''Note that message should move to another folder.  No move is
        carried out until Save() is called.'''
        # This move operation just changes where we think we are,
        # and we do an actual move on save (to avoid doing
        # this more than once)
        if self.previous_folder is None:
            self.previous_folder = self.folder
            self.folder = dest

    def Save(self):
        '''Save message to imap server.'''
        # we can't actually update the message with IMAP
        # so what we do is create a new message and delete the old one
        # we need to copy the flags as well
        if self.folder is None:
            raise RuntimeError, """Can't save a message that doesn't
            have a folder."""
        if self.id is None:
            raise RuntimeError, """Can't save a message that doesn't have
            an id."""
        response = imap.uid("FETCH", self.id, "(FLAGS INTERNALDATE)")
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
            flags = re.sub(r"\\Recent ?|\\ ?Recent", "", flags)
        else:
            flags = None

        # See searching for new uid comments below
        old_id = self.id
        self["X-Spambayes-IMAP-OldID"] = old_id

        response = imap.append(self.folder.name, flags,
                               msg_time, self.as_string())
        self._check(response, 'append')

        if self.previous_folder is None:
            imap.SelectFolder(self.folder.name)
        else:
            imap.SelectFolder(self.previous_folder.name)
            self.previous_folder = None
        response = imap.uid("STORE", old_id, "+FLAGS.SILENT", "(\\Deleted)")
        self._check(response, 'store')

        # We need to update the uid, as it will have changed
        # Searching for the new message is full of problems.  Searching for
        # the text sends far too much data through the connection, and
        # doesn't work reliably anyway.  We instead search for a special
        # header that we add for this explicit purpose.
        imap.SelectFolder(self.folder.name)
        response = imap.uid("SEARCH", "HEADER", "X-Spambayes-IMAP-OldID",
                            old_id)
        self._check(response, 'search')
        new_id = response[1][0]
        # This works with NetMail, but not with Courier.  Very strange,
        # and needs more examination.  For the moment, if the search
        # turns up empty, we make the very big assumption that the new
        # message is the last one with a recent flag
        if new_id == "":
            response = imap.uid("SEARCH", "RECENT")
            new_id = response[1][0]
            if new_id.find(' ') > -1:
                ids = new_id.split(' ')
                new_id = ids[-1]

        #XXX This code to delete the old message id from the message
        #XXX info db and manipulate the message id, is a *serious* hack.
        #XXX There's gotta be a better way to do this.
        message.msginfoDB._delState(self)
        self.id = new_id
        self.modified()

# This performs a similar function to email.message_from_string()
def imapmessage_from_string(s, _class=IMAPMessage, strict=False):
    return email.message_from_string(s, _class, strict)


class IMAPFolder(object):
    def __init__(self, folder_name, readOnly=True):
        self.name = folder_name
        self.rfc822_command = "RFC822.PEEK"

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

    def recent_keys(self):
        '''Returns uids for all the messages in the folder that
        are flagged as recent, but not flagged as deleted.'''
        imap.SelectFolder(self.name, True)
        response = imap.uid("SEARCH", "RECENT UNDELETED")
        self._check(response, "SEARCH RECENT UNDELETED")
        return response[1][0].split(' ')

    def keys(self):
        '''Returns uids for all the messages in the folder not
        marked as deleted.'''
        # request message range
        imap.SelectFolder(self.name)
        response = imap.uid("SEARCH", "UNDELETED")
        self._check(response, "SEARCH UNDELETED")
        if response[1][0] == "":
            return []
        return response[1][0].split(' ')

    def __getitem__(self, key):
        '''Return message matching the given uid'''
        imap.SelectFolder(self.name)
        # We really want to use RFC822.PEEK here, as that doesn't effect
        # the status of the message.  Unfortunately, it appears that not
        # all IMAP servers support this, even though it is in RFC1730
        response = imap.uid("FETCH", key, self.rfc822_command)
        if response[0] != "OK":
            self.rfc822_command = "RFC822"
            response = imap.uid("FETCH", key, self.rfc822_command)
        self._check(response, "uid fetch")
        data = _extract_fetch_data(response[1][0])
        messageText = data["RFC822"]

        # we return an instance of *our* message class, not the
        # raw rfc822 message
        msg = imapmessage_from_string(messageText)
        msg.setId(key)
        msg.setFolder(self)
        
        return msg
   
    def Train(self, classifier, isSpam):
        '''Train folder as spam/ham'''
        num_trained = 0
        for msg in self:
            if msg.GetTrained() == (not isSpam):
                classifier.unlearn(msg.asTokens(), not isSpam)
                # Once the message has been untrained, it's training memory
                # should reflect that on the off chance that for some reason
                # the training breaks, which happens on occasion (the
                # tokenizer is not yet perfect)
                msg.RememberTrained(None)

            if msg.GetTrained() is None:
                classifier.learn(msg.asTokens(), isSpam)
                num_trained += 1
                msg.RememberTrained(isSpam)

        return num_trained                

    def Filter(self, classifier, spamfolder, unsurefolder):
        for msg in self:
            if msg.GetClassification() is None:
                (prob, clues) = classifier.spamprob(msg.asTokens(),
                                                    evidence=True)
                # add headers and remember classification
                msg.addSBHeaders(prob, clues)

                cls = msg.GetClassification()
                if cls == options["Hammie", "header_ham_string"]:
                    # we leave ham alone
                    pass
                elif cls == options["Hammie", "header_spam_string"]:
                    msg.MoveTo(spamfolder)
                else:
                    msg.MoveTo(unsurefolder)

                msg.Save()

            
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
                    print "       %s trained." % (num_ham_trained)

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
                    print "       %s trained." % (num_spam_trained)

        if total_ham_trained or total_spam_trained:
            self.classifier.store()
        
        if options["globals", "verbose"]:
            print "Training took %s seconds, %s messages were trained" \
                  % (time.time() - t, total_ham_trained + total_spam_trained)

    def Filter(self):
        if options["globals", "verbose"]:
            t = time.time()

        # Select the spam folder and unsure folder to make sure they exist
        imap.SelectFolder(self.spam_folder.name)
        imap.SelectFolder(self.unsure_folder.name)
            
        for filter_folder in options["imap", "filter_folders"]:
            # Select the folder to make sure it exists
            imap.SelectFolder(filter_folder)
            folder = IMAPFolder(filter_folder, False)
            folder.Filter(self.classifier, self.spam_folder,
                          self.unsure_folder)
 
        if options["globals", "verbose"]:
            print "Filtering took", time.time() - t, "seconds."

 
def run():
    global imap
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hbtcvpl:e:i:d:D:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    bdbname = options["pop3proxy", "persistent_storage_file"]
    useDBM = options["pop3proxy", "persistent_use_database"]
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
        elif opt == '-d':
            useDBM = False
            bdbname = arg
        elif opt == '-D':
            useDBM = True
            bdbname = arg
        elif opt == "-b":
            launchUI = True
        elif opt == '-t':
            doTrain = True
        elif opt == '-p':
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

    if not (doClassify or doTrain or launchUI):
        print "-b, -c, or -t operands must be specified."
        print "Please use the -h operand for help."
        sys.exit()

    if (launchUI and (doClassify or doTrain)):
        print """
-b option is exclusive with -c and -t options.
The user interface will be launched, but no classification
or training will be performed."""

    bdbname = os.path.expanduser(bdbname)
    
    if options["globals", "verbose"]:
        print "Loading database %s..." % (bdbname),
    
    if useDBM:
        classifier = storage.DBDictClassifier(bdbname)
    else:
        classifier = storage.PickledClassifier(bdbname)

    if options["globals", "verbose"]:
        print "Done."            

    if options["imap", "server"]:
        # The options class is ahead of us here:
        #   it knows that imap:server will eventually be able to have
        #   multiple values, but for the moment, we just use the first one
        server = options["imap", "server"][0]
        username = options["imap", "username"][0]
        pwd = options["imap", "password"][0]
    else:
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
    if launchUI:
        if server != "":
            imap = IMAPSession(server, port, imapDebug, doExpunge)
        httpServer = UserInterfaceServer(options["html_ui", "port"])
        httpServer.register(IMAPUserInterface(classifier, imap, pwd))
        Dibbler.run(launchBrowser=launchUI)
    else:
        imap = IMAPSession(server, port, imapDebug, doExpunge)
        while True:
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
