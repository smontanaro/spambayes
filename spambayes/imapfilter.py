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
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
__credits__ = "Tim Stone, All the Spambayes folk."

# Tony thinks it would be nice if there was a web ui to
# this for the initial setup (i.e. like pop3proxy), which offered
# a list of folders to filter/train/etc.  It could then record a
# uid for the folder rather than a name, and it avoids the problems
# with different imap servers having different naming styles
# a list is retrieved via imap.list()

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

from spambayes.Options import options
from spambayes import tokenizer, storage, message

# global IMAPlib object
imap = None

class IMAPMessage(message.Message):
    # response checking is necessary throughout this class
    def __init__(self, folder_id, folder_name, message_id):
        message.Message.__init__(self)
        self.setId(message_id)
        self.folder_id = folder_id
        self.folder_name = folder_name

    def extractTime(self):
        # When we create a new copy of a message, we need to specify
        # a timestamp for the message.  Ideally, this would be the
        # timestamp from the message itself, but for the moment, we
        # just use the current time.
        return imaplib.Time2Internaldate(time.time())

    def Update(self):
        # we can't actually update the message with IMAP
        # so what we do is create a new message and delete the old one
        response = imap.append(self.folder_name, None,
                               self.extractTime(), self.get_payload())
        response = imap.select(self.folder_name, False)
        response = imap.uid("STORE", self.getId(), "+FLAGS.SILENT",
                                 "(\\Deleted)")
        # we need to update the uid, as it will have changed
        response = imap.uid("SEARCH", "(TEXT)", self.get_payload())
        self.changeId(response[1][0])


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
        msg = IMAPMessage(self.uid, self.name, key)
        msg.setPayload(messageText)
        return msg
       

class IMAPFilter(object):
    def __init__(self):
        global imap
        imap = imaplib.IMAP4(options.imap_server, options.imap_port)
        if options.verbose:
            print "Loading database...",
        filename = options.pop3proxy_persistent_storage_file
        filename = os.path.expanduser(filename)
        if options.pop3proxy_persistent_use_database:
            self.classifier = storage.DBDictClassifier(filename)
        else:
            self.classifier = storage.PickledClassifier(filename)
        if options.verbose:
            print "Done."

    def _check(self, response, command):
        if response[0] != "OK":
            print "Invalid response to %s:\n%s" % (command, response)
            sys.exit(-1)

    def _selectFolder(self, name, read_only):
        folder = imap.select(name, read_only)
        self._check(folder, 'select')
        return folder

    def Login(self):
        lgn = imap.login(options.imap_username, options.imap_password)
        self._check(lgn, 'login')

    def TrainFolder(self, folder_name, isSpam):
        folder = IMAPFolder(folder_name)
        for msg in folder:
            if msg.isTrained():
                if msg.isTrndAs(isSpam):
                    # already trained, nothing for us to do here
                    # (we don't want to train the same message twice)
                    continue
                if msg.isTrained():
                    self.classifier.unlearn(msg.asTokens(), not isSpam)
            self.classifier.learn(msg.asTokens(), isSpam)
            msg.trndAs(isSpam)

    def Train(self):
        if options.verbose:
            t = time.time()
        if options.imap_ham_train_folders != "":
            ham_training_folders = options.imap_ham_train_folders.split()
            for fol in ham_training_folders:
                self.TrainFolder(fol, False)
        if options.imap_spam_train_folders != "":
            spam_training_folders = options.imap_spam_train_folders.split(' ' )
            for fol in spam_training_folders:
                self.TrainFolder(fol, True)
        self.classifier.store()
        if options.verbose:
            print "Training took", time.time() - t, "seconds."

    def Filter(self):
        if options.verbose:
            t = time.time()
        for filter_folder in options.imap_filter_folders.split():
            folder = IMAPFolder(filter_folder, False)
            for msg in folder:
                (prob, clues) = self.classifier.spamprob(msg.asTokens(),
                                                         evidence=True)
                # add headers and remember classification
                msg.addSBHeaders(prob, clues)
                # XXX updating is disabled for the moment
                # msg.Update()
                self._filterMessage(msg)
        if options.verbose:
            print "Filtering took", time.time() - t, "seconds."

    def Logout(self):
        # sign off
        if options.imap_expunge:
            imap.expunge()
        imap.logout()

    def _extractTimeFromMessage(self, msg):
        # When we create a new copy of a message, we need to specify
        # a timestamp for the message.  Ideally, this would be the
        # timestamp from the message itself, but for the moment, we
        # just use the current time.
        return imaplib.Time2Internaldate(time.time())

    def _moveMessage(self, old_msg, dest):
        # The IMAP copy command makes an alias, not a whole new
        # copy, so what we need to do (sigh) is create a new message
        # in the correct folder, and delete the old one
        # XXX (someone tell me if this is wrong)
        response = imap.uid("FETCH", old_msg.getId(), "(RFC822)")
        self._check(response, 'uid fetch')
        msg = message.Message()
        msg.setPayload(response[1][0][1])
        #response = imap.uid("SEARCH", "(TEXT)", msg.get_payload())
        #self._check(response, "search")
        #self.changeId(response[1][0])

        response = imap.append(dest, None,
                               self._extractTimeFromMessage(msg),
                               msg.get_payload())
        self._check(response, "append")
        self._selectFolder(old_msg.folder_name, False)
        response = imap.uid("STORE", old_msg.getId(), "+FLAGS.SILENT",
                            "(\\Deleted)")
        self._check(response, "uid store")

    def _filterMessage(self, msg):
        if msg.isClsfdHam():
            # we leave ham alone
            print "untouched"
            pass
        elif msg.isClsfdSpam():
            self._moveMessage(msg, options.imap_spam_folder)
        else:
            self._moveMessage(msg, options.imap_unsure_folder)

if __name__ == '__main__':
    options.verbose = True
    imap_filter = IMAPFilter()
#    imap_filter.imap.debug = 10
    imap_filter.Login()
    imap_filter.Train()
    imap_filter.Filter()
    imap_filter.Logout()
