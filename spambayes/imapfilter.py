#!/usr/bin/env python

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
__credits__ = "All the Spambayes folk."

# This code will benefit immensely from
# (a) The new message class, which can hold information such as
#     whether a message has been seen before
# (b) The new header stuff, which will abstract out adding all
#     the headers

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

from spambayes.Options import options
from spambayes import tokenizer, storage

class IMAPFilter(object):
    def __init__(self):
        self.imap = imaplib.IMAP4(options.imap_server, options.imap_port)
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
        # Unique names for cached messages - see getNewMessageName() below.
        self.lastBaseMessageName = ''
        self.uniquifier = 2

    def Login(self):
        lgn = self.imap.login(options.imap_username, options.imap_password)
        self._check(lgn, 'login')

    def _check(self, response, command):
        if response[0] != "OK":
            print "Invalid response to %s:\n%s" % (command, response)
            sys.exit(-1)

    def _getUIDs(self, low, high):
        # Retreive a list of uids corresponding to the given range
        if high < low: return []
        # request message range
        range = str(low) + ":" + str(high)
        res = self.imap.fetch(range, "UID")
        self._check(res, 'fetch')
        r = re.compile(r"[0-9]+ \(UID ([0-9]+)\)")
        res2 = []
        for i in res[1]:
            mo = r.match(i)
            if mo is not None:
                res2.append(mo.group(1))
        return res2

    def getNewMessageName(self):
        # The message name is the time it arrived, with a uniquifier
        # appended if two arrive within one clock tick of each other.
        # (This is completely taken from the same function in pop3proxy's
        # State class.)
        messageName = "%10.10d" % long(time.time())
        if messageName == self.lastBaseMessageName:
            messageName = "%s-%d" % (messageName, self.uniquifier)
            self.uniquifier += 1
        else:
            self.lastBaseMessageName = messageName
            self.uniquifier = 2
        return messageName

    def _selectFolder(self, name, read_only):
        folder = self.imap.select(name, read_only)
        self._check(folder, 'select')
        return folder

    def RetrieveMessage(self, uid):
        response = self.imap.uid("FETCH", uid, "(RFC822.PEEK)")
        self._check(response, 'uid fetch')
        try:
            messageText = response[1][0][1]
        except:
            print "Could not retrieve message (id %s)" % uid
            messageText = ""

        msg = spambayes.message.Message()
        msg.setPayload(messageText)
        msg.setId(uid)

        msg.delSBHeaders()  # never include sb headers in a train
                
        return msg

    def TrainFolder(self, folder_name, isSpam):
        response = self._selectFolder(folder_name, True)
        uids = self._getUIDs(1, int(response[1][0]))
        for uid in uids:
            msg = self.RetrieveMessage(uid)

            if msg.isTrained():
                if isSpam and msg.isTrndHam():
                    bayes.unlearn(msg.asTokens(), False)  # untrain the ham
                elif not isSpam and msg.isTrndSpam():
                    bayes.unlearn(msg.asTokens(), True)
                
            bayes.learn(msg.asTokens(), isSpam) # train as spam

            if isSpam:
                msg.trndAsSpam()
            else:
                msg.trndAsHam()

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
        inbox = self._selectFolder(options.imap_inbox, False)
        # the number of messages are returned
        # get all the corresponding UIDs
        uids = self._getUIDs(1, int(inbox[1][0]))
        
        for uid in uids:
            msg = self.RetrieveMessage(uid)
            (prob, clues) = self.classifier.spamprob(msg.asTokens(), evidence=True)
            msg.addSBHeaders(prob, clues) # adds headers and remembers classification
            self._updateMessage(msg)
            self._filterMessage(msg)
        if options.verbose:
            print "Filtering took", time.time() - t, "seconds."

    def Logout(self):
        # sign off
        if options.imap_expunge:
            self.imap.expunge()
        self.imap.logout()

    def _updateMessage(self, msg):
        # we can't actually update the message with IMAP
        # XXX (someone tell me if this is wrong!)
        # so what we do is create a new message and delete the old one
        # we return the new uid, which we obtain by searching for the
        # spambayes id
        res = self.imap.append(options.imap_inbox, None,
                               self._extractTimeFromMessage(msg),
                               msg.payload())
        self._check(res, "append")
        res = self.imap.uid("STORE", msg.getId(), "+FLAGS.SILENT", "(\\Deleted)")
        self._check(res, "uid store")
        res = self.imap.uid("SEARCH", "(TEXT)", msg.payload())
        self._check(res, "uid search")
        return res[1][0]

    def _extractTimeFromMessage(self, msg):
        # When we create a new copy of a message, we need to specify
        # a timestamp for the message.  Ideally, this would be the
        # timestamp from the message itself, but for the moment, we
        # just use the current time.
        return imaplib.Time2Internaldate(time.time())

    def _moveMessage(self, msg, dest):
        # The IMAP copy command makes an alias, not a whole new
        # copy, so what we need to do (sigh) is create a new message
        # in the correct folder, and delete the old one
        # XXX (someone tell me if this is wrong, too!)
        response = self.imap.uid("FETCH", msg.getId(), "(RFC822.PEEK)")
        self._check(response, 'uid fetch')

        msg = spambayes.message.Message()
        msg.setPayload(response[1][0][1])
        msg.setId(_extractTimeFromMessage(msg))

        response = self.imap.append(dest, None, msg.getId(), msg.payload())
        self._check(response, "append")
        res = self.imap.uid("STORE", msg.getId(), "+FLAGS.SILENT", "(\\Deleted)")
        self._check(response, "uid store")

    def _filterMessage(self, msg, prob):
        if msg.isClsfdHam():
            # we leave ham alone
            pass
        elif msg.isClsfdSpam():
            self._moveMessage(msg, options.imap_spam_folder)
        else:
            self._moveMessage(msg, options.imap_unsure_folder)

if __name__ == '__main__':
    options.verbose = True
    imap_filter = IMAPFilter()
    imap_filter.Login()
    imap_filter.Train()
    imap_filter.Filter()
    imap_filter.Logout()
