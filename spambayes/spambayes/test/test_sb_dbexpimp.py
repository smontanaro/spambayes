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
from test_sb_server import good1, spam1

# WARNING!
# If these files exist when running this test, they will be deleted.
TEMP_PICKLE_NAME = os.path.join(os.path.dirname(__file__), "temp.pik")
TEMP_CSV_NAME = os.path.join(os.path.dirname(__file__), "temp.csv")
TEMP_DBM_NAME = os.path.join(os.path.dirname(__file__), "temp.dbm")

class dbexpimpTest(unittest.TestCase):
    def tearDown(self):
        try:
            os.remove(TEMP_PICKLE_NAME)
            os.remove(TEMP_CSV_NAME)
            os.remove(TEMP_DBM_NAME)
        except OSError:
            pass
        
    def test_csv_import(self):
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


def suite():
    suite = unittest.TestSuite()
    for cls in (dbexpimpTest,
               ):
        suite.addTest(unittest.makeSuite(cls))
    return suite

if __name__=='__main__':
    sb_test_support.unittest_main(argv=sys.argv + ['suite'])
