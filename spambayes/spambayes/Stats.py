#! /usr/bin/env python

"""Stats.py - Spambayes statistics class.

Classes:
    Stats - provides statistical information about previous activity.

Abstract:

    Provide statistics on the activity that spambayes has done - for
    example the number of messages classified as each type, and the
    number of messages trained as each type.  This information is
    retrieved from the messageinfo database, so is as reliable as that
    is <wink>.

To Do:
    o People would like pretty graphs, so maybe that could be done.
    o People have requested time-based statistics - mail per hour,
      spam per hour, and so on.
    o The possible stats to show are pretty much endless.  Some to
      consider would be: percentage of mail that is fp/fn/unsure,
      percentage of mail correctly classified.
    o Suggestions?

"""

# This module is part of the spambayes project, which is Copyright 2002-4
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
__credits__ = "Kenny Pitt, Mark Hammond, all the spambayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

import types

from spambayes.message import msginfoDB

class Stats(object):
    class __empty_msg:
        def getId(self):
            return self.id

    def __init__(self):
        self.CalculateStats()

    def Reset(self):
        self.cls_spam = 0
        self.cls_ham = 0
        self.cls_unsure = 0
        self.trn_spam = 0
        self.trn_ham = 0
        self.trn_unsure_ham = 0
        self.trn_unsure_spam = 0
        self.fp = 0
        self.fn = 0
        self.total = 0

    def CalculateStats(self):
        self.Reset()
        for msg in msginfoDB.db.keys():
            self.total += 1
            m = self.__empty_msg()
            m.id = msg
            msginfoDB._getState(m)
            if m.c == 's':
                # Classified as spam.
                self.cls_spam += 1
                if m.t == False:
                    # False positive (classified as spam, trained as ham)
                    self.fp += 1
            elif m.c == 'h':
                # Classified as ham.
                self.cls_ham += 1
                if m.t == True:
                    # False negative (classified as ham, trained as spam)
                    self.fn += 1
            elif m.c == 'u':
                # Classified as unsure.
                self.cls_unsure += 1
                if m.t == False:
                    self.trn_unsure_ham += 1
                elif m.t == True:
                    self.trn_unsure_spam += 1
            if m.t == True:
                self.trn_spam += 1
            elif m.t == False:
                self.trn_ham += 1

    def GetStats(self, use_html=True):
        if self.total == 0:
            return ["SpamBayes has processed zero messages"]
        chunks = []
        push = chunks.append
        not_trn_unsure = self.cls_unsure - self.trn_unsure_ham - \
                         self.trn_unsure_spam
        if self.cls_unsure:
            unsure_ham_perc = 100.0 * self.trn_unsure_ham / self.cls_unsure
            unsure_spam_perc = 100.0 * self.trn_unsure_spam / self.cls_unsure
            unsure_not_perc = 100.0 * not_trn_unsure / self.cls_unsure
        else:
            unsure_ham_perc = 0.0 # Not correct, really!
            unsure_spam_perc = 0.0 # Not correct, really!
            unsure_not_perc = 0.0 # Not correct, really!
        if self.trn_ham:
            trn_perc_unsure_ham = 100.0 * self.trn_unsure_ham / \
                                  self.trn_ham
            trn_perc_fp = 100.0 * self.fp / self.trn_ham
            trn_perc_ham = 100.0 - (trn_perc_unsure_ham + trn_perc_fp)
        else:
            trn_perc_ham = 0.0 # Not correct, really!
            trn_perc_unsure_ham = 0.0 # Not correct, really!
            trn_perc_fp = 0.0 # Not correct, really!
        if self.trn_spam:
            trn_perc_unsure_spam = 100.0 * self.trn_unsure_spam / \
                                   self.trn_spam
            trn_perc_fn = 100.0 * self.fn / self.trn_spam
            trn_perc_spam = 100.0 - (trn_perc_unsure_spam + trn_perc_fn)
        else:
            trn_perc_spam = 0.0 # Not correct, really!
            trn_perc_unsure_spam = 0.0 # Not correct, really!
            trn_perc_fn = 0.0 # Not correct, really!
        format_dict = {
            'num_seen' : self.total,
            'correct' : self.total - (self.cls_unsure + self.fp + self.fn),
            'incorrect' : self.cls_unsure + self.fp + self.fn,
            'unsure_ham_perc' : unsure_ham_perc,
            'unsure_spam_perc' : unsure_spam_perc,
            'unsure_not_perc' : unsure_not_perc,
            'not_trn_unsure' : not_trn_unsure,
            'trn_total' : (self.trn_ham + self.trn_spam + \
                           self.trn_unsure_ham + self.trn_unsure_spam),
            'trn_perc_ham' : trn_perc_ham,
            'trn_perc_unsure_ham' : trn_perc_unsure_ham,
            'trn_perc_fp' : trn_perc_fp,
            'trn_perc_spam' : trn_perc_spam,
            'trn_perc_unsure_spam' : trn_perc_unsure_spam,
            'trn_perc_fn' : trn_perc_fn,
            }
        format_dict.update(self.__dict__)

        # Add percentages of everything.
        for key, val in format_dict.items():
            perc_key = "perc_" + key
            if self.total and isinstance(val, types.IntType):
                format_dict[perc_key] = 100.0 * val / self.total
            else:
                format_dict[perc_key] = 0.0 # Not correct, really!

        # Figure out plurals
        for num, key in [("num_seen", "sp1"),
                         ("correct", "sp2"),
                         ("incorrect", "sp3"),
                         ("fp", "sp4"),
                         ("fn", "sp5"),
                         ("trn_unsure_ham", "sp6"),
                         ("trn_unsure_spam", "sp7"),
                         ("not_trn_unsure", "sp8"),
                         ("trn_total", "sp9"),
                         ]:
            if format_dict[num] == 1:
                format_dict[key] = ''
            else:
                format_dict[key] = 's'
        for num, key in [("correct", "wp1"),
                         ("incorrect", "wp2"),
                         ("not_trn_unsure", "wp3"),
                         ]:
            if format_dict[num] == 1:
                format_dict[key] = 'was'
            else:
                format_dict[key] = 'were'
        # Possibly use HTML for breaks/tabs.
        if use_html:
            format_dict["br"] = "<br/>"
            format_dict["tab"] = "&nbsp;&nbsp;&nbsp;&nbsp;"
        else:
            format_dict["br"] = "\r\n"
            format_dict["tab"] = "\t"

