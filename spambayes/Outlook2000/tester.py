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
from win32com.client import constants
from time import sleep

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
    for i in range(100):
        pythoncom.PumpWaitingMessages()
        sleep(0.01)

# Find the top 'n' words in the Spam database that are clearly
# marked as either ham or spam.  Simply enumerates the
# bayes word list looking for any word with zero count in the
# non-requested category.
def FindTopWords(bayes, num, get_spam):
    items = []
    for word, info in bayes.wordinfo.items():
        if ":" in word:
            continue
        if get_spam:
            if info.hamcount==0:
                items.append((info.spamcount, word))
        else:
            if info.spamcount==0:
                items.append((info.hamcount, word))
    items.sort()
    return [item[1] for item in items]

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
        msg = self.CreateTestMessage(spam_status)
        msg.Save() # Put into "Drafts".
        assert self.FindTestMessage(self.folder_drafts) is not None
        # Move it to the specified folder
        msg.Move(folder)
        # And now find it in the specified folder
        return self.FindTestMessage(folder)

    def CreateTestMessage(self, spam_status):
        words = []
        if spam_status != SPAM:
            words.extend(FindTopWords(self.manager.bayes, 50, False))
        if spam_status != HAM:
            words.extend(FindTopWords(self.manager.bayes, 50, True))
        # Create a new blank message with our words
        msg = self.manager.outlook.CreateItem(0)
        msg.Body = "\n".join(words)
        msg.Subject = TEST_SUBJECT
        return msg

# The tests themselves.
# The "spam" test is huge - we do standard filter tests, but
# also do incremental retrain tests.
def TestSpamFilter(driver):
    nspam = driver.manager.bayes.nspam
    nham = driver.manager.bayes.nham
    import copy
    original_bayes = copy.copy(driver.manager.bayes)
    # Create a spam message in the Inbox - it should get immediately filtered
    msg = driver.CreateTestMessageInFolder(SPAM, driver.folder_watch)
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

    if driver.manager.bayes.wordinfo != original_bayes.wordinfo:
        TestFailed("The bayes object's 'wordinfo' did not compare the same at the end of all this!")
    if driver.manager.bayes.probcache != original_bayes.probcache:
        TestFailed("The bayes object's 'probcache' did not compare the same at the end of all this!")

    spam_msg.Delete()
    print "Created a Spam message, and saw it get filtered and trained."

def TestHamFilter(driver):
    # Create a spam message in the Inbox - it should get immediately filtered
    msg = driver.CreateTestMessageInFolder(HAM, driver.folder_watch)
    # sleep to ensure filtering.
    WaitForFilters()
    # It should still be in the Inbox.
    if driver.FindTestMessage(driver.folder_watch) is None:
        TestFailed("The test ham message appeared to have been filtered!")
    msg.Delete()
    print "Created a Ham message, and saw it remain in place."

def TestUnsureFilter(driver):
    # Create a spam message in the Inbox - it should get immediately filtered
    msg = driver.CreateTestMessageInFolder(UNSURE, driver.folder_watch)
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

def test(manager = None):
    # Run the tests - called from our plugin.
    driver = Driver(manager)
    assert driver.manager.config.filter.enabled, "Filtering must be enabled for these tests"
    assert driver.manager.config.training.train_recovered_spam and \
           driver.manager.config.training.train_manual_spam, "Incremental training must be enabled for these tests"
    driver.CleanAllTestMessages()
    TestSpamFilter(driver)
    TestUnsureFilter(driver)
    TestHamFilter(driver)
    driver.CleanAllTestMessages()

if __name__=='__main__':
    print "NOTE: This will NOT work from the command line"
    print "(it nearly will, and is useful for debugging the tests"
    print "themselves, so we will run them anyway!)"
    test()
