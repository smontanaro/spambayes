#! /usr/bin/env python


from spambayes import mboxutils
from spambayes import storage
from spambayes.Options import options
from spambayes.tokenizer import tokenize

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


class Hammie:
    """A spambayes mail filter.

    This implements the basic functionality needed to score, filter, or
    train.  

    """

    def __init__(self, bayes):
        self.bayes = bayes

    def _scoremsg(self, msg, evidence=False):
        """Score a Message.

        msg can be a string, a file object, or a Message object.

        Returns the probability the message is spam.  If evidence is
        true, returns a tuple: (probability, clues), where clues is a
        list of the words which contributed to the score.

        """

        return self.bayes.spamprob(tokenize(msg), evidence)

    def formatclues(self, clues, sep="; "):
        """Format the clues into something readable."""

        return sep.join(["%r: %.2f" % (word, prob)
                         for word, prob in clues
                         if (word[0] == '*' or
                             prob <= options.clue_mailheader_cutoff or
                             prob >= 1.0 - options.clue_mailheader_cutoff)])

    def score(self, msg, evidence=False):
        """Score (judge) a message.

        msg can be a string, a file object, or a Message object.

        Returns the probability the message is spam.  If evidence is
        true, returns a tuple: (probability, clues), where clues is a
        list of the words which contributed to the score.

        """

        return self._scoremsg(msg, evidence)

    def filter(self, msg, header=None, spam_cutoff=None,
               ham_cutoff=None, debugheader=None,
               debug=None):
        """Score (judge) a message and add a disposition header.

        msg can be a string, a file object, or a Message object.

        Optionally, set header to the name of the header to add, and/or
        spam_cutoff/ham_cutoff to the probability values which must be met
        or exceeded for a message to get a 'Spam' or 'Ham' classification.

        An extra debugging header can be added if 'debug' is set to True.
        The name of the debugging header is given as 'debugheader'.

        All defaults for optional parameters come from the Options file.

        Returns the same message with a new disposition header.

        """

        if header == None:
            header = options.hammie_header_name
        if spam_cutoff == None:
            spam_cutoff = options.spam_cutoff
        if ham_cutoff == None:
            ham_cutoff = options.ham_cutoff
        if debugheader == None:
            debugheader = options.hammie_debug_header_name
        if debug == None:
            debug = options.hammie_debug_header

        msg = mboxutils.get_message(msg)
        try:
            del msg[header]
        except KeyError:
            pass
        prob, clues = self._scoremsg(msg, True)
        if prob < ham_cutoff:
            disp = options.header_ham_string
        elif prob > spam_cutoff:
            disp = options.header_spam_string
        else:
            disp = options.header_unsure_string
        disp += ("; %."+str(options.header_score_digits)+"f") % prob
        if options.header_score_logarithm:
            if prob<=0.005 and prob>0.0:
                import math
                x=-math.log10(prob)
                disp += " (%d)"%x
            if prob>=0.995 and prob<1.0:
                import math
                x=-math.log10(1.0-prob)
                disp += " (%d)"%x
        msg.add_header(header, disp)
        if debug:
            disp = self.formatclues(clues)
            msg.add_header(debugheader, disp)
        return msg.as_string(unixfrom=(msg.get_unixfrom() is not None))

    def train(self, msg, is_spam):
        """Train bayes with a message.

        msg can be a string, a file object, or a Message object.

        is_spam should be 1 if the message is spam, 0 if not.

        """

        self.bayes.learn(tokenize(msg), is_spam)

    def untrain(self, msg, is_spam):
        """Untrain bayes with a message.

        msg can be a string, a file object, or a Message object.

        is_spam should be 1 if the message is spam, 0 if not.

        """

        self.bayes.unlearn(tokenize(msg), is_spam)

    def train_ham(self, msg):
        """Train bayes with ham.

        msg can be a string, a file object, or a Message object.

        """

        self.train(msg, False)

    def train_spam(self, msg):
        """Train bayes with spam.

        msg can be a string, a file object, or a Message object.

        """

        self.train(msg, True)

    def untrain_ham(self, msg):
        """Untrain bayes with ham.

        msg can be a string, a file object, or a Message object.

        """

        self.untrain(msg, False)

    def train_spam(self, msg):
        """Untrain bayes with spam.

        msg can be a string, a file object, or a Message object.

        """

        self.untrain(msg, True)

    def store(self):
        """Write out the persistent store.

        This makes sure the persistent store reflects what is currently
        in memory.  You would want to do this after a write and before
        exiting.

        """

        self.bayes.store()


def open(filename, usedb=True, mode='r'):
    """Open a file, returning a Hammie instance.

    If usedb is False, open as a pickle instead of a DBDict.  mode is

    used as the flag to open DBDict objects.  'c' for read-write (create
    if needed), 'r' for read-only, 'w' for read-write.

    """

    if usedb:
        b = storage.DBDictClassifier(filename, mode)
    else:
        b = storage.PickledClassifier(filename)
    return Hammie(b)


if __name__ == "__main__":
    # Everybody's used to running hammie.py.  Why mess with success?  ;)
    import hammiebulk

    hammiebulk.main()
