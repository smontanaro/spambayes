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
        should_store = False
        for stat in ["num_ham", "num_spam", "num_unsure",
                     "num_deleted_spam", "num_deleted_spam_fn",
                     "num_recovered_good", "num_recovered_good_fp",]:
            count = getattr(self, stat)
            self.totals[stat] += count
            if count != 0:
                # One of the totals changed, so we need to store the updates.
                should_store = True
        if should_store:
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
        chunks = []
        push = chunks.append
        num_seen = self.num_ham + self.num_spam + self.num_unsure
        if not session_only:
            totals = self.totals
            num_seen += (totals["num_ham"] + totals["num_spam"] +
                         totals["num_unsure"])
        push(_("Messages classified: %d") % num_seen);
        if num_seen==0:
            return chunks
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
        num_ham_correct = num_ham - num_deleted_spam_fn
        num_spam_correct = num_spam - num_recovered_good_fp
        num_correct = num_ham_correct + num_spam_correct
        num_incorrect = num_deleted_spam_fn + num_recovered_good_fp
        perc_correct = 100.0 * num_correct / num_seen
        perc_incorrect = 100.0 * num_incorrect / num_seen
        perc_fp = 100.0 * num_recovered_good_fp / num_seen
        perc_fn = 100.0 * num_deleted_spam_fn / num_seen
        num_unsure_trained_ham = num_recovered_good - num_recovered_good_fp
        num_unsure_trained_spam = num_deleted_spam - num_deleted_spam_fn
        num_unsure_not_trained = num_unsure - num_unsure_trained_ham - num_unsure_trained_spam
        if num_unsure:
            perc_unsure_trained_ham = 100.0 * num_unsure_trained_ham / num_unsure
            perc_unsure_trained_spam = 100.0 * num_unsure_trained_spam / num_unsure
            perc_unsure_not_trained = 100.0 * num_unsure_not_trained / num_unsure
        else:
            perc_unsure_trained_ham = 0.0
            perc_unsure_trained_spam = 0.0
            perc_unsure_not_trained = 0.0
        total_ham = num_ham_correct + num_recovered_good
        total_spam = num_spam_correct + num_deleted_spam
        if total_ham:
            perc_ham_incorrect = 100.0 * num_recovered_good_fp / total_ham
            perc_ham_unsure = 100.0 * num_unsure_trained_ham / total_ham
            perc_ham_incorrect_or_unsure = \
                100.0 * (num_recovered_good_fp + num_unsure_trained_ham) / total_ham
        else:
            perc_ham_incorrect = 0.0
            perc_ham_unsure = 0.0
            perc_ham_incorrect_or_unsure = 0.0
        if total_spam:
            perc_spam_correct = 100.0 * num_spam_correct / total_spam
            perc_spam_unsure = 100.0 * num_unsure_trained_spam / total_spam
            perc_spam_correct_or_unsure = \
                100.0 * (num_spam_correct + num_unsure_trained_spam) / total_spam
        else:
            perc_spam_correct = 100.0
            perc_spam_unsure = 0.0
            perc_spam_correct_or_unsure = 100.0
        format_dict = locals().copy()
        del format_dict["self"]
        del format_dict["push"]
        del format_dict["chunks"]
        format_dict.update(dict(perc_spam=perc_spam, perc_ham=perc_ham,
                                perc_unsure=perc_unsure, num_seen=num_seen,
                                num_correct=num_correct, num_incorrect=num_incorrect,
                                perc_correct=perc_correct, perc_incorrect=perc_incorrect,
                                perc_fp=perc_fp, perc_fn=perc_fn,
                                num_unsure_trained_ham=num_unsure_trained_ham,
                                num_unsure_trained_spam=num_unsure_trained_spam,
                                num_unsure_not_trained=num_unsure_not_trained,
                                perc_unsure_trained_ham=perc_unsure_trained_ham,
                                perc_unsure_trained_spam=perc_unsure_trained_spam,
                                perc_unsure_not_trained=perc_unsure_not_trained,
                                perc_ham_incorrect=perc_ham_incorrect,
                                perc_ham_unsure=perc_ham_unsure,
                                perc_ham_incorrect_or_unsure=perc_ham_incorrect_or_unsure,
                                perc_spam_correct=perc_spam_correct,
                                perc_spam_unsure=perc_spam_unsure,
                                perc_spam_correct_or_unsure=perc_spam_correct_or_unsure))
        format_dict["perc_ham_s"] = "%%(perc_ham).%df%%(perc)s" \
                                    % (decimal_points,)
        format_dict["perc_spam_s"] = "%%(perc_spam).%df%%(perc)s" \
                                     % (decimal_points,)
        format_dict["perc_unsure_s"] = "%%(perc_unsure).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_correct_s"] = "%%(perc_correct).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_incorrect_s"] = "%%(perc_incorrect).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_fp_s"] = "%%(perc_fp).%df%%(perc)s" \
                                    % (decimal_points,)
        format_dict["perc_fn_s"] = "%%(perc_fn).%df%%(perc)s" \
                                    % (decimal_points,)
        format_dict["perc_spam_correct_s"] = "%%(perc_spam_correct).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_spam_unsure_s"] = "%%(perc_spam_unsure).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_spam_correct_or_unsure_s"] = "%%(perc_spam_correct_or_unsure).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_ham_incorrect_s"] = "%%(perc_ham_incorrect).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_ham_unsure_s"] = "%%(perc_ham_unsure).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_ham_incorrect_or_unsure_s"] = "%%(perc_ham_incorrect_or_unsure).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_unsure_trained_ham_s"] = "%%(perc_unsure_trained_ham).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_unsure_trained_spam_s"] = "%%(perc_unsure_trained_spam).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc_unsure_not_trained_s"] = "%%(perc_unsure_not_trained).%df%%(perc)s" \
                                       % (decimal_points,)
        format_dict["perc"] = "%"
        
        push((_("\tGood:\t%(num_ham)d (%(perc_ham_s)s)") \
             % format_dict) % format_dict)
        push((_("\tSpam:\t%(num_spam)d (%(perc_spam_s)s)") \
             % format_dict) % format_dict)
        push((_("\tUnsure:\t%(num_unsure)d (%(perc_unsure_s)s)") \
             % format_dict) % format_dict)
        push("")

        push((_("Classified correctly:\t%(num_correct)d (%(perc_correct_s)s of total)") \
             % format_dict) % format_dict)
        push((_("Classified incorrectly:\t%(num_incorrect)d (%(perc_incorrect_s)s of total)") \
             % format_dict) % format_dict)
        if num_incorrect:
            push((_("\tFalse positives:\t%(num_recovered_good_fp)d (%(perc_fp_s)s of total)") \
                 % format_dict) % format_dict)
            push((_("\tFalse negatives:\t%(num_deleted_spam_fn)d (%(perc_fn_s)s of total)") \
                 % format_dict) % format_dict)
        push("")
        
        push(_("Manually classified as good:\t%(num_recovered_good)d") % format_dict)
        push(_("Manually classified as spam:\t%(num_deleted_spam)d") % format_dict)
        push("")

        if num_unsure:
            push((_("Unsures trained as good:\t%(num_unsure_trained_ham)d (%(perc_unsure_trained_ham_s)s of unsures)") \
                 % format_dict) % format_dict)
            push((_("Unsures trained as spam:\t%(num_unsure_trained_spam)d (%(perc_unsure_trained_spam_s)s of unsures)") \
                 % format_dict) % format_dict)
            push((_("Unsures not trained:\t\t%(num_unsure_not_trained)d (%(perc_unsure_not_trained_s)s of unsures)") \
                 % format_dict) % format_dict)
            push("")

        push((_("Spam correctly identified:\t%(perc_spam_correct_s)s (+ %(perc_spam_unsure_s)s unsure)") \
             % format_dict) % format_dict)
        push((_("Good incorrectly identified:\t%(perc_ham_incorrect_s)s (+ %(perc_ham_unsure_s)s unsure)") \
             % format_dict) % format_dict)

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
