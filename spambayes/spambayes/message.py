#! /usr/bin/env python

'''message.py - Core Spambayes classes.

Classes:
    Message - an email.Message.Message, extended with spambayes methods
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
    
    Message is an extension of the email package Message class, to include
    persistent message information and Spambayes specific header manipulations.
    The persistent state -currently- consists of the message id, its current
    classification, and its current training.  The payload is not persisted.
    Payload persistence is left to whatever mail client software is being used.
    
Usage:
    A typical classification usage pattern would be something like:
    
    >>>msg = spambayes.message.Message()
    >>>msg.setPayload(substance) # substance comes from somewhere else
    >>>id = msg.setIdFromPayload()
    
    >>>if id is None:
    >>>    msg.setId(time())   # or some unique identifier
     
    >>>msg.delSBHeaders()      # never include sb headers in a classification
    
    >>># bayes object is your responsibility   
    >>>(prob, clues) = bayes.spamprob(msg.asTokens(), evidence=True)

    >>>msg.addSBHeaders(prob, clues)
    
    
    A typical usage pattern to train as spam would be something like:
    
    >>>msg = spambayes.message.Message()
    >>>msg.setPayload(substance) # substance comes from somewhere else
    >>>id = msg.setId(msgid)     # id is a fname, outlook msg id, something...

    >>>msg.delSBHeaders()        # never include sb headers in a train
    
    >>>if msg.isTrndHam():
    >>>    bayes.unlearn(msg.asTokens(), False)  # untrain the ham
    
    >>>bayes.learn(msg.asTokens(), True) # train as spam
    >>>msg.trndAsSpam()
    

To Do:
    o Master DB module
    o Suggestions?

    '''

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

import email.Message
import email.Parser

from spambayes.tokenizer import tokenize
from spambayes.Options import options

from cStringIO import StringIO

from spambayes import dbmstorage
import shelve

# XXX Tim, what do you want to do here?  This
# XXX recurses infinately at the moment
# Make shelve use binary pickles by default.
#oldShelvePickler = shelve.Pickler
#def binaryDefaultPickler(f, binary=1):
#    return oldShelvePickler(f, binary)
#shelve.Pickler = binaryDefaultPickler


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
            return self.db[msg.getId()]
        except KeyError:
            return None

    def _setState(self, msg):
        self.db[msg.getId()] = msg

    def _delState(self, msg):
        del self.db[msg.getId()]
        
# this should come from a mark hammond idea of a master db
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

        
    def setPayload(self, payload):
        prs = email.Parser.HeaderParser()
        prs._parseheaders(self, StringIO(payload))
        # we may want to do some header parsing error handling here
        # to try to extract important headers regardless of malformations
        prs._parsebody(self, StringIO(payload))
        
    def setIdFromPayload(self):
        try:
            self.setId(self[options.pop3proxy_mailid_header_name])
        except KeyError:
            return None

        return self.id

    def changeID(self, id):
        # We cannot re-set an id (see below).  However there are
        # occasionally times when the id for a message will change,
        # for example, on an IMAP server (or possibly an exchange
        # server), the server may change the ids that we are using
        # We enforce that this must be an explicit *change* rather
        # than simply re-setting, by having this as a separate
        # function
        if not self.id:
            raise ValueError, "MsgID has not been set, cannot be changed"
        self._setId(id)
    
    def setId(self, id):
        if self.id:
            raise ValueError, "MsgId has already been set, cannot be changed"
        self._setId(id)

    def _setId(self, id):    
        # we should probably enforce type(id) is StringType.
        # the database will insist upon it, but at that point, it's harder
        # to diagnose
        if id is None:
            raise ValueError, "MsgId must not be None"
            
        self.id = id
        msginfoDB._getState(self)
        
    def getId(self):
        return self.id

    def copy(self, old_msg):
        self.setPayload(old_msg.payload())  # this is expensive...
        self.setClassification(old_msg.getClassification())
        self.setTraining(old_msg.getTraining())
        
    def addSBHeaders(self, prob, clues):
        '''Add hammie header, and remember message's classification.  Also,
        add optional headers if needed.'''
        
        if prob < options.ham_cutoff:
            disposition = options.header_ham_string
            self.clsfyAsHam()
        elif prob > options.spam_cutoff:
            disposition = options.header_spam_string
            self.clsfyAsSpam()
        else:
            disposition = options.header_unsure_string
            self.clsfyAsUnsure()

        self[options.hammie_header_name] = disposition
        
        if options.pop3proxy_include_prob:
            self[options.pop3proxy_prob_header_name] = prob
            
        if options.pop3proxy_include_thermostat:
            thermostat = '**********'
            self[options.pop3proxy_thermostat_header_name] = \
                               thermostat[:int(prob*10)]
                               
        if options.pop3proxy_include_evidence:
            evd = "; ".join(["%r: %.2f" % (word, score)
                     for word, score in clues
                     if (word[0] == '*' or
                         score <= options.clue_mailheader_cutoff or
                         score >= 1.0 - options.clue_mailheader_cutoff)])
                         
            self[options.pop3proxy_evidence_header_name] = evd
        
        if options.pop3proxy_add_mailid_to.find("header") != -1:
            self[options.pop3proxy_mailid_header_name] = self.id

