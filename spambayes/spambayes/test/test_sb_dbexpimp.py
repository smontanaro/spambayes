# Test sb_dbexpimp script.

import os
import sys
import unittest

from spambayes.tokenizer import tokenize
from spambayes.storage import open_storage
from spambayes.storage import PickledClassifier, DBDictClassifier

import sb_test_support
sb_test_support.fix_sys_path()

import sb_dbexpimp

# We borrow the test messages that test_sb_server uses.
# I doubt it really makes much difference, but if we wanted more than
# one message of each type (the tests should all handle this ok) then
# Richie's hammer.py script has code for generating any number of
# randomly composed email messages.
from test_sb_server import good1, spam1

TEMP_PICKLE_NAME = os.path.join(os.path.dirname(__file__), "temp.pik")
TEMP_CSV_NAME = os.path.join(os.path.dirname(__file__), "temp.csv")
TEMP_DBM_NAME = os.path.join(os.path.dirname(__file__), "temp.dbm")
# The chances of anyone having files with these names in the test
# directory is minute, but we don't want to wipe anything, so make
# sure that they don't already exist.  Our tearDown code gets rid
# of our copies (whether the tests pass or fail) so they shouldn't
# be ours.
for fn in [TEMP_PICKLE_NAME, TEMP_CSV_NAME, TEMP_DBM_NAME]:
    if os.path.exists(fn):
        print fn, "already exists.  Please remove this file before " \
              "running these tests (a file by that name will be " \
              "created and destroyed as part of the tests)."
        sys.exit(1)

