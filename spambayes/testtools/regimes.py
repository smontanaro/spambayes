"""regimes.py

This module is not executable - it contains regime definitions
for use with incremental.py.  Pass the name of any regime to
incremental.py with the "-r" switch, and it will be loaded from
this module.

Existing regimes are:
  'perfect'       A train-on-everything regime.  The trainer is given
                  perfect and immediate knowledge of the proper
                  classification.
  'corrected'     A train-on-everything regime.  The trainer trusts the
                  classifier result until end-of-group, at which point
                  all mistrained and non-trained items (fp, fn, and
                  unsure) are corrected to be trained with their proper
                  classification.
  'balanced_corrected'
                  A partial-training regime.  Works just like the
                  'corrected' regime, except that if the database is
                  imbalanced more than 2::1 (or 1::2) then messages are
                  not used for training.
  'expire4months' This is like 'perfect', except that messages are
                  untrained after 120 groups have passed.
  'nonedge'       A partial-training regime, which trains only on messages
                  which are not properly classified with scores of 1.00 or
                  0.00 (rounded).  All false positives and false negatives
                  *are* trained.
  'fpfnunsure'    A partial-training regime, which trains only on
                  false positives, false negatives and unsures.
  'fnunsure'      A partial-training regime, which trains only on
                  false negatives and unsures.  This simulates, for
                  example, a user who deletes all mail classified as spam
                  without ever examining it for false positives.
"""

###
### This is a training regime for the incremental.py harness.
### It does perfect training on all messages.
###

class perfect:
    def __init__(self):
        pass

    def group_action(self, which, test):
        pass

    def guess_action(self, which, test, guess, actual, msg):
        return actual

###
### This is a training regime for the incremental.py harness.
### It does guess-based training on all messages, followed by
### correction to perfect at the end of each group.
###

class corrected:
    def __init__(self):
        self.spam_to_ham = []
        self.ham_to_spam = []
        self.unsure_to_ham = []
        self.unsure_to_spam = []

    def group_action(self, which, test):
        test.untrain(self.ham_to_spam, self.spam_to_ham)
        test.train(self.spam_to_ham, self.ham_to_spam)
        test.train(self.unsure_to_ham, self.unsure_to_spam)
        self.spam_to_ham = []
        self.ham_to_spam = []
        self.unsure_to_ham = []
        self.unsure_to_spam = []

    def guess_action(self, which, test, guess, actual, msg):
        if guess[0] != actual:
            if actual < 0:
                if guess[0] == 0:
                    self.unsure_to_spam.append(msg)
                else:
                    self.ham_to_spam.append(msg)
            else:
                if guess[0] == 0:
                    self.unsure_to_ham.append(msg)
                else:
                    self.spam_to_ham.append(msg)
        return guess[0]

###
### This is a training regime for the incremental.py harness.
### It does guess-based training on all messages, as long
### as the ham::spam ratio stays roughly even (not more than 2::1),
### followed by correction to perfect at the end of each group.
###

class balanced_corrected(corrected):
    ratio_maximum = 2.0
    def guess_action(self, which, test, guess, actual, msg):
        # In some situations, we just do the 'corrected' regime:
        #   If we haven't trained any ham/spam (regardless of
        #     the guess because if all we know is one, everything
        #     will look like it).
        #   If the guess is unsure.
        if not (guess[0] == 0 or test.nham_trained == 0 or \
                test.nspam_trained == 0):
            # Otherwise, we only train if it doesn't screw up the
            # balance.
            ratio = test.nham_trained / float(test.nspam_trained)
            if ratio > self.ratio_maximum and guess[0] == 1:
                # Too much ham, and this is ham - don't train.
                return 0
            elif ratio < (1/self.ratio_maximum) and guess[0] == -1:
                # Too much spam, and this is spam - don't train.
                return 0
        return corrected.guess_action(self, which, test, guess, actual, msg)

###
### This is a training regime for the incremental.py harness.
### It does perfect training for fp, fn, and unsures.
###

class fpfnunsure:
    def __init__(self):
        pass

    def group_action(self, which, test):
        pass

    def guess_action(self, which, test, guess, actual, msg):
        if guess[0] != actual:
            return actual
        return 0
###
### This is a training regime for the incremental.py harness.
### It does perfect training for fn, and unsures, leaving
### false positives broken.
###

class fnunsure:
    def __init__(self):
        pass

    def group_action(self, which, test):
        pass

    def guess_action(self, which, test, guess, actual, msg):
        if guess[0] != actual and guess[0] >= 0:
            return actual
        return 0

###
### This is a training regime for the incremental.py harness.
### It does perfect training for all messages not already
### properly classified with extreme confidence.
###

class nonedge:
    def __init__(self):
        pass

    def group_action(self, which, test):
        pass

    def guess_action(self, which, test, guess, actual, msg):
        if guess[0] != actual:
            return actual
        if 0.005 < guess[1] and guess[1] < 0.995:
            return actual
        return 0


###
### This is a training regime for the incremental.py harness.
### It does perfect training on all messages, followed by
### untraining after 120 groups have gone by.
###

class expire4months:
    def __init__(self):
        self.ham = [[]]
        self.spam = [[]]

    def group_action(self, which, test):
        if len(self.ham) >= 120:
            test.untrain(self.ham[119], self.spam[119])
            self.ham = self.ham[:119]
            self.spam = self.spam[:119]
        self.ham.insert(-1, [])
        self.spam.insert(-1, [])

    def guess_action(self, which, test, guess, actual, msg):
        if actual < 0:
            self.spam[0].append(msg)
        else:
            self.ham[0].append(msg)
        return actual

if __name__ == "__main__":
    print __doc__
