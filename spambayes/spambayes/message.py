#! /usr/bin/env python

"""message.py - Core Spambayes classes.

Classes:
    Message - an email.Message.Message, extended with spambayes methods
    SBHeaderMessage - A Message with spambayes header manipulations
    MessageInfoDB - persistent state storage for Message

Abstract:

    MessageInfoDB is a simple shelve persistency class for the persistent
    state of a Message obect.  The MessageInfoDB currently does not provide
    iterators, but should at some point.  This would allow us to, for
    example, see how many messages have been trained differently than their
    classification, for fp/fn assessment purposes.

    Message is an extension of the email package Message class, to
    include persistent message information. The persistent state
    currently consists of the message id, its current classification, and
    its current training.  The payload is not persisted.

    SBHeaderMessage extends Message to include spambayes header specific
    manipulations.

Usage:
    A typical classification usage pattern would be something like:

    >>> import email
    >>> # substance comes from somewhere else
    >>> msg = email.message_from_string(substance, _class=SBHeaderMessage)
    >>> id = msg.setIdFromPayload()

    >>> if id is None:
    >>>     msg.setId(time())   # or some unique identifier

    >>> msg.delSBHeaders()      # never include sb headers in a classification

    >>> # bayes object is your responsibility
    >>> (prob, clues) = bayes.spamprob(msg.asTokens(), evidence=True)

    >>> msg.addSBHeaders(prob, clues)


    A typical usage pattern to train as spam would be something like:

    >>> import email
    >>> # substance comes from somewhere else
    >>> msg = email.message_from_string(substance, _class=SBHeaderMessage)
    >>> id = msg.setId(msgid)     # id is a fname, outlook msg id, something...

    >>> msg.delSBHeaders()        # never include sb headers in a train

    >>> if msg.getTraining() == False:   # could be None, can't do boolean test
    >>>     bayes.unlearn(msg.asTokens(), False)  # untrain the ham

    >>> bayes.learn(msg.asTokens(), True) # train as spam
    >>> msg.rememberTraining(True)


To Do:
    o Suggestions?
"""

# This module is part of the spambayes project, which is Copyright 2002-5
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

import os
import sys
import types
import math
import re
import errno
import shelve
import warnings
try:
    import cPickle as pickle
except ImportError:
    import pickle
import traceback

import email
import email.Message
import email.Parser
import email.Header

from spambayes import storage
from spambayes import dbmstorage
from spambayes.Options import options, get_pathname_option
from spambayes.tokenizer import tokenize

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

CRLF_RE = re.compile(r'\r\n|\r|\n')

class MessageInfoBase(object):
    def __init__(self, db_name):
        self.db_name = db_name

    def __len__(self):
        return len(self.db)

    def load_msg(self, msg):
        if self.db is not None:
            try:
                try:
                    attributes = self.db[msg.getDBKey()]
                except pickle.UnpicklingError:
                    # The old-style Outlook message info db didn't use
                    # shelve, so get it straight from the dbm.
                    if hasattr(self, "dbm"):
                        attributes = self.dbm[msg.getDBKey()]
                    else:
                        raise
            except KeyError:
                # Set to None, as it's not there.
                for att in msg.stored_attributes:
                    # Don't overwrite.
                    if not hasattr(msg, att):
                        setattr(msg, att, None)
            else:
                if not isinstance(attributes, types.ListType):
                    # Old-style message info db
                    if isinstance(attributes, types.TupleType):
                        # sb_server/sb_imapfilter, which only handled
                        # storing 'c' and 't'.
                        (msg.c, msg.t) = attributes
                        return
                    elif isinstance(attributes, types.StringTypes):
                        # Outlook plug-in, which only handled storing 't',
                        # and did it as a string.
                        msg.t = {"0" : False, "1" : True}[attributes]
                        return
                    else:
                        print >> sys.stderr, "Unknown message info type"
                        sys.exit(1)
                for att, val in attributes:
                    setattr(msg, att, val)

    def store_msg(self, msg):
        if self.db is not None:
            attributes = []
            for att in msg.stored_attributes:
                attributes.append((att, getattr(msg, att)))
            self.db[msg.getDBKey()] = attributes
            self.store()

    def remove_msg(self, msg):
        if self.db is not None:
            del self.db[msg.getDBKey()]
            self.store()

