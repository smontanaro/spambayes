#! /usr/bin/env python

# A server version of hammie.py

# Server code

import SimpleXMLRPCServer
import email
import hammie
from tokenizer import tokenize

# Default header to add
DFL_HEADER = "X-Hammie-Disposition"

# Default spam cutoff
DFL_CUTOFF = 0.9

class Hammie:
    def __init__(self, bayes):
        self.bayes = bayes

    def _scoremsg(self, msg, evidence=False):
        """Score an email.Message.

        Returns the probability the message is spam.  If evidence is
        true, returns a tuple: (probability, clues), where clues is a
        list of the words which contributed to the score.

        """

        return self.bayes.spamprob(tokenize(msg), evidence)

    def score(self, msg, evidence=False):
        """Score (judge) a message.

        Pass in a message as a string.

        Returns the probability the message is spam.  If evidence is
        true, returns a tuple: (probability, clues), where clues is a
        list of the words which contributed to the score.

        """

        return self._scoremsg(email.message_from_string(msg), evidence)

    def filter(self, msg, header=DFL_HEADER, cutoff=DFL_CUTOFF):
        """Score (judge) a message and add a disposition header.

        Pass in a message as a string.  Optionally, set header to the
        name of the header to add, and/or cutoff to the probability
        value which must be met or exceeded for a message to get a 'Yes'
        disposition.

        Returns the same message with a new disposition header.

        """

        msg = email.message_from_string(msg)
        prob, clues = self._scoremsg(msg, True)
        if prob < cutoff:
            disp = "No"
        else:
            disp = "Yes"
        disp += "; %.2f" % prob
        disp += "; " + hammie.formatclues(clues)
        msg.add_header(header, disp)
        return msg.as_string(unixfrom=(msg.get_unixfrom() is not None))

    def train(self, msg, is_spam):
        """Train bayes with a message.

        msg should be the message as a string, and is_spam should be 1
        if the message is spam, 0 if not.

        Probabilities are not updated after this call is made; to do
        that, call update_probabilities().

        """

        self.bayes.learn(tokenize(msg), is_spam, False)

    def train_ham(self, msg):
        """Train bayes with ham.

        msg should be the message as a string.

        Probabilities are not updated after this call is made; to do
        that, call update_probabilities().

        """

        self.train(msg, False)

    def train_spam(self, msg):
        """Train bayes with spam.

        msg should be the message as a string.

        Probabilities are not updated after this call is made; to do
        that, call update_probabilities().

        """

        self.train(msg, True)

    def update_probabilities(self):
        """Update probability values.

        You would want to call this after a training session.  It's
        pretty slow, so if you have a lot of messages to train, wait
        until you're all done before calling this.

        """

        self.bayes.update_probabilites()

def main():
    usedb = True
    pck = "/home/neale/lib/hammie.db"

    if usedb:
        bayes = hammie.PersistentGrahamBayes(pck)
    else:
        bayes = None
        try:
            fp = open(pck, 'rb')
        except IOError, e:
            if e.errno <> errno.ENOENT: raise
        else:
            bayes = pickle.load(fp)
            fp.close()
        if bayes is None:
            import classifier
            bayes = classifier.GrahamBayes()

    server = SimpleXMLRPCServer.SimpleXMLRPCServer(("localhost", 7732))
    server.register_instance(Hammie(bayes))
    server.serve_forever()

if __name__ == "__main__":
    main()
