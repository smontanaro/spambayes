#!/usr/bin/env python

from __future__ import generators

"""An IMAP filter.  An IMAP message box is scanned and all non-scored
messages are scored and (where necessary) filtered.

It is suggested that this filter is set to run at certain intervals.
Note that it is (currently) fairly slow, so this should not be too
often.  An alternative to this would be to keep the filter running
and logged in, and periodically check for new mail.

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
            -e          : sets expunge to the *opposite* of options.imap_expunge
            -i debuglvl : a somewhat mysterious imaplib debugging level

Examples:

    Classify inbox, with dbm database
        imapfilter -c -D bayes.db
        
    Train Spam and Ham, then classify inbox, with dbm database
        imapfilter -t -c -D bayes.db

    Train Spam and Ham only, with pickled database
        imapfilter -t -d bayes.db
 
To Do:
    o Remove old msg from info database when saveing modified messages
    o Use DELETE rather than storing //DELETED flag when saving modified messages
    o Web UI for configuration and setup. # Tony thinks it would be
        nice if there was a web ui to this for the initial setup (i.e. like
        pop3proxy), which offered a list of folders to filter/train/etc.  It
        could then record a uid for the folder rather than a name, and it
        avoids the problems with different imap servers having different
        naming styles a list is retrieved via imap.list()
    o Suggestions?
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
__credits__ = "Tim Stone, All the Spambayes folk."

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
import email.Parser

from spambayes.Options import options
from spambayes import tokenizer, storage, message

# global IMAPlib object
imap = None

class IMAPMessage(message.SBHeaderMessage):
    # response checking is necessary throughout this class
    def __init__(self, folder, id):        
        message.Message.__init__(self)

        self.id = id
        self.folder = folder
        self.previous_folder = None

    def _check(self, response, command):
        if response[0] != "OK":
            print "Invalid response to %s:\n%s" % (command, response)
            sys.exit(-1)

    def extractTime(self):
        # When we create a new copy of a message, we need to specify
        # a timestamp for the message.  Ideally, this would be the
        # timestamp from the message itself, but for the moment, we
        # just use the current time.
        #XXX the imaplib time function returns a string like
        #XXX "12-Apr-2003 19:56:28 -0500"  This seems like a bad message id.
        #XXX For one thing, it only resolves to one second.  Even a cheap
        #XXX refractor telescope can resolve better than that ;)
#        return imaplib.Time2Internaldate(time.time())
        return time.time()

    def MoveTo(self, dest):
        # The move just changes where we think we are,
        # and we do an actual move on save (to avoid doing
        # this more than once)
        if self.previous_folder is None:
            self.previous_folder = self.folder
            self.folder = dest

    def Save(self):
        # we can't actually update the message with IMAP
        # so what we do is create a new message and delete the old one
        new_id = self.extractTime()
        response = imap.append(self.folder.name, None,
                               new_id, self.as_string())
        self._check(response, 'append')
        # we need to update the uid, as it will have changed
        # XXX there will be problems here if the message *has not*
        # XXX changed, as the message to be deleted will be found first
        # XXX (if they are in the same folder)
        #response = imap.uid("SEARCH", "(TEXT)", self.as_string())
        #self._check(response, 'search')
        #self.id = response[1][0]

        old_id = self.id
        self.id = new_id
        if self.previous_folder is not None:
            response = imap.select(self.previous_folder.name, False)
            self._check(response, 'folder select')
            self.previous_folder = None
            response = imap.uid("STORE", old_id, "+FLAGS.SILENT", "(\\Deleted)")
            self._check(response, 'store')

            #XXX We really should delete the old message from the msgid db.
            #XXX There is currently no interface to do this with.


class IMAPFolder(object):
    # response checking is necessary throughout this class
    def __init__(self, folder_name, readOnly=True):
        self.name = folder_name
        # Convert folder name to a uid
        self.uid = None
        response = imap.select(self.name, readOnly)
        responses = imap.response("OK")[1]
        for response in responses:
            if response[:13] == "[UIDVALIDITY ":
                r = re.compile(r"(?P<uid>\d+)")
                self.uid = r.search(response[13:]).group('uid')
        # We really want to use RFC822.PEEK here, as that doesn't effect
        # the status of the message.  Unfortunately, it appears that not
        # all IMAP servers support this, even though it is in RFC1730
        self.rfc822_command = "(RFC822.PEEK)"
        response = imap.fetch("1:1", self.rfc822_command)
        if response[0] != "OK":
            self.rfc822_command = "(RFC822)"

    def Select(self):
        imap.select(self.name, False)
        self._check(folder, 'select')

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

    def keys(self):
        '''Returns uids for all the messages in the folder'''
        # request message range
        response = imap.select(self.name, True)
        total_messages = response[1][0]
        if total_messages == '0':
            return []
        response = imap.fetch("1:" + total_messages, "UID")
        r = re.compile(r"[0-9]+ \(UID ([0-9]+)\)")
        uids = []
        for i in response[1]:
            mo = r.match(i)
            if mo is not None:
                uids.append(mo.group(1))
        return uids

    def __getitem__(self, key):
        '''Return message matching the given uid'''
        response = imap.uid("FETCH", key, self.rfc822_command)
        messageText = response[1][0][1]
        # we return an instance of *our* message class, not the
        # raw rfc822 message

        msg = IMAPMessage(self, key)
        msg.setPayload(messageText)
        
        return msg

    def Train(self, classifier, isSpam):
        '''Train folder as spam/ham'''
        num_trained = 0
        for msg in self:
            if msg.GetTrained() == isSpam:
                classifier.unlearn(msg.asTokens(), not isSpam)
                # Once the message has been untrained, it's training memory
                # should reflect that on the off chance that for some reason
                # the training breaks, which happens on occasion (the
                # tokenizer is not yet perfect)
                msg.RememberTrained(None)

            if msg.GetTrained() is not None:
                classifier.learn(msg.asTokens(), isSpam)
                num_trained += 1
                msg.RememberTrained(isSpam)

        return num_trained                

    def Filter(self, classifier, spamfolder, unsurefolder):
        for msg in self:
            if msg.GetClassification() is None:
                (prob, clues) = classifier.spamprob(msg.asTokens(), evidence=True)
                # add headers and remember classification
                msg.addSBHeaders(prob, clues)

                cls = msg.GetClassification()
                if cls == options.header_ham_string:
                    # we leave ham alone
                    pass
                elif cls == options.header_spam_string:
                    msg.MoveTo(spamfolder)
                else:
                    msg.MoveTo(unsurefolder)

                msg.Save()
            
class IMAPFilter(object):
    def __init__(self, classifier):
        global imap
        imap = imaplib.IMAP4(options.imap_server, options.imap_port)

        self.Login(options.imap_username, options.imap_password)
        
        self.spam_folder = IMAPFolder(options.imap_spam_folder)
        self.unsure_folder = IMAPFolder(options.imap_unsure_folder)

        self.classifier = classifier
        
    def Train(self):
        if options.verbose:
            t = time.time()

        if options.imap_ham_train_folders != "":
            ham_training_folders = options.imap_ham_train_folders.split()
            for fol in ham_training_folders:
                folder = IMAPFolder(fol)
                num_ham_trained = folder.Train(self.classifier, False)

        if options.imap_spam_train_folders != "":
            spam_training_folders = options.imap_spam_train_folders.split(' ' )
            for fol in spam_training_folders:
                folder = IMAPFolder(fol)
                num_spam_trained = folder.Train(self.classifier, True)

        if num_ham_trained or num_spam_trained:
            self.classifier.store()
        
        if options.verbose:
            print "Training took %s seconds, %s messages were trained" \
                  % (time.time() - t, num_ham_trained + num_spam_trained)

    def Filter(self):
        if options.verbose:
            t = time.time()
            
        for filter_folder in options.imap_filter_folders.split():
            folder = IMAPFolder(filter_folder, False)
            folder.Filter(self.classifier, self.spam_folder, self.unsure_folder)
 
        if options.verbose:
            print "Filtering took", time.time() - t, "seconds."

    def Login(self, uid, pw):
        try:
            lgn = imap.login(uid, pw)
        except imaplib.IMAP4.error, e:
            if str(e) == "permission denied":
                print "There was an error logging in to the IMAP server."
                print "The userid and/or password may be in error."
                sys.exit()
            else:
                raise
    
    def Logout(self, expunge):
        # sign off
        if expunge:
            imap.expunge()
        imap.logout()

 
if __name__ == '__main__':

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'htcvei:d:D:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    bdbname = options.pop3proxy_persistent_storage_file
    useDBM = options.pop3proxy_persistent_use_database
    doTrain = False
    doClassify = False
    doExpunge = options.imap_expunge
    imapDebug = 0

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
        elif opt == '-t':
            doTrain = True
        elif opt == '-c':
            doClassify = True
        elif opt == '-v':
            options.verbose = True
        elif opt == '-e':
            doExpunge = not doExpunge
        elif opt == '-i:':
            imapDebug = int(arg)


    bdbname = os.path.expanduser(bdbname)
    
    if options.verbose:
        print "Loading database %s..." % (bdbname),
    
    if useDBM:
        classifier = storage.DBDictClassifier(bdbname)
    else:
        classifier = storage.PickledClassifier(bdbname)

    if options.verbose:
        print "Done."            
                
    imap_filter = IMAPFilter(classifier)
    imap.debug = imapDebug

    if doTrain:
        imap_filter.Train()
    if doClassify:
        imap_filter.Filter()
        
    imap_filter.Logout(doExpunge)
