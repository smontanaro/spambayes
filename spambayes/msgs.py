import os
import random

from tokenizer import tokenize

HAMKEEP  = None
SPAMKEEP = None
SEED = random.randrange(2000000000)

class Msg(object):
    __slots__ = 'tag', 'guts'

    def __init__(self, dir, name):
        path = dir + "/" + name
        self.tag = path
        f = open(path, 'rb')
        self.guts = f.read()
        f.close()

    def __iter__(self):
        return tokenize(self.guts)

    # Compare msgs by their paths; this is appropriate for sets of msgs.
    def __hash__(self):
        return hash(self.tag)

    def __eq__(self, other):
        return self.tag == other.tag

    def __str__(self):
        return self.guts

# The iterator yields a stream of Msg objects, taken from a list of
# directories.
class MsgStream(object):
    __slots__ = 'tag', 'directories', 'keep'

    def __init__(self, tag, directories, keep=None):
        self.tag = tag
        self.directories = directories
        self.keep = keep

    def __str__(self):
        return self.tag

    def produce(self):
        if self.keep is None:
            for directory in self.directories:
                for fname in os.listdir(directory):
                    yield Msg(directory, fname)
            return
        # We only want part of the msgs.  Shuffle each directory list, but
        # in such a way that we'll get the same result each time this is
        # called on the same directory list.
        for directory in self.directories:
            all = os.listdir(directory)
            random.seed(hash(max(all)) ^ SEED) # reproducible across calls
            random.shuffle(all)
            del all[self.keep:]
            all.sort()  # seems to speed access on Win98!
            for fname in all:
                yield Msg(directory, fname)

    def __iter__(self):
        return self.produce()

class HamStream(MsgStream):
    def __init__(self, tag, directories):
        MsgStream.__init__(self, tag, directories, HAMKEEP)

class SpamStream(MsgStream):
    def __init__(self, tag, directories):
        MsgStream.__init__(self, tag, directories, SPAMKEEP)

def setparms(hamkeep, spamkeep, seed=None):
    """Set HAMKEEP and SPAMKEEP.  If seed is not None, also set SEED."""

    global HAMKEEP, SPAMKEEP, SEED
    HAMKEEP, SPAMKEEP = hamkeep, spamkeep
    if seed is not None:
        SEED = seed