class MessageInfoPickle(MessageInfoBase):
    def __init__(self, db_name, pickle_type=1):
        MessageInfoBase.__init__(self, db_name)
        self.mode = pickle_type
        self.load()

    def load(self):
        try:
            fp = open(self.db_name, 'rb')
        except IOError, e:
            if e.errno == errno.ENOENT:
                # New pickle
                self.db = {}
            else:
                raise
        else:
            self.db = pickle.load(fp)
            fp.close()

    def close(self):
        # we keep no resources open - nothing to do
        pass

    def store(self):
        fp = open(self.db_name, 'wb')
        pickle.dump(self.db, fp, self.mode)
        fp.close()

class MessageInfoDB(MessageInfoBase):
    def __init__(self, db_name, mode='c'):
        MessageInfoBase.__init__(self, db_name)
        self.mode = mode
        self.load()

    def load(self):
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

    def __del__(self):
        self.close()

    def close(self):
        # Close our underlying database.  Better not assume all databases
        # have close functions!
        def noop(): pass
        getattr(self.db, "close", noop)()
        getattr(self.dbm, "close", noop)()

    def store(self):
        if self.db is not None:
            self.db.sync()

# values are classifier class, True if it accepts a mode
# arg, and True if the argument is a pathname
_storage_types = {"dbm" : (MessageInfoDB, True, True),
                  "pickle" : (MessageInfoPickle, False, True),
##                  "pgsql" : (MessageInfoPG, False, False),
##                  "mysql" : (MessageInfoMySQL, False, False),
##                  "cdb" : (MessageInfoCDB, False, True),
##                  "zodb" : (MessageInfoZODB, False, True),
##                  "zeo" : (MessageInfoZEO, False, False),
                  }

def open_storage(data_source_name, db_type="dbm", mode=None):
    """Return a storage object appropriate to the given parameters."""
    try:
        klass, supports_mode, unused = _storage_types[db_type]
    except KeyError:
        raise storage.NoSuchClassifierError(db_type)
    if supports_mode and mode is not None:
        return klass(data_source_name, mode)
    else:
        return klass(data_source_name)

def database_type():
    dn = ("Storage", "messageinfo_storage_file")
    # The storage options here may lag behind those in storage.py,
    # so we try and be more robust.  If we can't use the same storage
    # method, then we fall back to pickle.
    nm, typ = storage.database_type((), default_name=dn)
    if typ not in _storage_types.keys():
        typ = "pickle"
    return nm, typ


