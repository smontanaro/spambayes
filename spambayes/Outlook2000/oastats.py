# oastats.py - Outlook Addin Stats

class Stats:
    def __init__(self, config):
        self.config = config
        self.Reset()
    def Reset(self):
        self.num_ham = self.num_spam = self.num_unsure = 0
        self.num_deleted_spam = self.num_deleted_spam_fn  = 0
        self.num_recovered_good = self.num_recovered_good_fp = 0
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
    def GetStats(self):
        num_seen = self.num_ham + self.num_spam + self.num_unsure
        if num_seen==0:
            return ["SpamBayes has processed zero messages"]
        chunks = []
        push = chunks.append
        perc_ham = 100.0 * self.num_ham / num_seen
        perc_spam = 100.0 * self.num_spam / num_seen
        perc_unsure = 100.0 * self.num_unsure / num_seen
        format_dict = dict(perc_spam=perc_spam, perc_ham=perc_ham,
                           perc_unsure=perc_unsure, num_seen = num_seen)
        format_dict.update(self.__dict__)
        push("SpamBayes has processed %(num_seen)d messages - " \
             "%(num_ham)d (%(perc_ham)d%%) good, " \
             "%(num_spam)d (%(perc_spam)d%%) spam " \
             "and %(num_unsure)d (%(perc_unsure)d%%) unsure" % format_dict)
        if self.num_recovered_good:
            push("%(num_recovered_good)d message(s) were manually " \
                 "classified as good (with %(num_recovered_good_fp)d " \
                 "being false positives)" % format_dict)
        else:
            push("No messages were manually classified as good")
        if self.num_deleted_spam:
            push("%(num_deleted_spam)d message(s) were manually " \
                 "classified as spam (with %(num_deleted_spam_fn)d " \
                 "being false negatives)" % format_dict)
        else:
            push("No messages were manually classified as spam")
        return chunks

if __name__=='__main__':
    class FilterConfig:
        unsure_threshold = 15
        spam_threshold = 85
    class Config:
        filter = FilterConfig()
    # processed zero
    s = Stats(Config())
    print "\n".join(s.GetStats())
    # No recovery
    s = Stats(Config())
    s.RecordClassification(.2)
    print "\n".join(s.GetStats())
    
    s = Stats(Config())
    s.RecordClassification(.2)
    s.RecordClassification(.1)
    s.RecordClassification(.4)
    s.RecordClassification(.9)
    s.RecordManualClassification(True, 0.1)
    s.RecordManualClassification(True, 0.9)
    s.RecordManualClassification(False, 0.1)
    s.RecordManualClassification(False, 0.9)
    print "\n".join(s.GetStats())
