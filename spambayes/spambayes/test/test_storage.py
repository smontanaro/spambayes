# Test the basic storage operations of the classifier.

import unittest, os, sys
import tempfile
import cStringIO as StringIO

import sb_test_support
sb_test_support.fix_sys_path()

from spambayes.storage import DBDictClassifier, PickledClassifier

class _StorageTestBase(unittest.TestCase):
    # Subclass must define a concrete StorageClass.
    StorageClass = None

    def setUp(self):
        self.db_name = tempfile.mktemp("spambayestest")
        self.classifier = self.StorageClass(self.db_name)

    def tearDown(self):
        self.classifier = None
        if os.path.isfile(self.db_name):
            os.remove(self.db_name)

    def _checkWordCounts(self, word, expected_ham, expected_spam):
        assert word
        info = self.classifier._wordinfoget(word)
        if info is None:
            if expected_ham == expected_spam == 0:
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

    def test_bug777026(self):
        c = self.classifier
        word = "tim"
        c.learn([word], False)
        c.learn([word], False)
        self._checkAllWordCounts([(word, 2, 0)], False)

        # Clone word's WordInfo record.
        record = self.classifier.wordinfo[word]
        newrecord = type(record)()
        newrecord.__setstate__(record.__getstate__())
        self.assertEqual(newrecord.hamcount, 2)
        self.assertEqual(newrecord.spamcount, 0)

        # Reduce the hamcount -- this tickled an excruciatingly subtle
        # bug in a DBDictClassifier's _wordinfoset, which, at the time
        # this test was written, couldn't actually be provoked by the
        # way _wordinfoset got called by way of learn() and unlearn()
        # methods.  The code implicitly relied on that the record passed
        # to _wordinfoset was always the same object as was already
        # in wordinfo[word].
        newrecord.hamcount -= 1
        c._wordinfoset(word, newrecord)
        # If the bug is present, the DBDictClassifier still believes
        # the hamcount is 2.
        self._checkAllWordCounts([(word, 1, 0)], False)

        c.unlearn([word], False)
        self._checkAllWordCounts([(word, 0, 0)], False)

# Test classes for each classifier.
class PickleStorageTestCase(_StorageTestBase):
    StorageClass = PickledClassifier

class DBStorageTestCase(_StorageTestBase):
    StorageClass = DBDictClassifier

    def tearDown(self):
        self.classifier.db.close()
        _StorageTestBase.tearDown(self)

    def _fail_open_best(self, *args):
        from spambayes import dbmstorage
        raise dbmstorage.error("No dbm modules available!")

    def testNoDBMAvailable(self):
        import tempfile
        from spambayes.storage import open_storage

        db_name = tempfile.mktemp("nodbmtest")
        DBDictClassifier_load = DBDictClassifier.load
        DBDictClassifier.load = self._fail_open_best
        # Redirect sys.stderr, as open_storage() prints a msg to stderr.
        # Then it does sys.exit(), which we catch.
        sys_stderr = sys.stderr
        sys.stderr = StringIO.StringIO()
        try:
            try:
                open_storage(db_name, True)
            except SystemExit:
                pass
            else:
                self.fail("expected SystemExit from open_storage() call")
        finally:
            DBDictClassifier.load = DBDictClassifier_load
            sys.stderr = sys_stderr

        if os.path.isfile(db_name):
            os.remove(db_name)

def suite():
    suite = unittest.TestSuite()
    for cls in (PickleStorageTestCase,
                DBStorageTestCase,
               ):
        suite.addTest(unittest.makeSuite(cls))
    return suite

if __name__=='__main__':
    sb_test_support.unittest_main(argv=sys.argv + ['suite'])