##        Our result should look something like this:
##        (devised by Mark Moraes and Kenny Pitt)
##
##        SpamBayes has classified a total of 1223 messages:
##            827 ham (67.6% of total)
##            333 spam (27.2% of total)
##            63 unsure (5.2% of total)
##
##        1125 messages were classified correctly (92.0% of total)
##        35 messages were classified incorrectly (2.9% of total)
##            0 false positives (0.0% of total)
##            35 false negatives (2.9% of total)
##
##        6 unsures trained as ham (9.5% of unsures)
##        56 unsures trained as spam (88.9% of unsures)
##        1 unsure was not trained (1.6% of unsures)
##
##        A total of 760 messages have been trained:
##            346 ham (98.3% ham, 1.7% unsure, 0.0% false positives)
##            414 spam (78.0% spam, 13.5% unsure, 8.5% false negatives)

        push("SpamBayes has classified a total of " \
             "%(num_seen)d message%(sp1)s:" \
             "%(br)s%(tab)s%(cls_ham)d " \
             "(%(perc_cls_ham).0f%% of total) good" \
             "%(br)s%(tab)s%(cls_spam)d " \
             "(%(perc_cls_spam).0f%% of total) spam" \
             "%(br)s%(tab)s%(cls_unsure)d " \
             "(%(perc_cls_unsure).0f%% of total) unsure." % \
             format_dict)
        push("%(correct)d message%(sp2)s %(wp1)s classified correctly " \
             "(%(perc_correct).0f%% of total)" \
             "%(br)s%(incorrect)d message%(sp3)s %(wp2)s classified " \
             "incorrectly " \
             "(%(perc_incorrect).0f%% of total)" \
             "%(br)s%(tab)s%(fp)d false positive%(sp4)s " \
             "(%(perc_fp).0f%% of total)" \
             "%(br)s%(tab)s%(fn)d false negative%(sp5)s " \
             "(%(perc_fn).0f%% of total)" % \
             format_dict)
        push("%(trn_unsure_ham)d unsure%(sp6)s trained as good " \
             "(%(unsure_ham_perc).0f%% of unsures)" \
             "%(br)s%(trn_unsure_spam)d unsure%(sp7)s trained as spam " \
             "(%(unsure_spam_perc).0f%% of unsures)" \
             "%(br)s%(not_trn_unsure)d unsure%(sp8)s %(wp3)s not trained " \
             "(%(unsure_not_perc).0f%% of unsures)" % \
             format_dict)
        push("A total of %(trn_total)d message%(sp9)s have been trained:" \
             "%(br)s%(tab)s%(trn_ham)d good " \
             "(%(trn_perc_ham)0.f%% good, %(trn_perc_unsure_ham)0.f%% " \
             "unsure, %(trn_perc_fp).0f%% false positives)" \
             "%(br)s%(tab)s%(trn_spam)d spam " \
             "(%(trn_perc_spam)0.f%% spam, %(trn_perc_unsure_spam)0.f%% " \
             "unsure, %(trn_perc_fn).0f%% false negatives)" % \
             format_dict)
        return chunks


if __name__=='__main__':
    s = Stats()
    print "\n".join(s.GetStats())
