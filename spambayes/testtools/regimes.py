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
### It does guess-based training on all messages, followed by
### correction to perfect at the end of each group.
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
