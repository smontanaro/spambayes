# unit tester for the Outlook addin.
#
# Note we are only attempting to test Outlook specific
# functionality, such as filters, etc.
#
# General process is to create test messages known to contain ham/spam
# keywords, and tracking their progress through the filters.  We also
# move this test message back around, and watch the incremental retrain
# in action.  Also checks that the message correctly remains classified
# after a message move.
from __future__ import generators

from win32com.client import constants
from time import sleep
import copy

HAM="ham"
SPAM="spam"
UNSURE="unsure"

TEST_SUBJECT = "SpamBayes addin auto-generated test message"

class TestFailure(Exception):
    pass

def TestFailed(msg):
    raise TestFailure(msg)

def WaitForFilters():
    import pythoncom
    # Must wait longer than normal, so when run with a timer we still work.
    for i in range(500):
        pythoncom.PumpWaitingMessages()
        sleep(0.01)

def DictExtractor(bayes):
    for k, v in bayes.wordinfo.items():
        yield k, v

def DBExtractor(bayes):
    # We use bsddb3 now if we can
    try:
        import bsddb3 as bsddb
        bsddb_error = bsddb.db.DBNotFoundError
    except ImportError:
        import bsddb
        bsddb_error = bsddb.error
    key = bayes.dbm.first()[0]
    if key not in ["saved state"]:
        yield key, bayes._wordinfoget(key)
    while True:
        try:
            key = bayes.dbm.next()[0]
        except bsddb.error:
            break
        except bsddb_error:
            break
        if key not in ["saved state"]:
            yield key, bayes._wordinfoget(key)

# Find the top 'n' words in the Spam database that are clearly
# marked as either ham or spam.  Simply enumerates the
# bayes word list looking for any word with zero count in the
# non-requested category.
def FindTopWords(bayes, num, get_spam):
    items = []
    try:
        bayes.db # bsddb style
        extractor = DBExtractor
    except AttributeError:
        extractor = DictExtractor

    for word, info in extractor(bayes):
        if ":" in word:
            continue
        if get_spam:
            if info.hamcount==0:
                items.append((info.spamcount, word, info))
        else:
            if info.spamcount==0:
                items.append((info.hamcount, word, info))
    items.sort()
    items.reverse()
    # Throw an error if we don't have enough tokens - otherwise
    # the test itself may fail, which will be more confusing than this.
    if len(items) < num:
        TestFailed("Error: could not find %d words with Spam=%s - only found %d" % (num, get_spam, len(items)))
    ret = {}
    for n, word, info in items[:num]:
        ret[word]=copy.copy(info)
    return ret

# A little driver/manager for our tests
class Driver:
    def __init__(self, mgr):
        if mgr is None:
            import manager
            mgr = manager.GetManager()
        self.manager = mgr
        # Remember the "spam" folder.
        folder = mgr.message_store.GetFolder(mgr.config.filter.spam_folder_id)
        self.folder_spam = folder.GetOutlookItem()
        # Remember the "unsure" folder.
        folder = mgr.message_store.GetFolder(mgr.config.filter.unsure_folder_id)
        self.folder_unsure = folder.GetOutlookItem()
        # The "watch" folder is a folder we can stick stuff into to have them
        # filtered - just use the first one nominated.
        for folder in mgr.message_store.GetFolderGenerator(
                                mgr.config.filter.watch_folder_ids,
                                mgr.config.filter.watch_include_sub):
            self.folder_watch = folder.GetOutlookItem()
            break

        # And the drafts folder where new messages are created.
        self.folder_drafts = mgr.outlook.Session.GetDefaultFolder(constants.olFolderDrafts)

    def FindTestMessage(self, folder):
        subject = TEST_SUBJECT
        items = folder.Items
        return items.Find("[Subject] = '%s'" % (subject,))

    def _CleanTestMessageFromFolder(self, folder):
        subject = TEST_SUBJECT
        num = 0
        while True:
            msg = self.FindTestMessage(folder)
            if msg is None:
                break
            msg.Delete()
            num += 1
        if num:
            print "Cleaned %d test messages from folder '%s'" % (num, folder.Name)

    def CleanAllTestMessages(self):
        subject = TEST_SUBJECT
        self._CleanTestMessageFromFolder(self.folder_spam)
        self._CleanTestMessageFromFolder(self.folder_unsure)
        self._CleanTestMessageFromFolder(self.folder_watch)
        self._CleanTestMessageFromFolder(self.folder_drafts)

    def CreateTestMessageInFolder(self, spam_status, folder):
        msg, words = self.CreateTestMessage(spam_status)
        msg.Save() # Put into "Drafts".
        assert self.FindTestMessage(self.folder_drafts) is not None
        # Move it to the specified folder
        msg.Move(folder)
        # And now find it in the specified folder
        return self.FindTestMessage(folder), words

    def CreateTestMessage(self, spam_status):
        words = {}
        if spam_status != SPAM:
            words.update(FindTopWords(self.manager.bayes, 50, False))
        if spam_status != HAM:
            words.update(FindTopWords(self.manager.bayes, 50, True))
        # Create a new blank message with our words
        msg = self.manager.outlook.CreateItem(0)
        msg.Body = "\n".join(words.keys())
        msg.Subject = TEST_SUBJECT
        return msg, words

