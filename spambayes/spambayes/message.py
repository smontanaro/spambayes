#! /usr/bin/env python

"""message.py - Core Spambayes classes.

Classes:
    Message - an email.Message.Message, extended with spambayes methods
    SBHeaderMessage - A Message with spambayes header manipulations
    MessageInfoDB - persistent state storage for Message

Abstract:

    MessageInfoDB is a simple shelve persistency class for the persistent
    state of a Message obect.  For the moment, the db name is hard-coded,
    but we'll have to do this a different way.  Mark Hammond's idea is to
    have a master database, that simply keeps track of the names and instances
    of other databases, such as the wordinfo and msginfo databases.  The
    MessageInfoDB currently does not provide iterators, but should at some
    point.  This would allow us to, for example, see how many messages
    have been trained differently than their classification, for fp/fn
    assessment purposes.

    Message is an extension of the email package Message class, to
    include persistent message information. The persistent state
    -currently- consists of the message id, its current
    classification, and its current training.  The payload is not
    persisted. Payload persistence is left to whatever mail client
    software is being used.

    SBHeaderMessage extends Message to include spambayes header specific
    manipulations.

Usage:
    A typical classification usage pattern would be something like:

    >>> msg = spambayes.message.SBHeaderMessage()
    >>> msg.setPayload(substance) # substance comes from somewhere else
    >>> id = msg.setIdFromPayload()

    >>> if id is None:
    >>>     msg.setId(time())   # or some unique identifier

    >>> msg.delSBHeaders()      # never include sb headers in a classification

    >>> # bayes object is your responsibility
    >>> (prob, clues) = bayes.spamprob(msg.asTokens(), evidence=True)

    >>> msg.addSBHeaders(prob, clues)


    A typical usage pattern to train as spam would be something like:

    >>> msg = spambayes.message.SBHeaderMessage()
    >>> msg.setPayload(substance) # substance comes from somewhere else
    >>> id = msg.setId(msgid)     # id is a fname, outlook msg id, something...

    >>> msg.delSBHeaders()        # never include sb headers in a train

    >>> if msg.getTraining() == False:   # could be None, can't do boolean test
    >>>     bayes.unlearn(msg.asTokens(), False)  # untrain the ham

    >>> bayes.learn(msg.asTokens(), True) # train as spam
    >>> msg.rememberTraining(True)


To Do:
    o Master DB module, or at least make the msginfodb name an options parm
    o Figure out how to safely add message id to body (or if it can be done
      at all...)
    o Suggestions?

    """

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tim Stone <tim@fourstonesExpressions.com>"
__credits__ = "Mark Hammond, Tony Meyer, all the spambayes contributors."

from __future__ import generators

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0
    def bool(val):
        return not not val

import sys
import os
import types
import re

import email            # for message_from_string
import email.Message
import email.Parser

from spambayes.tokenizer import tokenize
from spambayes.Options import options

from cStringIO import StringIO

from spambayes import dbmstorage
import shelve

CRLF_RE = re.compile(r'\r\n|\r|\n')

class MessageInfoDB:
    def __init__(self, db_name, mode='c'):
        self.mode = mode
        self.db_name = db_name
        try:
            self.dbm = dbmstorage.open(self.db_name, self.mode)
            self.db = shelve.Shelf(self.dbm)
        except dbmstorage.error:
            # This probably means that we don't have a dbm module
            # available.  Print out a warning, and continue on
            # (not persisting any of this data).
            if options["globals", "verbose"]:
                print "Warning: no dbm modules available for MessageInfoDB"
            self.dbm = self.db = None

    def store(self):
        if self.db is not None:
            self.db.sync()

    def _getState(self, msg):
        if self.db is not None:
            try:
                (msg.c, msg.t) = self.db[msg.getId()]
            except KeyError:
                pass

    def _setState(self, msg):
        if self.db is not None:
            self.db[msg.getId()] = (msg.c, msg.t)

    def _delState(self, msg):
        if self.db is not None:
            del self.db[msg.getId()]

# This should come from a Mark Hammond idea of a master db
# For the moment, we get the name of another file from the options,
# so that these files don't litter lots of working directories.
# Once there is a master db, this option can be removed.
message_info_db_name = options["Storage", "messageinfo_storage_file"]
message_info_db_name = os.path.expanduser(message_info_db_name)
msginfoDB = MessageInfoDB(message_info_db_name)

