# Test the basic storage operations of the classifier.

import unittest, os, sys

# Hack sys.path - 2 levels up must be on sys.path.
try:
    this_file = __file__
except NameError:
    this_file = sys.argv[0]
sb_dir = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(this_file))))
if sb_dir not in sys.path:
    sys.path.append(sb_dir)

from spambayes.storage import DBDictClassifier, PickledClassifier

class _StorageTestBase(unittest.TestCase):
    StorageClass = None

    def setUp(self):
        import tempfile
        self.db_name = tempfile.mktemp("spambayestest")
        self.classifier = self.__class__.StorageClass(self.db_name)

    def tearDown(self):
        self.classifier = None
        if os.path.isfile(self.db_name):
            os.remove(self.db_name)
    
    def _checkWordCounts(self, word, expected_ham, expected_spam):
        assert word
        info = self.classifier._wordinfoget(word)
        if info is None:
            if expected_ham==0 and expected_spam==0:
                return
            self.fail("_CheckWordCounts for '%s' got None!")
        if info.hamcount != expected_ham:
            self.fail("Hamcount '%s' wrong - got %d, but expected %d" \
                        % (word, info.hamcount, expected_ham))
        if info.spamcount != expected_spam:
            self.fail("Spamcount '%s' wrong - got %d, but expected %d" \
                        % (word, info.spamcount, expected_spam))

    def _checkAllWordCounts(self, counts, do_persist):
        for info in counts:
            self._checkWordCounts(*info)
        if do_persist:
            self.classifier.store()
            self.classifier.load()
            self._checkAllWordCounts(counts, False)

    def testHapax(self):
        self._dotestHapax(False)
        self._dotestHapax(True)

    def _dotestHapax(self, do_persist):
        c = self.classifier
        c.learn(["common","nearly_hapax", "hapax", ], False)
        c.learn(["common","nearly_hapax"], False)
        c.learn(["common"], False)
        # All the words should be there.
        self._checkAllWordCounts( (("common", 3, 0),
                                   ("nearly_hapax", 2, 0),
                                   ("hapax", 1, 0)),
                                  do_persist)
        # Unlearn the complete set.
        c.unlearn(["common","nearly_hapax", "hapax", ], False)
        # 'hapax' removed, rest still there
        self._checkAllWordCounts( (("common", 2, 0),
                                   ("nearly_hapax", 1, 0),
                                   ("hapax", 0, 0)),
                                  do_persist)
        # Re-learn that set, so deleted hapax is reloaded
        c.learn(["common","nearly_hapax", "hapax", ], False)
        self._checkAllWordCounts( (("common", 3, 0),
                                   ("nearly_hapax", 2, 0),
                                   ("hapax", 1, 0)),
                                  do_persist)
        # Back to where we started - start unlearning all down to zero.
        c.unlearn(["common","nearly_hapax", "hapax", ], False)
        # 'hapax' removed, rest still there
        self._checkAllWordCounts( (("common", 2, 0),
                                   ("nearly_hapax", 1, 0),
                                   ("hapax", 0, 0)),
                                  do_persist)

        # Unlearn the next set.
        c.unlearn(["common","nearly_hapax"], False)
        self._checkAllWordCounts( (("common", 1, 0),
                                   ("nearly_hapax", 0, 0),
                                   ("hapax", 0, 0)),
                                  do_persist)

        
        c.unlearn(["common"], False)
        self._checkAllWordCounts( (("common", 0, 0),
                                   ("nearly_hapax", 0, 0),
                                   ("hapax", 0, 0)),
                                  do_persist)

# Test classes for each classifier.
class PickleStorageTestCase(_StorageTestBase):
    StorageClass = PickledClassifier
    def setUp(self):
        return _StorageTestBase.setUp(self)

class DBStorageTestCase(_StorageTestBase):
    StorageClass = DBDictClassifier
    def setUp(self):
        return _StorageTestBase.setUp(self)
    def tearDown(self):
        self.classifier.db.close()
        _StorageTestBase.tearDown(self)

def suite():
    # We dont want our base class run
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PickleStorageTestCase))
    suite.addTest(unittest.makeSuite(DBStorageTestCase))
    return suite

if __name__=='__main__':
    unittest.main(argv=sys.argv + ['suite'])
