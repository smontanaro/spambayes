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

# This module is part of the spambayes project, which is Copyright 2002
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

class MessageInfoDB:
    def __init__(self, db_name, mode='c'):
        self.mode = mode
        self.db_name = db_name
        self.dbm = dbmstorage.open(self.db_name, self.mode)
        self.db = shelve.Shelf(self.dbm)

    def store(self):
        self.db.sync()

    def _getState(self, msg):
        try:
            (msg.c, msg.t) = self.db[msg.getId()]
        except KeyError:
            pass

    def _setState(self, msg):
        self.db[msg.getId()] = (msg.c, msg.t)

    def _delState(self, msg):
        del self.db[msg.getId()]
        
# this should come from a Mark Hammond idea of a master db
msginfoDB = MessageInfoDB("spambayes.messageinfo.db")

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

    def modified(self):
        if self.id:    # only persist if key is present
            msginfoDB._setState(self)

    def GetClassification(self):
        if self.c == 's':
            return options['Hammie','header_spam_string']
        if self.c == 'h':
            return options['Hammie','header_ham_string']
        if self.c == 'u':
            return options['Hammie','header_unsure_string']

        return None

    def RememberClassification(self, cls):
        # this must store state independent of options settings, as they
        # may change, which would really screw this database up

        if cls == options['Hammie','header_spam_string']:
            self.c = 's'
        elif cls == options['Hammie','header_ham_string']:
            self.c = 'h'
        elif cls == options['Hammie','header_unsure_string']:
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
            self.setId(self[options['pop3proxy','mailid_header_name']])
        except KeyError:
            return None

        return self.id

    def addSBHeaders(self, prob, clues):
        '''Add hammie header, and remember message's classification.  Also,
        add optional headers if needed.'''
        
        if prob < options['Categorization','ham_cutoff']:
            disposition = options['Hammie','header_ham_string']
        elif prob > options['Categorization','spam_cutoff']:
            disposition = options['Hammie','header_spam_string']
        else:
            disposition = options['Hammie','header_unsure_string']
        self.RememberClassification(disposition)
        self[options['Hammie','header_name']] = disposition
        
        if options['pop3proxy','include_prob']:
            self[options['pop3proxy','prob_header_name']] = prob
            
        if options['pop3proxy','include_thermostat']:
            thermostat = '**********'
            self[options['pop3proxy','thermostat_header_name']] = \
                               thermostat[:int(prob*10)]
                               
        if options['pop3proxy','include_evidence']:
            hco = options['Hammie','clue_mailheader_cutoff']
            sco = 1 - hco
            evd = []
            for word, score in clues:
                if (word[0] == '*' or score <= hco or score >= sco):
                    evd.append("%r: %.2f" % (word, score))
            self[options['pop3proxy','evidence_header_name']] = "; ".join(evd)
        
        if "header" in options['pop3proxy','add_mailid_to']:
            self[options['pop3proxy','mailid_header_name']] = self.id

# This won't work for now, because email.Message does not isolate message body
# This is also not consistent with the function of this method...
#        if options.pop3proxy_add_mailid_to.find("body") != -1:
#            body = body[:len(body)-3] + \
#                   options.pop3proxy_mailid_header_name + ": " \
#                    + messageName + "\r\n.\r\n"

    def delSBHeaders(self):
        del self[options['Hammie','header_name']]
        del self[options['pop3proxy','mailid_header_name']]
        del self[options['Hammie','header_name' + "-ID"]]  # test mode header
        del self[options['pop3proxy','prob_header_name']]
        del self[options['pop3proxy','thermostat_header_name']]
        del self[options['pop3proxy','evidence_header_name']]

# These perform similar functions to email.message_from_string()
def message_from_string(s, _class=Message, strict=False):
    return email.message_from_string(s, _class, strict)

def sbheadermessage_from_string(s, _class=SBHeaderMessage, strict=False):
    return email.message_from_string(s, _class, strict)