def check_words(words, bayes, spam_offset, ham_offset):
    for word, existing_info in words.items():
        new_info = bayes._wordinfoget(word)
        if existing_info.spamcount+spam_offset != new_info.spamcount or \
           existing_info.hamcount+ham_offset != new_info.hamcount:
            TestFailed("Word check for '%s failed. "
                       "old spam/ham=%d/%d, new spam/ham=%d/%d,"
                       "spam_offset=%d, ham_offset=%d" % \
                       (word,
                        existing_info.spamcount, existing_info.hamcount,
                        new_info.spamcount, new_info.hamcount,
                        spam_offset, ham_offset))

# The tests themselves.
# The "spam" test is huge - we do standard filter tests, but
# also do incremental retrain tests.
def TestSpamFilter(driver):
    nspam = driver.manager.bayes.nspam
    nham = driver.manager.bayes.nham
    original_bayes = copy.copy(driver.manager.bayes)
    # Create a spam message in the Inbox - it should get immediately filtered
    msg, words = driver.CreateTestMessageInFolder(SPAM, driver.folder_watch)
    # sleep to ensure filtering.
    WaitForFilters()
    # It should no longer be in the Inbox.
    if driver.FindTestMessage(driver.folder_watch) is not None:
        TestFailed("The test message appeared to not be filtered")
    # It should be in the "sure is spam" folder.
    spam_msg = driver.FindTestMessage(driver.folder_spam)
    if spam_msg is None:
        TestFailed("The test message vanished from the Inbox, but didn't appear in Spam")
    # Check that none of the above caused training.
    if nspam != driver.manager.bayes.nspam:
        TestFailed("Something caused a new spam message to appear")
    if nham != driver.manager.bayes.nham:
        TestFailed("Something caused a new ham message to appear")
    check_words(words, driver.manager.bayes, 0, 0)

    # Now move the message back to the inbox - it should get trained.
    store_msg = driver.manager.message_store.GetMessage(spam_msg)
    import train
    if train.been_trained_as_ham(store_msg, driver.manager):
        TestFailed("This new spam message should not have been trained as ham yet")
    if train.been_trained_as_spam(store_msg, driver.manager):
        TestFailed("This new spam message should not have been trained as spam yet")
    spam_msg.Move(driver.folder_watch)
    WaitForFilters()
    spam_msg = driver.FindTestMessage(driver.folder_watch)
    if spam_msg is None:
        TestFailed("The message appears to have been filtered out of the watch folder")
    store_msg = driver.manager.message_store.GetMessage(spam_msg)
    need_untrain = True
    try:
        if nspam != driver.manager.bayes.nspam:
            TestFailed("There were not the same number of spam messages after a re-train")
        if nham+1 != driver.manager.bayes.nham:
            TestFailed("There was not one more ham messages after a re-train")
        if train.been_trained_as_spam(store_msg, driver.manager):
            TestFailed("This new spam message should not have been trained as spam yet")
        if not train.been_trained_as_ham(store_msg, driver.manager):
            TestFailed("This new spam message should have been trained as ham now")
        # word infos should have one extra ham
        check_words(words, driver.manager.bayes, 0, 1)
        # Now move it back to the Spam folder.
        # This should see the message un-trained as ham, and re-trained as Spam
        spam_msg.Move(driver.folder_spam)
        WaitForFilters()
        spam_msg = driver.FindTestMessage(driver.folder_spam)
        if spam_msg is None:
            TestFailed("Could not find the message in the Spam folder")
        store_msg = driver.manager.message_store.GetMessage(spam_msg)
        if nspam +1 != driver.manager.bayes.nspam:
            TestFailed("There should be one more spam now")
        if nham != driver.manager.bayes.nham:
            TestFailed("There should be the same number of hams again")
        if not train.been_trained_as_spam(store_msg, driver.manager):
            TestFailed("This new spam message should have been trained as spam by now")
        if train.been_trained_as_ham(store_msg, driver.manager):
            TestFailed("This new spam message should have been un-trained as ham")
        # word infos should have one extra spam, no extra ham
        check_words(words, driver.manager.bayes, 1, 0)
        # Move the message to another folder, and make sure we still
        # identify it correctly as having been trained.
        # Move to the "unsure" folder, just cos we know about it, and
        # we know that no special watching of this folder exists.
        spam_msg.Move(driver.folder_unsure)
        spam_msg = driver.FindTestMessage(driver.folder_unsure)
        if spam_msg is None:
            TestFailed("Could not find the message in the Unsure folder")
        store_msg = driver.manager.message_store.GetMessage(spam_msg)
        if not train.been_trained_as_spam(store_msg, driver.manager):
            TestFailed("Message was not identified as Spam after moving")

        # word infos still be 'spam'
        check_words(words, driver.manager.bayes, 1, 0)

        # Now undo the damage we did.
        was_spam = train.untrain_message(store_msg, driver.manager)
        if not was_spam:
            TestFailed("Untraining this message did not indicate it was spam")
        if train.been_trained_as_spam(store_msg, driver.manager) or \
           train.been_trained_as_ham(store_msg, driver.manager):
            TestFailed("Untraining this message kept it has ham/spam")
        need_untrain = False
    finally:
        if need_untrain:
            train.untrain_message(store_msg, driver.manager)

    # Check all the counts are back where we started.
    if nspam != driver.manager.bayes.nspam:
        TestFailed("Spam count didn't get back to the same")
    if nham != driver.manager.bayes.nham:
        TestFailed("Ham count didn't get back to the same")
    check_words(words, driver.manager.bayes, 0, 0)

    if driver.manager.bayes.wordinfo != original_bayes.wordinfo:
        TestFailed("The bayes object's 'wordinfo' did not compare the same at the end of all this!")
    if driver.manager.bayes.probcache != original_bayes.probcache:
        TestFailed("The bayes object's 'probcache' did not compare the same at the end of all this!")

    spam_msg.Delete()
    print "Created a Spam message, and saw it get filtered and trained."