class Message(email.Message.Message):
    '''An email.Message.Message extended for Spambayes'''

    def __init__(self):
        email.Message.Message.__init__(self)

        # persistent state
        self.id = None
        self.c = None
        self.t = None

        # non-persistent state includes all of email.Message.Message state

    # This function (and it's hackishness) can be avoided by using the
    # message_from_string and sbheadermessage_from_string functions
    # at the end of the module.  i.e. instead of doing this:
    #   >>> msg = spambayes.message.SBHeaderMessage()
    #   >>> msg.setPayload(substance)
    # you do this:
    #   >>> msg = sbheadermessage_from_string(substance)
    # imapfilter has an example of this in action
    def setPayload(self, payload):
        prs = email.Parser.Parser()
        fp = StringIO(payload)
        # this is kindof a hack, due to the fact that the parser creates a
        # new message object, and we already have the message object
        prs._parseheaders(self, fp)
        # we may want to do some header parsing error handling here
        # to try to extract important headers regardless of malformations
        prs._parsebody(self, fp)

    def setId(self, id):
        if self.id:
            raise ValueError, "MsgId has already been set, cannot be changed"

        if id is None:
            raise ValueError, "MsgId must not be None"

        if not type(id) in types.StringTypes:
            raise TypeError, "Id must be a string"

        self.id = id
        msginfoDB._getState(self)

    def getId(self):
        return self.id

    def asTokens(self):
        return tokenize(self.as_string())

    def _force_CRLF(self, data):
        """Make sure data uses CRLF for line termination."""
        return CRLF_RE.sub('\r\n', data)

    def as_string(self):
        # The email package stores line endings in the "internal" Python
        # format ('\n').  It is up to whoever transmits that information to
        # convert to appropriate line endings (according to RFC822, that is
        # \r\n *only*).  imaplib *should* take care of this for us (in the
        # append function), but does not, so we do it here
        return self._force_CRLF(email.Message.Message.as_string(self))

    def modified(self):
        if self.id:    # only persist if key is present
            msginfoDB._setState(self)

    def GetClassification(self):
        if self.c == 's':
            return options['Headers','header_spam_string']
        elif self.c == 'h':
            return options['Headers','header_ham_string']
        elif self.c == 'u':
            return options['Headers','header_unsure_string']
        return None

    def RememberClassification(self, cls):
        # this must store state independent of options settings, as they
        # may change, which would really screw this database up

        if cls == options['Headers','header_spam_string']:
            self.c = 's'
        elif cls == options['Headers','header_ham_string']:
            self.c = 'h'
        elif cls == options['Headers','header_unsure_string']:
            self.c = 'u'
        else:
            raise ValueError, \
                  "Classification must match header strings in options"
        self.modified()

    def GetTrained(self):
        return self.t

    def RememberTrained(self, isSpam):
        # isSpam == None means no training has been done
        self.t = isSpam
        self.modified()

    def __repr__(self):
        return "spambayes.message.Message%r" % repr(self.__getstate__())

    def __getstate__(self):
        return (self.id, self.c, self.t)

    def __setstate__(self, t):
        (self.id, self.c, self.t) = t


class SBHeaderMessage(Message):
    '''Message class that is cognizant of Spambayes headers.
    Adds routines to add/remove headers for Spambayes'''

    def __init__(self):
        Message.__init__(self)

    def setIdFromPayload(self):
        try:
            self.setId(self[options['Headers','mailid_header_name']])
        except ValueError:
            return None

        return self.id

    def addSBHeaders(self, prob, clues):
        """Add hammie header, and remember message's classification.  Also,
        add optional headers if needed."""

        if prob < options['Categorization','ham_cutoff']:
            disposition = options['Headers','header_ham_string']
        elif prob > options['Categorization','spam_cutoff']:
            disposition = options['Headers','header_spam_string']
        else:
            disposition = options['Headers','header_unsure_string']
        self.RememberClassification(disposition)
        self[options['Headers','classification_header_name']] = disposition

        if options['Headers','include_score']:
            self[options['Headers','score_header_name']] = str(prob)

        if options['Headers','include_thermostat']:
            thermostat = '**********'
            self[options['Headers','thermostat_header_name']] = \
                               thermostat[:int(prob*10)]

        if options['Headers','include_evidence']:
            hco = options['Headers','clue_mailheader_cutoff']
            sco = 1 - hco
            evd = []
            for word, score in clues:
                if (word[0] == '*' or score <= hco or score >= sco):
                    evd.append("%r: %.2f" % (word, score))

            # Line-wrap this header, because it can get very long.  We don't
            # use email.Header.Header because that can explode with unencoded
            # non-ASCII characters.  We can't use textwrap because that's 2.3.
            wrappedEvd = []
            headerName = options['Headers','evidence_header_name']
            lineLength = len(headerName) + len(': ')
            for component, index in zip(evd, range(len(evd))):
                wrappedEvd.append(component)
                lineLength += len(component)
                if index < len(evd)-1:
                    if lineLength + len('; ') + len(evd[index+1]) < 78:
                        wrappedEvd.append('; ')
                    else:
                        wrappedEvd.append(';\n\t')
                        lineLength = 8
            self[headerName] = "".join(wrappedEvd)

        # These are pretty ugly, but no-one has a better idea about how to
        # allow filtering in 'stripped down' mailers like Outlook Express,
        # so for the moment, they stay in.
        if disposition in options["pop3proxy", "notate_to"]:
            try:
                self.replace_header("To", "%s,%s" % (disposition,
                                                     self["To"]))
            except KeyError:
                self["To"] = disposition

        if disposition in options["pop3proxy", "notate_subject"]:
            try:
                self.replace_header("Subject", "%s,%s" % (disposition,
                                                          self["Subject"]))
            except KeyError:
                self["Subject"] = disposition

        if options['Headers','add_unique_id']:
            self[options['Headers','mailid_header_name']] = self.id

    def delSBHeaders(self):
        del self[options['Headers','classification_header_name']]
        del self[options['Headers','mailid_header_name']]
        del self[options['Headers','classification_header_name'] + "-ID"]  # test mode header
        del self[options['Headers','thermostat_header_name']]
        del self[options['Headers','evidence_header_name']]
        del self[options['Headers','score_header_name']]
        del self[options['Headers','trained_header_name']]

# These perform similar functions to email.message_from_string()
def message_from_string(s, _class=Message, strict=False):
    return email.message_from_string(s, _class, strict)

def sbheadermessage_from_string(s, _class=SBHeaderMessage, strict=False):
    return email.message_from_string(s, _class, strict)