class Message(email.Message.Message):
    '''An email.Message.Message extended for SpamBayes'''

    def __init__(self):
        email.Message.Message.__init__(self)

        # persistent state
        nm, typ = database_type()
        self.message_info_db = open_storage(nm, typ)
        self.stored_attributes = ['c', 't',]
        self.getDBKey = self.getId
        self.id = None
        self.c = None
        self.t = None

        # non-persistent state includes all of email.Message.Message state

    # This function (and it's hackishness) can be avoided by using
    # email.message_from_string(text, _class=SBHeaderMessage)
    # i.e. instead of doing this:
    #   >>> msg = spambayes.message.SBHeaderMessage()
    #   >>> msg.setPayload(substance)
    # you do this:
    #   >>> msg = email.message_from_string(substance, _class=SBHeaderMessage)
    # imapfilter has an example of this in action
    def setPayload(self, payload):
        """DEPRECATED.

        This function does not work (as a result of using private
        methods in a hackish way) in Python 2.4, so is now deprecated.
        Use *_from_string as described above.

        More: Python 2.4 has a new email package, and the private functions
        are gone.  So this won't even work.  We have to do something to
        get this to work, for the 1.0.x branch, so use a different ugly
        hack.
        """
        warnings.warn("setPayload is deprecated. Use " \
                      "email.message_from_string(payload, _class=" \
                      "Message) instead.",
                      DeprecationWarning, 2)
        new_me = email.message_from_string(payload, _class=Message)
        self.__dict__ = new_me.__dict__

    def setId(self, id):
        if self.id and self.id != id:
            raise ValueError, "MsgId has already been set, cannot be changed"

        if id is None:
            raise ValueError, "MsgId must not be None"

        if not type(id) in types.StringTypes:
            raise TypeError, "Id must be a string"

        self.id = id
        self.message_info_db.load_msg(self)

    def getId(self):
        return self.id

    def tokenize(self):
        return tokenize(self)

    def _force_CRLF(self, data):
        """Make sure data uses CRLF for line termination."""
        return CRLF_RE.sub('\r\n', data)

    def as_string(self, unixfrom=False):
        # The email package stores line endings in the "internal" Python
        # format ('\n').  It is up to whoever transmits that information to
        # convert to appropriate line endings (according to RFC822, that is
        # \r\n *only*).  imaplib *should* take care of this for us (in the
        # append function), but does not, so we do it here
        try:
            return self._force_CRLF(\
                email.Message.Message.as_string(self, unixfrom))
        except TypeError:
            parts = []
            for part in self.get_payload():
                parts.append(email.Message.Message.as_string(part, unixfrom))
            return self._force_CRLF("\n".join(parts))

    def modified(self):
        if self.id:    # only persist if key is present
            self.message_info_db.store_msg(self)

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
    '''Message class that is cognizant of SpamBayes headers.
    Adds routines to add/remove headers for SpamBayes'''
    def setPayload(self, payload):
        """DEPRECATED.
        """
        warnings.warn("setPayload is deprecated. Use " \
                      "email.message_from_string(payload, _class=" \
                      "SBHeaderMessage) instead.",
                      DeprecationWarning, 2)
        new_me = email.message_from_string(payload, _class=SBHeaderMessage)
        self.__dict__ = new_me.__dict__

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
            disp = "%.*f" % (options["Headers", "header_score_digits"], prob)
            if options["Headers", "header_score_logarithm"]:
                if prob<=0.005 and prob>0.0:
                    x=-math.log10(prob)
                    disp += " (%d)"%x
                if prob>=0.995 and prob<1.0:
                    x=-math.log10(1.0-prob)
                    disp += " (%d)"%x
            self[options['Headers','score_header_name']] = disp

        if options['Headers','include_thermostat']:
            thermostat = '**********'
            self[options['Headers','thermostat_header_name']] = \
                               thermostat[:int(prob*10)]

        if options['Headers','include_evidence']:
            hco = options['Headers','clue_mailheader_cutoff']
            sco = 1 - hco
            evd = []
            for word, score in clues:
                if (word == '*H*' or word == '*S*' \
                    or score <= hco or score >= sco):
                    if isinstance(word, types.UnicodeType):
                        word = email.Header.Header(word,
                                                   charset='utf-8').encode()
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

        if options['Headers','add_unique_id']:
            self[options['Headers','mailid_header_name']] = self.id

        self.addNotations()            

    def addNotations(self):
        """Add the appropriate string to the subject: and/or to: header.

        This is a reasonably ugly method of including the classification,
        but no-one has a better idea about how to allow filtering in
        'stripped down' mailers (i.e. Outlook Express), so, for the moment,
        this is it.
        """
        disposition = self.GetClassification()
        # options["Headers", "notate_to"] (and notate_subject) can be
        # either a single string (like "spam") or a tuple (like
        # ("unsure", "spam")).  In Python 2.3 checking for a string in
        # something that could be a string or a tuple works fine, but
        # it dies in Python 2.2, because you can't do 'string in string',
        # only 'character in string', so we allow for that.
        if isinstance(options["Headers", "notate_to"], types.StringTypes):
            notate_to = (options["Headers", "notate_to"],)
        else:
            notate_to = options["Headers", "notate_to"]
        if disposition in notate_to:
            # Once, we treated the To: header just like the Subject: one,
            # but that doesn't really make sense - and OE stripped the
            # comma that we added, treating it as a separator, so it
            # wasn't much use anyway.  So we now convert the classification
            # to an invalid address, and add that.
            address = "%s@spambayes.invalid" % (disposition, )
            try:
                self.replace_header("To", "%s,%s" % (address, self["To"]))
            except KeyError:
                self["To"] = address

        if isinstance(options["Headers", "notate_subject"], types.StringTypes):
            notate_subject = (options["Headers", "notate_subject"],)
        else:
            notate_subject = options["Headers", "notate_subject"]
        if disposition in notate_subject:
            try:
                self.replace_header("Subject", "%s,%s" % (disposition,
                                                          self["Subject"]))
            except KeyError:
                self["Subject"] = disposition

    def delNotations(self):
        """If present, remove our notation from the subject: and/or to:
        header of the message.

        This is somewhat problematic, as we cannot be 100% positive that we
        added the notation.  It's almost certain to be us with the to:
        header, but someone else might have played with the subject:
        header.  However, as long as the user doesn't turn this option on
        and off, this will all work nicely.

        See also [ 848365 ] Remove subject annotations from message review
                            page
        """
        subject = self["Subject"]
        ham = options["Headers", "header_ham_string"] + ','
        spam = options["Headers", "header_spam_string"] + ','
        unsure = options["Headers", "header_unsure_string"] + ','
        if options["Headers", "notate_subject"]:
            for disp in (ham, spam, unsure):
                if subject.startswith(disp):
                    self.replace_header("Subject", subject[len(disp):])
                    # Only remove one, maximum.
                    break
        to = self["To"]
        ham = "%s@spambayes.invalid," % \
              (options["Headers", "header_ham_string"],)
        spam = "%s@spambayes.invalid," % \
               (options["Headers", "header_spam_string"],)
        unsure = "%s@spambayes.invalid," % \
                 (options["Headers", "header_unsure_string"],)
        if options["Headers", "notate_to"]:
            for disp in (ham, spam, unsure):
                if to.startswith(disp):
                    self.replace_header("To", to[len(disp):])
                    # Only remove one, maximum.
                    break

    def currentSBHeaders(self):
        """Return a dictionary containing the current values of the
        SpamBayes headers.  This can be used to restore the values
        after using the delSBHeaders() function."""
        headers = {}
        for header_name in [options['Headers','classification_header_name'],
                            options['Headers','mailid_header_name'],
                            options['Headers','classification_header_name'] + "-ID",
                            options['Headers','thermostat_header_name'],
                            options['Headers','evidence_header_name'],
                            options['Headers','score_header_name'],
                            options['Headers','trained_header_name'],
                            ]:
            value = self[header_name]
            if value is not None:
                headers[header_name] = value
        return headers

    def delSBHeaders(self):
        del self[options['Headers','classification_header_name']]
        del self[options['Headers','mailid_header_name']]
        del self[options['Headers','classification_header_name'] + "-ID"]  # test mode header
        del self[options['Headers','thermostat_header_name']]
        del self[options['Headers','evidence_header_name']]
        del self[options['Headers','score_header_name']]
        del self[options['Headers','trained_header_name']]
        # Also delete notations - typically this is called just before
        # training, and we don't want them there for that.
        self.delNotations()