def TestHamFilter(driver):
    # Create a ham message in the Inbox - it should not get filtered
    msg, words = driver.CreateTestMessageInFolder(HAM, driver.folder_watch)
    # sleep to ensure filtering.
    WaitForFilters()
    # It should still be in the Inbox.
    if driver.FindTestMessage(driver.folder_watch) is None:
        TestFailed("The test ham message appeared to have been filtered!")
    msg.Delete()
    print "Created a Ham message, and saw it remain in place."

def TestUnsureFilter(driver):
    # Create a spam message in the Inbox - it should get immediately filtered
    msg, words = driver.CreateTestMessageInFolder(UNSURE, driver.folder_watch)
    # sleep to ensure filtering.
    WaitForFilters()
    # It should no longer be in the Inbox.
    if driver.FindTestMessage(driver.folder_watch) is not None:
        TestFailed("The test unsure message appeared to not be filtered")
    # It should be in the "unsure" folder.
    spam_msg = driver.FindTestMessage(driver.folder_unsure)
    if spam_msg is None:
        TestFailed("The test message vanished from the Inbox, but didn't appear in Unsure")
    spam_msg.Delete()
    print "Created an unsure message, and saw it get filtered"

def run_tests(manager):
    driver = Driver(manager)
    manager.Save() # necessary after a full retrain
    assert driver.manager.config.filter.enabled, "Filtering must be enabled for these tests"
    assert driver.manager.config.training.train_recovered_spam and \
           driver.manager.config.training.train_manual_spam, "Incremental training must be enabled for these tests"
    driver.CleanAllTestMessages()
    TestSpamFilter(driver)
    TestUnsureFilter(driver)
    TestHamFilter(driver)
    driver.CleanAllTestMessages()