# This won't work for now, because email.Message does not isolate message body
# This is also not consistent with the function of this method...
#        if options.pop3proxy_add_mailid_to.find("body") != -1:
#            body = body[:len(body)-3] + \
#                   options.pop3proxy_mailid_header_name + ": " \
#                    + messageName + "\r\n.\r\n"


    def delSBHeaders(self):
        del self[options.hammie_header_name]
        del self[options.pop3proxy_mailid_header_name]
        del self[options.hammie_header_name + "-ID"]  # test mode header
        del self[options.pop3proxy_prob_header_name]
        del self[options.pop3proxy_thermostat_header_name]
        del self[options.pop3proxy_evidence_header_name]
    
    def asTokens(self):
        # use as_string() here because multipart/digest will return
        # a list of message objects if get_payload() is used
        return tokenize(self.as_string())
        
    def modified(self):
        if self.id:    # only persist if key is present
            msginfoDB._setState(self)
        
    def isClsfdSpam(self):
        return self.c == 's'
        
    def isClsfdHam(self):
        return self.c == 'h'
        
    def isClsfdUnsure(self):
        return self.c == 'u'
        
    def isClassified(self):
        return not self.c is None
        
    def clsfyAsSpam(self):
        self.c = 's'
        self.modified()
        
    def clsfyAsHam(self):
        self.c = 'h'
        self.modified()
        
    def clsfyAsUnsure(self):
        self.c = 'u'
        self.modified()
    
    def getClassification(self):
        return self.c

    def setClassification(self, cls):
        if cls == 's' or cls == 'h' or cls == 'u' or cls is None:
            self.c = cls
            self.modified()
        else:
            raise ValueError
        
    def isTrndSpam(self):
        return self.t == 's'
        
    def isTrndHam(self):
        return self.t == 'h'
    
    def trndAsSpam(self):
        self.t = 's'
        self.modified()
        
    def trndAsHam(self):
        self.t = 'h'
        self.modified()
        
    def isTrndAs(self, isSpam):
        if self.t == 'h' and not isSpam:
            return True
        if self.t == 's' and isSpam:
            return True
        return False

    def trndAs(self, isSpam):
        if isSpam:
            self.t = 's'
        else:
            self.t = 'h'

    def notTrained(self):
        self.t = None
        self.modified()
        
    def isTrained(self):
        return not self.t is None
    
    def getTraining(self):
        return self.t

    def setTraining(self, trn):
        if trn == 's' or trn == 'h' or trn is None:
            self.t = trn
            self.modified()
        else:
            raise ValueError
         
    def __repr__(self):
        return "core.Message%r" % repr(self.__getstate__())

    def __getstate__(self):
        return (self.id, self.c, self.t)

    def __setstate__(self, t):
        (self.id, self.c, self.t) = t