# Utility function to insert an exception header into the given RFC822 text.
# This is used by both sb_server and sb_imapfilter, so it's handy to have
# it available separately.
def insert_exception_header(string_msg, msg_id=None):
    """Insert an exception header into the given RFC822 message (as text).

    Returns a tuple of the new message text and the exception details."""
    stream = StringIO.StringIO()
    traceback.print_exc(None, stream)
    details = stream.getvalue()

    # Build the header.  This will strip leading whitespace from
    # the lines, so we add a leading dot to maintain indentation.
    detailLines = details.strip().split('\n')
    dottedDetails = '\n.'.join(detailLines)
    headerName = 'X-Spambayes-Exception'
    header = email.Header.Header(dottedDetails, header_name=headerName)

    # Insert the exception header, and optionally also insert the id header,
    # otherwise we might keep doing this message over and over again.
    # We also ensure that the line endings are /r/n as RFC822 requires.
    try:
        headers, body = re.split(r'\n\r?\n', string_msg, 1)
    except ValueError:
        # No body - this is a bad message!
        headers = string_msg
        body = ""
    header = re.sub(r'\r?\n', '\r\n', str(header))
    headers += "\n%s: %s\r\n" % (headerName, header)
    if msg_id:
        headers += "%s: %s\r\n" % \
                   (options["Headers", "mailid_header_name"], msg_id)
    return (headers + body, details)
