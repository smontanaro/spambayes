###
### This is a training regime for the incremental.py harness.
### It does guess-based training on all messages, followed by
### correction to perfect at the end of each group.
###

class Regime:
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
