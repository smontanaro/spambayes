# oastats.py - Outlook Addin Stats

import os
import pickle

STATS_FILENAME = "performance_statistics_database.pik"

class Stats:
    def __init__(self, config, data_directory):
        self.config = config
        self.stored_statistics_fn = os.path.join(data_directory,
                                                 STATS_FILENAME)
        if os.path.exists(self.stored_statistics_fn):
            self.Load()
        else:
            self.ResetTotal()
        self.Reset()
    def Reset(self):
        self.num_ham = self.num_spam = self.num_unsure = 0
        self.num_deleted_spam = self.num_deleted_spam_fn  = 0
        self.num_recovered_good = self.num_recovered_good_fp = 0
    def ResetTotal(self, permanently=False):
        self.totals = {}
        for stat in ["num_ham", "num_spam", "num_unsure",
                     "num_deleted_spam", "num_deleted_spam_fn",
                     "num_recovered_good", "num_recovered_good_fp",]:
            self.totals[stat] = 0
        if permanently:
            # Also remove the file.
            try:
                os.remove(self.stored_statistics_fn)
            except OSError:
                # Maybe we had never saved it.
                pass
    def Load(self):
        store = open(self.stored_statistics_fn, 'rb')
        self.totals = pickle.load(store)
        store.close()
    def Store(self):
        # Update totals, and save that.
        for stat in ["num_ham", "num_spam", "num_unsure",
                     "num_deleted_spam", "num_deleted_spam_fn",
                     "num_recovered_good", "num_recovered_good_fp",]:
            self.totals[stat] += getattr(self, stat)
        store = open(self.stored_statistics_fn, 'wb')
        pickle.dump(self.totals, store)
        store.close()
        # Reset, or the reporting for the remainder of this session will be
        # incorrect.
        self.Reset()
    def RecordClassification(self, score):
        score *= 100 # same units as our config values.
        if score >= self.config.filter.spam_threshold:
            self.num_spam += 1
        elif score >= self.config.filter.unsure_threshold:
            self.num_unsure += 1
        else:
            self.num_ham += 1
    def RecordManualClassification(self, recover_as_good, score):
        score *= 100 # same units as our config values.
        if recover_as_good:
            self.num_recovered_good += 1
            # If we are recovering an item that is in the "spam" threshold,
            # then record it as a "false positive"
            if score > self.config.filter.spam_threshold:
                self.num_recovered_good_fp += 1
        else:
            self.num_deleted_spam += 1
            # If we are deleting as Spam an item that was in our "good" range,
            # then record it as a false neg.
            if score < self.config.filter.unsure_threshold:
                self.num_deleted_spam_fn += 1
    def GetStats(self, session_only=False, decimal_points=1):
        """Return a description of the statistics.

        If session_only is True, then only a description of the statistics
        since we were last reset.  Otherwise, lifetime statistics (i.e.
        those including the ones loaded).

        Users probably care most about persistent statistics, so present
        those by default.  If session-only stats are desired, then a
        special call to here can be made.

        The percentages will be accurate to the given number of decimal
        points.
        """
        num_seen = self.num_ham + self.num_spam + self.num_unsure
        if not session_only:
            totals = self.totals
            num_seen += (totals["num_ham"] + totals["num_spam"] +
                         totals["num_unsure"])
        if num_seen==0:
            return [_("SpamBayes has processed zero messages")]
        chunks = []
        push = chunks.append
        if session_only:
            num_ham = self.num_ham
            num_spam = self.num_spam
            num_unsure = self.num_unsure
            num_recovered_good = self.num_recovered_good
            num_recovered_good_fp = self.num_recovered_good_fp
            num_deleted_spam = self.num_deleted_spam
            num_deleted_spam_fn = self.num_deleted_spam_fn
        else:
            num_ham = self.num_ham + self.totals["num_ham"]
            num_spam = self.num_spam + self.totals["num_spam"]
            num_unsure = self.num_unsure + self.totals["num_unsure"]
            num_recovered_good = self.num_recovered_good + \
                                 self.totals["num_recovered_good"]
            num_recovered_good_fp = self.num_recovered_good_fp + \
                                    self.totals["num_recovered_good_fp"]
            num_deleted_spam = self.num_deleted_spam + \
                               self.totals["num_deleted_spam"]
            num_deleted_spam_fn = self.num_deleted_spam_fn + \
                                  self.totals["num_deleted_spam_fn"]
        perc_ham = 100.0 * num_ham / num_seen
        perc_spam = 100.0 * num_spam / num_seen
        perc_unsure = 100.0 * num_unsure / num_seen
        format_dict = locals().copy()
        del format_dict["self"]
        del format_dict["push"]
        del format_dict["chunks"]
        format_dict.update(dict(perc_spam=perc_spam, perc_ham=perc_ham,
                                perc_unsure=perc_unsure, num_seen=num_seen))
        format_dict["perc_ham_s"] = "%%(perc_ham).%df%%(perc)s" \
                                    % (decimal_points,)
        format_dict["perc_spam_s"] = "%%(perc_spam).%df%%(perc)s" \
                                     % (decimal_points,)
        format_dict["perc_unsure_s"] = "%%(perc_unsure).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc"] = "%"
        push((_("SpamBayes has processed %(num_seen)d messages - " \
             "%(num_ham)d (%(perc_ham_s)s) good, " \
             "%(num_spam)d (%(perc_spam_s)s) spam " \
             "and %(num_unsure)d (%(perc_unsure_s)s) unsure") \
             % format_dict) % format_dict)

        if num_recovered_good:
            push(_("%(num_recovered_good)d message(s) were manually " \
                 "classified as good (with %(num_recovered_good_fp)d " \
                 "being false positives)") % format_dict)
        else:
            push(_("No messages were manually classified as good"))
        if num_deleted_spam:
            push(_("%(num_deleted_spam)d message(s) were manually " \
                 "classified as spam (with %(num_deleted_spam_fn)d " \
                 "being false negatives)") % format_dict)
        else:
            push(_("No messages were manually classified as spam"))
        return chunks

if __name__=='__main__':
    class FilterConfig:
        unsure_threshold = 15
        spam_threshold = 85
    class Config:
        filter = FilterConfig()
    data_directory = os.getcwd()
    # processed zero
    s = Stats(Config(), data_directory)
    print "\n".join(s.GetStats())
    # No recovery
    s = Stats(Config(), data_directory)
    s.RecordClassification(.2)
    print "\n".join(s.GetStats())

    s = Stats(Config(), data_directory)
    s.RecordClassification(.2)
    s.RecordClassification(.1)
    s.RecordClassification(.4)
    s.RecordClassification(.9)
    s.RecordManualClassification(True, 0.1)
    s.RecordManualClassification(True, 0.9)
    s.RecordManualClassification(False, 0.1)
    s.RecordManualClassification(False, 0.9)
    print "\n".join(s.GetStats())

    # Store
    # (this will leave an artifact in the cwd)
    s.Store()
    # Load
    s = Stats(Config(), data_directory)
    print "\n".join(s.GetStats())
    print "\n".join(s.GetStats(True))
