#! /usr/bin/env python

"""Stats.py - SpamBayes statistics class.

Classes:
    Stats - provides statistical information about previous activity.

Abstract:

    Provide statistics on the activity that spambayes has done - for
    example the number of messages classified as each type, and the
    number of messages trained as each type.  This information is
    retrieved from the messageinfo database, so is as reliable as that
    is <wink>.

    This class provides information for both the web interface, the
    Outlook plug-in, and sb_pop3dnd.

To Do:
    o People would like pretty graphs, so maybe that could be done.
    o People have requested time-based statistics - mail per hour,
      spam per hour, and so on.
      Discussion on spambayes-dev indicated that this would be a lot
      of work for not much gain; however, since we now have some
      time data stored, it wouldn't be too bad, so maybe it can go in.
    o Suggestions?
"""

# This module is part of the spambayes project, which is Copyright 2002-5
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
__credits__ = "Kenny Pitt, Mark Hammond, all the spambayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

import time
import types

from spambayes.message import STATS_START_KEY
from spambayes.message import database_type, open_storage, Message

try:
    _
except NameError:
    _ = lambda arg: arg

class Stats(object):
    def __init__(self, options, messageinfo_db):
        self.messageinfo_db = messageinfo_db
        self.options = options
        # Reset session stats.
        self.Reset()
        # Load persistent stats.
        self.from_date = self.messageinfo_db.get_statistics_start_date()
        self.CalculatePersistentStats()

    def Reset(self):
        self.num_ham = self.num_spam = self.num_unsure = 0
        self.num_trained_spam = self.num_trained_spam_fn  = 0
        self.num_trained_ham = self.num_trained_ham_fp = 0

    def ResetTotal(self, permanently=False):
        self.totals = {}
        for stat in ["num_ham", "num_spam", "num_unsure",
                     "num_trained_spam", "num_trained_spam_fn",
                     "num_trained_ham", "num_trained_ham_fp",]:
            self.totals[stat] = 0
        if permanently:
            # Reset the date.
            self.from_date = time.time()
            self.messageinfo_db.set_statistics_start_date(self.from_date)

    def RecordClassification(self, score):
        if score >= self.options["Categorization", "spam_cutoff"]:
            self.num_spam += 1
        elif score >= self.options["Categorization", "ham_cutoff"]:
            self.num_unsure += 1
        else:
            self.num_ham += 1

    def RecordTraining(self, as_ham, old_score):
        if as_ham:
            self.num_trained_ham += 1
            # If we are recovering an item that is in the "spam" threshold,
            # then record it as a "false positive"
            if old_score > self.options["Categorization", "spam_cutoff"]:
                self.num_trained_ham_fp += 1
        else:
            self.num_trained_spam += 1
            # If we are deleting as Spam an item that was in our "good"
            # range, then record it as a false negative.
            if old_score < self.options["Categorization", "ham_cutoff"]:
                self.num_trained_spam_fn += 1

    def CalculatePersistentStats(self):
        """Calculate the statistics totals (i.e. not this session).

        This is done by running through the messageinfo database and
        adding up the various information.  This could get quite time
        consuming if the messageinfo database gets very large, so
        some consideration should perhaps be made about what to do
        then.
        """
        self.ResetTotal()
        totals = self.totals
        for msg_id in self.messageinfo_db.db.keys():
            # Skip the date key.
            if msg_id == STATS_START_KEY:
                continue
            m = Message(msg_id, self.messageinfo_db)
            self.messageinfo_db.load_msg(m)

            # Skip all old messages that don't have a date.
            if m.date_modified is None:
                continue

            # Skip ones that are too old.
            if self.from_date and m.date_modified < self.from_date:
                continue

            classification = m.GetClassification()
            trained = m.GetTrained()
            
            if classification == self.options["Headers",
                                              "header_spam_string"]:
                # Classified as spam.
                totals["num_spam"] += 1
                if trained == False:
                    # False positive (classified as spam, trained as ham)
                    totals["num_trained_ham_fp"] += 1
            elif classification == self.options["Headers",
                                                "header_ham_string"]:
                # Classified as ham.
                totals["num_ham"] += 1
                if trained == True:
                    # False negative (classified as ham, trained as spam)
                    totals["num_trained_spam_fn"] += 1
            elif classification == self.options["Headers",
                                                "header_unsure_string"]:
                # Classified as unsure.
                totals["num_unsure"] += 1
                if trained == False:
                    totals["num_trained_ham"] += 1
                elif trained == True:
                    totals["num_trained_spam"] += 1

    def _CombineSessionAndTotal(self):
        totals = self.totals
        data = {}
        data["num_ham"] = self.num_ham + totals["num_ham"]
        data["num_spam"] = self.num_spam + totals["num_spam"]
        data["num_unsure"] = self.num_unsure + totals["num_unsure"]
        data["num_seen"] = data["num_ham"] + data["num_spam"] + \
                           data["num_unsure"]
        data["num_trained_ham"] = self.num_trained_ham + \
                                  totals["num_trained_ham"]
        data["num_trained_ham_fp"] = self.num_trained_ham_fp + \
                                     totals["num_trained_ham_fp"]
        data["num_trained_spam"] = self.num_trained_spam + \
                                   totals["num_trained_spam"]
        data["num_trained_spam_fn"] = self.num_trained_spam_fn + \
                                      totals["num_trained_spam_fn"]
        return data

    def _CalculateAdditional(self, data):
        data["perc_ham"] = 100.0 * data["num_ham"] / data["num_seen"]
        data["perc_spam"] = 100.0 * data["num_spam"] / data["num_seen"]
        data["perc_unsure"] = 100.0 * data["num_unsure"] / data["num_seen"]
        data["num_ham_correct"] = data["num_ham"] - \
                                  data["num_trained_spam_fn"]
        data["num_spam_correct"] = data["num_spam"] - \
                                   data["num_trained_ham_fp"]
        data["num_correct"] = data["num_ham_correct"] + \
                              data["num_spam_correct"]
        data["num_incorrect"] = data["num_trained_spam_fn"] + \
                                data["num_trained_ham_fp"]
        data["perc_correct"] = 100.0 * data["num_correct"] / \
                               data["num_seen"]
        data["perc_incorrect"] = 100.0 * data["num_incorrect"] / \
                                 data["num_seen"]
        data["perc_fp"] = 100.0 * data["num_trained_ham_fp"] / \
                          data["num_seen"]
        data["perc_fn"] = 100.0 * data["num_trained_spam_fn"] / \
                          data["num_seen"]
        data["num_unsure_trained_ham"] = data["num_trained_ham"] - \
                                         data["num_trained_ham_fp"]
        data["num_unsure_trained_spam"] = data["num_trained_spam"] - \
                                          data["num_trained_spam_fn"]
        data["num_unsure_not_trained"] = data["num_unsure"] - \
                                         data["num_unsure_trained_ham"] - \
                                         data["num_unsure_trained_spam"]
        if data["num_unsure"]:
            data["perc_unsure_trained_ham"] = 100.0 * \
                                              data["num_unsure_trained_ham"] / \
                                              data["num_unsure"]
            data["perc_unsure_trained_spam"] = 100.0 * \
                                               data["num_unsure_trained_spam"] / \
                                               data["num_unsure"]
            data["perc_unsure_not_trained"] = 100.0 * \
                                              data["num_unsure_not_trained"] / \
                                              data["num_unsure"]
        data["total_ham"] = data["num_ham_correct"] + \
                            data["num_trained_ham"]
        data["total_spam"] = data["num_spam_correct"] + \
                             data["num_trained_spam"]
        if data["total_ham"]:
            data["perc_ham_incorrect"] = 100.0 * \
                                         data["num_trained_ham_fp"] / \
                                         data["total_ham"]
            data["perc_ham_unsure"] = 100.0 * \
                                      data["num_unsure_trained_ham"] / \
                                      data["total_ham"]
            data["perc_ham_incorrect_or_unsure"] = \
                100.0 * (data["num_trained_ham_fp"] +
                         data["num_unsure_trained_ham"]) / \
                         data["total_ham"]
        if data["total_spam"]:
            data["perc_spam_correct"] = 100.0 * data["num_spam_correct"] / \
                                        data["total_spam"]
            data["perc_spam_unsure"] = 100.0 * \
                                       data["num_unsure_trained_spam"] / \
                                       data["total_spam"]
            data["perc_spam_correct_or_unsure"] = \
                100.0 * (data["num_spam_correct"] + \
                         data["num_unsure_trained_spam"]) / \
                         data["total_spam"]

        fp_cost = self.options["TestDriver", "best_cutoff_fp_weight"]
        fn_cost = self.options["TestDriver", "best_cutoff_fn_weight"]
        unsure_cost = self.options["TestDriver",
                                   "best_cutoff_unsure_weight"]
        data["total_cost"] = data["num_trained_ham_fp"] * fp_cost + \
                             data["num_trained_spam_fn"] * fn_cost + \
                             data["num_unsure"] * unsure_cost
        # If there was no filtering done, what would the cost have been?
        # (Assuming that any spam in the inbox earns the cost of a fn)
        no_filter_cost = data["num_spam"] * fn_cost
        data["cost_savings"] = no_filter_cost - data["total_cost"]

        return data

    def _AddPercentStrings(self, data, dp):
        data["perc_ham_s"] = "%%(perc_ham).%df%%(perc)s" % (dp,)
        data["perc_spam_s"] = "%%(perc_spam).%df%%(perc)s" % (dp,)
        data["perc_unsure_s"] = "%%(perc_unsure).%df%%(perc)s" % (dp,)
        data["perc_correct_s"] = "%%(perc_correct).%df%%(perc)s" % (dp,)
        data["perc_incorrect_s"] = "%%(perc_incorrect).%df%%(perc)s" % (dp,)
        data["perc_fp_s"] = "%%(perc_fp).%df%%(perc)s" % (dp,)
        data["perc_fn_s"] = "%%(perc_fn).%df%%(perc)s" % (dp,)
        data["perc_spam_correct_s"] = "%%(perc_spam_correct).%df%%(perc)s" \
                                      % (dp,)
        data["perc_spam_unsure_s"] = "%%(perc_spam_unsure).%df%%(perc)s" \
                                     % (dp,)
        data["perc_spam_correct_or_unsure_s"] = \
              "%%(perc_spam_correct_or_unsure).%df%%(perc)s" % (dp,)
        data["perc_ham_incorrect_s"] = "%%(perc_ham_incorrect).%df%%(perc)s" \
                                       % (dp,)
        data["perc_ham_unsure_s"] = "%%(perc_ham_unsure).%df%%(perc)s" \
                                    % (dp,)
        data["perc_ham_incorrect_or_unsure_s"] = \
              "%%(perc_ham_incorrect_or_unsure).%df%%(perc)s" % (dp,)
        data["perc_unsure_trained_ham_s"] = \
              "%%(perc_unsure_trained_ham).%df%%(perc)s" % (dp,)
        data["perc_unsure_trained_spam_s"] = "%%(perc_unsure_trained_spam).%df%%(perc)s" \
                                             % (dp,)
        data["perc_unsure_not_trained_s"] = "%%(perc_unsure_not_trained).%df%%(perc)s" \
                                            % (dp,)
        data["perc"] = "%"
        return data

    def GetStats(self, use_html=False, session_only=False, decimal_points=1):
        """Return a description of the statistics.

        If session_only is True, then only a description of the statistics
        since we were last reset.  Otherwise, lifetime statistics (i.e.
        those including the ones loaded).

        Users probably care most about persistent statistics, so present
        those by default.  If session-only stats are desired, then a
        special call to here can be made.

        The percentages will be accurate to the given number of decimal
        points.

        If use_html is True, then the returned data is marked up with
        appropriate HTML, otherwise it is plain text.
        """
        chunks = []
        push = chunks.append

        if session_only:
            data = {}
            data["num_seen"] = self.num_ham + self.num_spam + \
                               self.num_unsure
            data["num_ham"] = self.num_ham
            data["num_spam"] = self.num_spam
            data["num_unsure"] = self.num_unsure
            data["num_trained_ham"] = self.num_trained_ham
            data["num_trained_ham_fp"] = self.num_trained_ham_fp
            data["num_trained_spam"] = self.num_trained_spam
            data["num_trained_spam_fn"] = self.num_trained_spam_fn
        else:
            data = self._CombineSessionAndTotal()

        push(_("Messages classified: %d") % (data["num_seen"],))
        if data["num_seen"] == 0:
            return chunks

        data = self._CalculateAdditional(data)
        format_dict = self._AddPercentStrings(data, decimal_points)
        
        # Possibly use HTML for tabs.
        if use_html:
            format_dict["tab"] = "&nbsp;&nbsp;&nbsp;&nbsp;"
        else:
            format_dict["tab"] = "\t"

        push((_("%(tab)sGood:%(tab)s%(num_ham)d (%(perc_ham_s)s)") \
             % format_dict) % format_dict)
        push((_("%(tab)sSpam:%(tab)s%(num_spam)d (%(perc_spam_s)s)") \
             % format_dict) % format_dict)
        push((_("%(tab)sUnsure:%(tab)s%(num_unsure)d (%(perc_unsure_s)s)") \
             % format_dict) % format_dict)
        push("")

        push((_("Classified correctly:%(tab)s%(num_correct)d (%(perc_correct_s)s of total)") \
             % format_dict) % format_dict)
        push((_("Classified incorrectly:%(tab)s%(num_incorrect)d (%(perc_incorrect_s)s of total)") \
             % format_dict) % format_dict)
        if format_dict["num_incorrect"]:
            push((_("%(tab)sFalse positives:%(tab)s%(num_trained_ham_fp)d (%(perc_fp_s)s of total)") \
                 % format_dict) % format_dict)
            push((_("%(tab)sFalse negatives:%(tab)s%(num_trained_spam_fn)d (%(perc_fn_s)s of total)") \
                 % format_dict) % format_dict)
        push("")
        
        push(_("Manually classified as good:%(tab)s%(num_trained_ham)d") % format_dict)
        push(_("Manually classified as spam:%(tab)s%(num_trained_spam)d") % format_dict)
        push("")

        if format_dict["num_unsure"]:
            push((_("Unsures trained as good:%(tab)s%(num_unsure_trained_ham)d (%(perc_unsure_trained_ham_s)s of unsures)") \
                 % format_dict) % format_dict)
            push((_("Unsures trained as spam:%(tab)s%(num_unsure_trained_spam)d (%(perc_unsure_trained_spam_s)s of unsures)") \
                 % format_dict) % format_dict)
            push((_("Unsures not trained:%(tab)s%(tab)s%(num_unsure_not_trained)d (%(perc_unsure_not_trained_s)s of unsures)") \
                 % format_dict) % format_dict)
            push("")

        if format_dict["total_spam"]:
            push((_("Spam correctly identified:%(tab)s%(perc_spam_correct_s)s (+ %(perc_spam_unsure_s)s unsure)") \
                 % format_dict) % format_dict)
        if format_dict["total_ham"]:
            push((_("Good incorrectly identified:%(tab)s%(perc_ham_incorrect_s)s (+ %(perc_ham_unsure_s)s unsure)") \
                 % format_dict) % format_dict)
        if format_dict["total_spam"] or format_dict["total_ham"]:
            push("")

        push(_("Total cost of spam:%(tab)s$%(total_cost).2f") % format_dict)
        push(_("SpamBayes savings:%(tab)s$%(cost_savings).2f") % format_dict)

        return chunks


if __name__=='__main__':
    s = Stats()
    print "\n".join(s.GetStats())
