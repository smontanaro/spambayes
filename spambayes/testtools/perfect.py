###
### This is a training regime for the incremental.py harness.
### It does perfect training on all messages.
###

class Regime:
    def __init__(self):
        pass

    def group_action(self, which, test):
        pass

    def guess_action(self, which, test, guess, actual, msg):
        return actual