def run_filter_tests(manager):
    # setup config to save info with the message, and test
    print "*" * 10, "Running tests with save_spam_info=True, timer off"
    manager.config.experimental.timer_start_delay = 0
    manager.config.experimental.timer_interval = 0
    manager.config.filter.save_spam_info = True
    manager.addin.FiltersChanged() # to ensure correct filtler in place
    run_tests(manager)
    # do it again with the same config, just to prove we can.
    print "*" * 10, "Running them again with save_spam_info=True"
    run_tests(manager)
    # enable the timer.
    manager.config.experimental.timer_start_delay = 1000
    manager.config.experimental.timer_interval = 500
    manager.addin.FiltersChanged() # to switch to timer based filters.
    print "*" * 10, "Running them again with save_spam_info=True, and timer enabled"
    run_tests(manager)
    # and with save_spam_info False.
    print "*" * 10, "Running tests with save_spam_info=False"
    manager.config.filter.save_spam_info = False
    run_tests(manager)
    print "*" * 10, "Filtering tests completed successfully."

def run_nonfilter_tests(manager):
    # And now some other 'sanity' checks.
    # Check messages we are unable to score.
    # Must enable the filtering code for this test
    import msgstore
    msgstore.test_suite_running = False
    try:
        num_found = num_looked = 0
        for folder_ids, include_sub in [
            (manager.config.filter.watch_folder_ids, manager.config.filter.watch_include_sub),
            ([manager.config.filter.spam_folder_id], False),
            ]:
            for folder in manager.message_store.GetFolderGenerator(folder_ids, include_sub):
                for message in folder.GetMessageGenerator(False):
                    # If not ipm.note, then no point reporting - but any
                    # ipm.note messages we don't want to filter should be
                    # reported.
                    num_looked += 1
                    if not message.IsFilterCandidate() and \
                        message.msgclass.lower().startswith("ipm.note"):
                        if num_found == 0:
                            print "*" * 80
                            print "WARNING: We found the following messages in your folders that would not be filtered by the addin"
                            print "If any of these messages should be filtered, we have a bug!"
                        num_found += 1
                        print " %s/%s" % (folder.name, message.subject)
        print "Checked %d items, %d non-filterable items found" % (num_looked, num_found)
    finally:
        msgstore.test_suite_running = True

def test(manager):
    import msgstore, win32ui
    win32ui.DoWaitCursor(1)
    try: # restore the plugin config at exit.
        msgstore.test_suite_running = True
        run_filter_tests(manager)
        run_nonfilter_tests(manager)
    finally:
        # Always restore configuration to how we started.
        msgstore.test_suite_running = False
        manager.LoadConfig()
        manager.addin.FiltersChanged() # restore original filters.
        win32ui.DoWaitCursor(0)

if __name__=='__main__':
    print "NOTE: This will NOT work from the command line"
    print "(it nearly will, and is useful for debugging the tests"
    print "themselves, so we will run them anyway!)"
    test()