class dbexpimpTest(unittest.TestCase):
    def tearDown(self):
        try:
            os.remove(TEMP_PICKLE_NAME)
        except OSError:
            pass
        try:
            os.remove(TEMP_CSV_NAME)
        except OSError:
            pass
        try:
            os.remove(TEMP_DBM_NAME)
        except OSError:
            pass
        
    def test_csv_module_import(self):
        """Check that we don't import the old object craft csv module."""
        self.assert_(hasattr(sb_dbexpimp.csv, "reader"))

    def test_pickle_export(self):
        # Create a pickled classifier to export.
        bayes = PickledClassifier(TEMP_PICKLE_NAME)
        # Stuff some messages in it so it's not empty.
        bayes.learn(tokenize(spam1), True)
        bayes.learn(tokenize(good1), False)
        # Save.
        bayes.store()
        # Export.
        sb_dbexpimp.runExport(TEMP_PICKLE_NAME, "pickle", TEMP_CSV_NAME)
        # Verify that the CSV holds all the original data (and, by using
        # the CSV module to open it, that it is valid CSV data).
        fp = open(TEMP_CSV_NAME, "rb")
        reader = sb_dbexpimp.csv.reader(fp)
        (nham, nspam) = reader.next()
        self.assertEqual(int(nham), bayes.nham)
        self.assertEqual(int(nspam), bayes.nspam)
        for (word, hamcount, spamcount) in reader:
            word = sb_dbexpimp.uunquote(word)
            self.assert_(word in bayes._wordinfokeys())
            wi = bayes._wordinfoget(word)
            self.assertEqual(int(hamcount), wi.hamcount)
            self.assertEqual(int(spamcount), wi.spamcount)
        
    def test_dbm_export(self):
        # Create a dbm classifier to export.
        bayes = DBDictClassifier(TEMP_DBM_NAME)
        # Stuff some messages in it so it's not empty.
        bayes.learn(tokenize(spam1), True)
        bayes.learn(tokenize(good1), False)
        # Save & Close.
        bayes.store()
        bayes.close()
        # Export.
        sb_dbexpimp.runExport(TEMP_DBM_NAME, "dbm", TEMP_CSV_NAME)
        # Reopen the original.
        bayes = open_storage(TEMP_DBM_NAME, "dbm")
        # Verify that the CSV holds all the original data (and, by using
        # the CSV module to open it, that it is valid CSV data).
        fp = open(TEMP_CSV_NAME, "rb")
        reader = sb_dbexpimp.csv.reader(fp)
        (nham, nspam) = reader.next()
        self.assertEqual(int(nham), bayes.nham)
        self.assertEqual(int(nspam), bayes.nspam)
        for (word, hamcount, spamcount) in reader:
            word = sb_dbexpimp.uunquote(word)
            self.assert_(word in bayes._wordinfokeys())
            wi = bayes._wordinfoget(word)
            self.assertEqual(int(hamcount), wi.hamcount)
            self.assertEqual(int(spamcount), wi.spamcount)

    def test_import_to_pickle(self):
        # Create a CSV file to import.
        temp = open(TEMP_CSV_NAME, "wb")
        temp.write("3,4\n")
        csv_data = {"this":(2,1), "is":(0,1), "a":(3,4), 'test':(1,1),
                    "of":(1,0), "the":(1,2), "import":(3,1)}
        for word, (ham, spam) in csv_data.items():
            temp.write("%s,%s,%s\n" % (word, ham, spam))
        temp.close()
        sb_dbexpimp.runImport(TEMP_PICKLE_NAME, "pickle", True,
                              TEMP_CSV_NAME)
        # Open the converted file and verify that it has all the data from
        # the CSV file (and by opening it, that it is a valid pickle).
        bayes = open_storage(TEMP_PICKLE_NAME, "pickle")
        self.assertEqual(bayes.nham, 3)
        self.assertEqual(bayes.nspam, 4)
        for word, (ham, spam) in csv_data.items():
            word = sb_dbexpimp.uquote(word)
            self.assert_(word in bayes._wordinfokeys())
            wi = bayes._wordinfoget(word)
            self.assertEqual(wi.hamcount, ham)
            self.assertEqual(wi.spamcount, spam)

    def test_import_to_dbm(self):
        # Create a CSV file to import.
        temp = open(TEMP_CSV_NAME, "wb")
        temp.write("3,4\n")
        csv_data = {"this":(2,1), "is":(0,1), "a":(3,4), 'test':(1,1),
                    "of":(1,0), "the":(1,2), "import":(3,1)}
        for word, (ham, spam) in csv_data.items():
            temp.write("%s,%s,%s\n" % (word, ham, spam))
        temp.close()
        sb_dbexpimp.runImport(TEMP_DBM_NAME, "dbm", True, TEMP_CSV_NAME)
        # Open the converted file and verify that it has all the data from
        # the CSV file (and by opening it, that it is a valid dbm file).
        bayes = open_storage(TEMP_DBM_NAME, "dbm")
        self.assertEqual(bayes.nham, 3)
        self.assertEqual(bayes.nspam, 4)
        for word, (ham, spam) in csv_data.items():
            word = sb_dbexpimp.uquote(word)
            self.assert_(word in bayes._wordinfokeys())
            wi = bayes._wordinfoget(word)
            self.assertEqual(wi.hamcount, ham)
            self.assertEqual(wi.spamcount, spam)

    def test_merge_to_pickle(self):
        # Create a pickled classifier to merge with.
        bayes = PickledClassifier(TEMP_PICKLE_NAME)
        # Stuff some messages in it so it's not empty.
        bayes.learn(tokenize(spam1), True)
        bayes.learn(tokenize(good1), False)
        # Save.
        bayes.store()
        # Create a CSV file to import.
        nham, nspam = 3,4
        temp = open(TEMP_CSV_NAME, "wb")
        temp.write("%d,%d\n" % (nham, nspam))
        csv_data = {"this":(2,1), "is":(0,1), "a":(3,4), 'test':(1,1),
                    "of":(1,0), "the":(1,2), "import":(3,1)}
        for word, (ham, spam) in csv_data.items():
            temp.write("%s,%s,%s\n" % (word, ham, spam))
        temp.close()
        sb_dbexpimp.runImport(TEMP_PICKLE_NAME, "pickle", False,
                              TEMP_CSV_NAME)
        # Open the converted file and verify that it has all the data from
        # the CSV file (and by opening it, that it is a valid pickle),
        # and the data from the original pickle.
        bayes2 = open_storage(TEMP_PICKLE_NAME, "pickle")
        self.assertEqual(bayes2.nham, nham + bayes.nham)
        self.assertEqual(bayes2.nspam, nspam + bayes.nspam)
        words = bayes._wordinfokeys()
        words.extend(csv_data.keys())
        for word in words:
            word = sb_dbexpimp.uquote(word)
            self.assert_(word in bayes2._wordinfokeys())
            h, s = csv_data.get(word, (0,0))
            wi = bayes._wordinfoget(word)
            if wi:
                h += wi.hamcount
                s += wi.spamcount
            wi2 = bayes2._wordinfoget(word)
            self.assertEqual(h, wi2.hamcount)
            self.assertEqual(s, wi2.spamcount)

    def test_merge_to_dbm(self):
        # Create a dbm classifier to merge with.
        bayes = DBDictClassifier(TEMP_DBM_NAME)
        # Stuff some messages in it so it's not empty.
        bayes.learn(tokenize(spam1), True)
        bayes.learn(tokenize(good1), False)
        # Save data to check against.
        original_nham = bayes.nham
        original_nspam = bayes.nspam
        original_data = {}
        for key in bayes._wordinfokeys():
            original_data[key] = bayes._wordinfoget(key)
        # Save & Close.
        bayes.store()
        bayes.close()
        # Create a CSV file to import.
        nham, nspam = 3,4
        temp = open(TEMP_CSV_NAME, "wb")
        temp.write("%d,%d\n" % (nham, nspam))
        csv_data = {"this":(2,1), "is":(0,1), "a":(3,4), 'test':(1,1),
                    "of":(1,0), "the":(1,2), "import":(3,1)}
        for word, (ham, spam) in csv_data.items():
            temp.write("%s,%s,%s\n" % (word, ham, spam))
        temp.close()
        sb_dbexpimp.runImport(TEMP_DBM_NAME, "dbm", False, TEMP_CSV_NAME)
        # Open the converted file and verify that it has all the data from
        # the CSV file (and by opening it, that it is a valid dbm file),
        # and the data from the original dbm database.
        bayes2 = open_storage(TEMP_DBM_NAME, "dbm")
        self.assertEqual(bayes2.nham, nham + original_nham)
        self.assertEqual(bayes2.nspam, nspam + original_nspam)
        words = original_data.keys()[:]
        words.extend(csv_data.keys())
        for word in words:
            word = sb_dbexpimp.uquote(word)
            self.assert_(word in bayes2._wordinfokeys())
            h, s = csv_data.get(word, (0,0))
            wi = original_data.get(word, None)
            if wi:
                h += wi.hamcount
                s += wi.spamcount
            wi2 = bayes2._wordinfoget(word)
            self.assertEqual(h, wi2.hamcount)
            self.assertEqual(s, wi2.spamcount)


def suite():
    suite = unittest.TestSuite()
    for cls in (dbexpimpTest,
               ):
        suite.addTest(unittest.makeSuite(cls))
    return suite

if __name__=='__main__':
    sb_test_support.unittest_main(argv=sys.argv + ['suite'])
