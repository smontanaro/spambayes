"""Spam/ham profile for a single VM user."""

import ZODB
from ZODB.PersistentList import PersistentList
from Persistence import Persistent
from BTrees.OOBTree import OOBTree

import classifier
from tokenizer import tokenize

from pspam.folder import Folder
from pspam.options import options

import os

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


def open_folders(dir, names, klass):
    L = []
    for name in names:
        path = os.path.join(dir, name)
        L.append(klass(path))
    return L

import time
_start = None
def log(s):
    global _start
    if _start is None:
        _start = time.time()
    print round(time.time() - _start, 2), s


class IterOOBTree(OOBTree):

    def iteritems(self):
        return self.items()

class WordInfo(Persistent):

    def __init__(self, atime, spamprob=options.unknown_word_prob):
        self.atime = atime
        self.spamcount = self.hamcount = self.killcount = 0
        self.spamprob = spamprob

    def __repr__(self):
        return "WordInfo%r" % repr((self.atime, self.spamcount,
                                    self.hamcount, self.killcount,
                                    self.spamprob))

class PBayes(classifier.Bayes, Persistent):

    WordInfoClass = WordInfo

    def __init__(self):
        classifier.Bayes.__init__(self)
        self.wordinfo = IterOOBTree()

    # XXX what about the getstate and setstate defined in base class

class Profile(Persistent):

    FolderClass = Folder

    def __init__(self, folder_dir):
        self._dir = folder_dir
        self.classifier = PBayes()
        self.hams = PersistentList()
        self.spams = PersistentList()

    def add_ham(self, folder):
        p = os.path.join(self._dir, folder)
        f = self.FolderClass(p)
        self.hams.append(f)

    def add_spam(self, folder):
        p = os.path.join(self._dir, folder)
        f = self.FolderClass(p)
        self.spams.append(f)

    def update(self):
        """Update classifier from current folder contents."""
        changed1 = self._update(self.hams, False)
        changed2 = self._update(self.spams, True)
        if changed1 or changed2:
            self.classifier.update_probabilities()
        get_transaction().commit()
        log("updated probabilities")

    def _update(self, folders, is_spam):
        changed = False
        for f in folders:
            log("update from %s" % f.path)
            added, removed = f.read()
            if added:
                log("added %d" % len(added))
            if removed:
                log("removed %d" % len(removed))
            get_transaction().commit()
            if not (added or removed):
                continue
            changed = True

            # It's important not to commit a transaction until
            # after update_probabilities is called in update().
            # Otherwise some new entries will cause scoring to fail.
            for msg in added.keys():
                self.classifier.learn(tokenize(msg), is_spam, False)
            del added
            get_transaction().commit(1)
            log("learned")
            for msg in removed.keys():
                self.classifier.unlearn(tokenize(msg), is_spam, False)
            if removed:
                log("unlearned")
            del removed
            get_transaction().commit(1)
        return changed
