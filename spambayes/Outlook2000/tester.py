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
import sys
from time import sleep
import copy
import rfc822
import cStringIO
import threading

from spambayes.storage import STATE_KEY

import msgstore

from win32com.mapi import mapi, mapiutil
import pythoncom

HAM="ham"
SPAM="spam"
UNSURE="unsure"

TEST_SUBJECT = "SpamBayes addin auto-generated test message"

class TestFailure(Exception):
    pass

def TestFailed(msg):
    raise TestFailure(msg)

def AssertRaises(exception, func, *args):
    try:
        func(*args)
        raise TestFailed("Function '%s' should have raised '%r', but it worked!" % \
                         (func, exception))
    except:
        exc_type = sys.exc_info()[0]
        if exc_type == exception or issubclass(exc_type, exception):
            return
        raise

filter_event = threading.Event()

def WaitForFilters():
    # Must wait longer than normal, so when run with a timer we still work.
    filter_event.clear()
    for i in range(500):
        pythoncom.PumpWaitingMessages()
        if filter_event.isSet():
            break
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
    if key != STATE_KEY:
        yield key, bayes._wordinfoget(key)
    while True:
        try:
            key = bayes.dbm.next()[0]
        except bsddb.error:
            break
        except bsddb_error:
            break
        if key != STATE_KEY:
            yield key, bayes._wordinfoget(key)

# Find the top 'n' words in the Spam database that are clearly
# marked as either ham or spam.  Simply enumerates the
# bayes word list looking for any word with zero count in the
# non-requested category.
_top_ham = None
_top_spam = None
def FindTopWords(bayes, num, get_spam):
    global _top_spam, _top_ham
    if get_spam and _top_spam: return _top_spam
    if not get_spam and _top_ham: return _top_ham
    items = []
    try:
        bayes.db # bsddb style
        extractor = DBExtractor
    except AttributeError:
        extractor = DictExtractor

    for word, info in extractor(bayes):
        if info is None:
            break
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
    if get_spam:
        _top_spam = ret
    else:
        _top_ham = ret
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
        # And the drafts folder where new messages are created.
        self.folder_drafts = mgr.outlook.Session.GetDefaultFolder(constants.olFolderDrafts)

    def GetWatchFolderGenerator(self):
        mgr = self.manager
        gen = mgr.message_store.GetFolderGenerator(
                                mgr.config.filter.watch_folder_ids,
                                mgr.config.filter.watch_include_sub)
        for f in gen:
            yield f, f.GetOutlookItem()

    def FindTestMessage(self, folder):
        subject = TEST_SUBJECT
        items = folder.Items
        return items.Find("[Subject] = '%s'" % (subject,))

    def CheckMessageFilteredFrom(self, folder):
        # For hotmail accounts, the message may take a little time to actually
        # be removed from the original folder (ie, it appears in the "dest"
        # folder before it vanished.
        for i in range(5):
            if self.FindTestMessage(folder) is None:
                break
            for j in range(10):
                sleep(.05)
        else:
            ms_folder = self.manager.message_store.GetFolder(folder)
            TestFailed("The test message remained in folder '%s'" % ms_folder.GetFQName())

    def _CleanTestMessageFromFolder(self, folder):
        subject = TEST_SUBJECT
        num = 0
        # imap/hotmail etc only soft delete, and I see no way to differentiate
        # force the user to purge them manually
        for i in range(50):
            msg = self.FindTestMessage(folder)
            if msg is None:
                break
            msg.Delete()
        else:
            raise TestFailed("Old test messages appear to still exist.  These may" \
                             "be 'soft-deleted' - you will need to purge them manually")
        if num:
            print "Cleaned %d test messages from folder '%s'" % (num, folder.Name)

    def CleanAllTestMessages(self):
        self._CleanTestMessageFromFolder(self.folder_spam)
        self._CleanTestMessageFromFolder(self.folder_unsure)
        self._CleanTestMessageFromFolder(self.folder_drafts)
        for msf, of in self.GetWatchFolderGenerator():
            self._CleanTestMessageFromFolder(of)

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
        bayes = self.manager.classifier_data.bayes
        if spam_status != SPAM:
            words.update(FindTopWords(bayes, 50, False))
        if spam_status != HAM:
            words.update(FindTopWords(bayes, 50, True))
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
    bayes = driver.manager.classifier_data.bayes
    nspam = bayes.nspam
    nham = bayes.nham
    original_bayes = copy.copy(driver.manager.classifier_data.bayes)
    # for each watch folder, create a spam message, and do the training thang
    for msf_watch, folder_watch in driver.GetWatchFolderGenerator():
        print "Performing Spam test on watch folder '%s'..." % msf_watch.GetFQName()
        # Create a spam message in the Inbox - it should get immediately filtered
        msg, words = driver.CreateTestMessageInFolder(SPAM, folder_watch)
        # sleep to ensure filtering.
        WaitForFilters()
        # It should no longer be in the Inbox.
        driver.CheckMessageFilteredFrom(folder_watch)
        # It should be in the "sure is spam" folder.
        spam_msg = driver.FindTestMessage(driver.folder_spam)
        if spam_msg is None:
            TestFailed("The test message vanished from the Inbox, but didn't appear in Spam")
        # Check that none of the above caused training.
        if nspam != bayes.nspam:
            TestFailed("Something caused a new spam message to appear")
        if nham != bayes.nham:
            TestFailed("Something caused a new ham message to appear")
        check_words(words, bayes, 0, 0)

        # Now move the message back to the inbox - it should get trained.
        store_msg = driver.manager.message_store.GetMessage(spam_msg)
        driver.manager.classifier_data.message_db.load_msg(store_msg)
        import train
        if train.been_trained_as_ham(store_msg):
            TestFailed("This new spam message should not have been trained as ham yet")
        if train.been_trained_as_spam(store_msg):
            TestFailed("This new spam message should not have been trained as spam yet")
        spam_msg.Move(folder_watch)
        WaitForFilters()
        spam_msg = driver.FindTestMessage(folder_watch)
        if spam_msg is None:
            TestFailed("The message appears to have been filtered out of the watch folder")
        store_msg = driver.manager.message_store.GetMessage(spam_msg)
        driver.manager.classifier_data.message_db.load_msg(store_msg)
        need_untrain = True
        try:
            if nspam != bayes.nspam:
                TestFailed("There were not the same number of spam messages after a re-train")
            if nham+1 != bayes.nham:
                TestFailed("There was not one more ham messages after a re-train")
            if train.been_trained_as_spam(store_msg):
                TestFailed("This new spam message should not have been trained as spam yet")
            if not train.been_trained_as_ham(store_msg):
                TestFailed("This new spam message should have been trained as ham now")
            # word infos should have one extra ham
            check_words(words, bayes, 0, 1)
            # Now move it back to the Spam folder.
            # This should see the message un-trained as ham, and re-trained as Spam
            spam_msg.Move(driver.folder_spam)
            WaitForFilters()
            spam_msg = driver.FindTestMessage(driver.folder_spam)
            if spam_msg is None:
                TestFailed("Could not find the message in the Spam folder")
            store_msg = driver.manager.message_store.GetMessage(spam_msg)
            driver.manager.classifier_data.message_db.load_msg(store_msg)
            if nspam +1 != bayes.nspam:
                TestFailed("There should be one more spam now")
            if nham != bayes.nham:
                TestFailed("There should be the same number of hams again")
            if not train.been_trained_as_spam(store_msg):
                TestFailed("This new spam message should have been trained as spam by now")
            if train.been_trained_as_ham(store_msg):
                TestFailed("This new spam message should have been un-trained as ham")
            # word infos should have one extra spam, no extra ham
            check_words(words, bayes, 1, 0)
            # Move the message to another folder, and make sure we still
            # identify it correctly as having been trained.
            # Move to the "unsure" folder, just cos we know about it, and
            # we know that no special watching of this folder exists.
            spam_msg.Move(driver.folder_unsure)
            spam_msg = driver.FindTestMessage(driver.folder_unsure)
            if spam_msg is None:
                TestFailed("Could not find the message in the Unsure folder")
            store_msg = driver.manager.message_store.GetMessage(spam_msg)
            driver.manager.classifier_data.message_db.load_msg(store_msg)
            if not train.been_trained_as_spam(store_msg):
                TestFailed("Message was not identified as Spam after moving")

            # word infos still be 'spam'
            check_words(words, bayes, 1, 0)

            # Now undo the damage we did.
            was_spam = train.untrain_message(store_msg, driver.manager.classifier_data)
            driver.manager.classifier_data.message_db.load_msg(store_msg)
            if not was_spam:
                TestFailed("Untraining this message did not indicate it was spam")
            if train.been_trained_as_spam(store_msg) or \
               train.been_trained_as_ham(store_msg):
                TestFailed("Untraining this message kept it has ham/spam")
            need_untrain = False
        finally:
            if need_untrain:
                train.untrain_message(store_msg, driver.manager.classifier_data)

        # Check all the counts are back where we started.
        if nspam != bayes.nspam:
            TestFailed("Spam count didn't get back to the same")
        if nham != bayes.nham:
            TestFailed("Ham count didn't get back to the same")
        check_words(words, bayes, 0, 0)

        if bayes.wordinfo != original_bayes.wordinfo:
            TestFailed("The bayes object's 'wordinfo' did not compare the same at the end of all this!")
        if bayes.probcache != original_bayes.probcache:
            TestFailed("The bayes object's 'probcache' did not compare the same at the end of all this!")

        spam_msg.Delete()
    print "Created a Spam message, and saw it get filtered and trained."

def _DoTestHamTrain(driver, folder1, folder2):
    # [ 780612 ] Outlook incorrectly trains on moved messages
    # Should not train when previously classified message is moved by the user
    # from one watch folder to another.
    bayes = driver.manager.classifier_data.bayes
    nham = bayes.nham
    nspam = bayes.nspam

    # Create a ham message in the Inbox - it wont get filtered if the other
    # tests pass, but we do need to wait for it to be scored.
    msg, words = driver.CreateTestMessageInFolder(HAM, folder1)
    # sleep to ensure filtering.
    WaitForFilters()
    # It should still be in the Inbox.
    if driver.FindTestMessage(folder1) is None:
        TestFailed("The test ham message appeared to have been filtered!")

    # Manually move it to folder2
    msg.Move(folder2)
    # sleep to any processing in this folder.
    WaitForFilters()
    # re-find it in folder2
    msg = driver.FindTestMessage(folder2)
    if driver.FindTestMessage(folder2) is None:
        TestFailed("Couldn't find the ham message we just moved")

    if nspam != bayes.nspam or nham != bayes.nham:
        TestFailed("Move of existing ham caused a train")
    msg.Delete()

def _DoTestHamFilter(driver, folder):
    # Create a ham message in the Inbox - it should not get filtered
    msg, words = driver.CreateTestMessageInFolder(HAM, folder)
    # sleep to ensure filtering.
    WaitForFilters()
    # It should still be in the Inbox.
    if driver.FindTestMessage(folder) is None:
        TestFailed("The test ham message appeared to have been filtered!")
    msg.Delete()

def TestHamFilter(driver):
    # Execute the 'ham' test in every folder we watch.
    mgr = driver.manager
    gen = mgr.message_store.GetFolderGenerator(
                        mgr.config.filter.watch_folder_ids,
                        mgr.config.filter.watch_include_sub)
    num = 0
    folders = []
    for f in gen:
        print "Running ham filter tests on folder '%s'" % f.GetFQName()
        f = f.GetOutlookItem()
        _DoTestHamFilter(driver, f)
        num += 1
        folders.append(f)
    # Now test incremental train logic, between all these folders.
    if len(folders)<2:
        print "NOTE: Can't do incremental training tests as only 1 watch folder is in place"
    else:
        for f in folders:
            # 'targets' is a list of all folders except this
            targets = folders[:]
            targets.remove(f)
            for t in targets:
                _DoTestHamTrain(driver, f, t)
    print "Created a Ham message, and saw it remain in place (in %d watch folders.)" % num

def TestUnsureFilter(driver):
    # Create a spam message in the Inbox - it should get immediately filtered
    for msf_watch, folder_watch in driver.GetWatchFolderGenerator():
        print "Performing Spam test on watch folder '%s'..." % msf_watch.GetFQName()
        msg, words = driver.CreateTestMessageInFolder(UNSURE, folder_watch)
        # sleep to ensure filtering.
        WaitForFilters()
        # It should no longer be in the Inbox.
        driver.CheckMessageFilteredFrom(folder_watch)
        # It should be in the "unsure" folder.
        spam_msg = driver.FindTestMessage(driver.folder_unsure)
        if spam_msg is None:
            TestFailed("The test message vanished from the Inbox, but didn't appear in Unsure")
        spam_msg.Delete()
    print "Created an unsure message, and saw it get filtered"

def run_tests(manager):
    "Filtering tests"
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
    apply_with_new_config(manager,
                          {"Filter.timer_enabled": False,
                           "Filter.save_spam_info" : True,
                          },
                          run_tests, manager)

    apply_with_new_config(manager,
                          {"Filter.timer_enabled": True,
                           "Filter.save_spam_info" : True,
                          },
                          run_tests, manager)
    apply_with_new_config(manager,
                          {"Filter.timer_enabled": False,
                           "Filter.save_spam_info" : False,
                          },
                          run_tests, manager)

    apply_with_new_config(manager,
                          {"Filter.timer_enabled": True,
                           "Filter.save_spam_info" : False,
                          },
                          run_tests, manager)

def apply_with_new_config(manager, new_config_dict, func, *args):
    old_config = {}
    friendly_opts = []
    for name, val in new_config_dict.items():
        sect_name, opt_name = name.split(".")
        old_config[sect_name, opt_name] = manager.options.get(sect_name, opt_name)
        manager.options.set(sect_name, opt_name, val)
        friendly_opts.append("%s=%s" % (name, val))
    manager.addin.FiltersChanged() # to ensure correct filtler in place
    try:
        test_name = getattr(func, "__doc__", None)
        if not test_name: test_name = func.__name__
        print "*" * 10, "Running '%s' with %s" % (test_name, ", ".join(friendly_opts))
        func(*args)
    finally:
        for (sect_name, opt_name), val in old_config.items():
            manager.options.set(sect_name, opt_name, val)

###############################################################################
# "Non-filter" tests are those that don't require us to create messages and
# see them get filtered.
def run_nonfilter_tests(manager):
    # And now some other 'sanity' checks.
    # Check messages we are unable to score.
    # Must enable the filtering code for this test
    msgstore.test_suite_running = False
    try:
        print "Scanning all your good mail and spam for some sanity checks..."
        num_found = num_looked = 0
        num_without_headers = num_without_body = num_without_html_body = 0
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
                    if num_looked % 500 == 0: print " scanned", num_looked, "messages..."
                    if not message.IsFilterCandidate() and \
                        message.msgclass.lower().startswith("ipm.note"):
                        if num_found == 0:
                            print "*" * 80
                            print "WARNING: We found the following messages in your folders that would not be filtered by the addin"
                            print "If any of these messages should be filtered, we have a bug!"
                        num_found += 1
                        print " %s/%s" % (folder.name, message.subject)
                    headers, body, html_body = message._GetMessageTextParts()
                    if not headers: num_without_headers += 1
                    if not body: num_without_body += 1
                    # for HTML, we only check multi-part
                    temp_obj = rfc822.Message(cStringIO.StringIO(headers+"\n\n"))
                    content_type = temp_obj.get("content-type", '')
                    if content_type.lower().startswith("multipart"):
                        if not html_body: num_without_html_body += 1

        print "Checked %d items, %d non-filterable items found" % (num_looked, num_found)
        print "of these items, %d had no headers, %d had no text body and %d had no HTML" % \
                (num_without_headers, num_without_body, num_without_html_body)
    finally:
        msgstore.test_suite_running = True

def run_invalid_id_tests(manager):
    # Do some tests with invalid message and folder IDs.
    print "Doing some 'invalid ID' tests - you should see a couple of warning, but no errors or tracebacks"
    id_no_item = ('0000','0000') # this ID is 'valid' - but there will be no such item
    id_invalid = ('xxxx','xxxx') # this ID is 'invalid' in that the hex-bin conversion fails
    id_empty1 = ('','')
    id_empty2 = ()
    bad_ids = id_no_item, id_invalid, id_empty1, id_empty2
    for id in bad_ids:
        AssertRaises(msgstore.MsgStoreException, manager.message_store.GetMessage, id)
    # Test 'GetFolderGenerator' works with invalid ids.
    for id in bad_ids:
        AssertRaises(msgstore.MsgStoreException, manager.message_store.GetFolder, id)
        ids = manager.config.filter.watch_folder_ids[:]
        ids.append(id)
        found = 0
        for f in manager.message_store.GetFolderGenerator(ids, False):
            found += 1
        if found > len(manager.config.filter.watch_folder_ids):
            raise TestFailed("Seemed to find the extra folder")
        names = manager.FormatFolderNames(ids, False)
        if names.find("<unknown") < 0:
            raise TestFailed("Couldn't find unknown folder in names '%s'" % names)
    print "Finished 'invalid ID' tests"

###############################################################################
# "Failure" tests - execute some tests while provoking the msgstore to simulate
# various MAPI errors.  Although not complete, it does help exercise our code
# paths through the code.
def _restore_mapi_failure():
    msgstore.test_suite_failure = None
    msgstore.test_suite_failure_request = None

def _setup_for_mapi_failure(checkpoint, hr, fail_count = None):
    assert msgstore.test_suite_running, "msgstore should already know its running"
    assert not msgstore.test_suite_failure, "should already have torn down previous failure"
    msgstore.test_suite_failure = pythoncom.com_error, \
                         (hr, "testsuite generated error", None, -1)
    msgstore.test_suite_failure_request = checkpoint
    msgstore.test_suite_failure_count = fail_count

def _setup_mapi_notfound_failure(checkpoint):
    _setup_for_mapi_failure(checkpoint, mapi.MAPI_E_NOT_FOUND)

def _do_single_failure_ham_test(driver, checkpoint, hr, fail_count = None):
    _do_single_failure_test(driver, True, checkpoint, hr, fail_count)

def _do_single_failure_spam_test(driver, checkpoint, hr, fail_count = None):
    _do_single_failure_test(driver, False, checkpoint, hr, fail_count)

def _do_single_failure_test(driver, is_ham, checkpoint, hr, fail_count):
    print "-> Testing MAPI error '%s' in %s" % (mapiutil.GetScodeString(hr),
                                              checkpoint)
    # message moved after we have ID, but before opening.
    for msf, folder in driver.GetWatchFolderGenerator():
        print "Testing in folder '%s'" % msf.GetFQName()
        if is_ham:
            msg, words = driver.CreateTestMessageInFolder(HAM, folder)
        else:
            msg, words = driver.CreateTestMessageInFolder(SPAM, folder)
        try:
            _setup_for_mapi_failure(checkpoint, hr, fail_count)
            try:
                # sleep to ensure filtering.
                WaitForFilters()
            finally:
                _restore_mapi_failure()
            if driver.FindTestMessage(folder) is None:
                TestFailed("We appear to have filtered a message even though we forced 'not found' failure")
        finally:
            if msg is not None:
                msg.Delete()
    print "<- Finished MAPI error '%s' in %s" % (mapiutil.GetScodeString(hr),
                                                 checkpoint)

def do_failure_tests(manager):
    # We setup msgstore to fail for us, then try a few tests.  The idea is to
    # ensure we gracefully degrade in these failures.
    # We set verbosity to min of 1, as this helps us see how the filters handle
    # the errors.
    driver = Driver(manager)
    driver.CleanAllTestMessages()
    old_verbose = manager.verbose
    manager.verbose = max(1, old_verbose)
    try:
        _do_single_failure_ham_test(driver, "MAPIMsgStoreMsg._EnsureObject", mapi.MAPI_E_NOT_FOUND)
        _do_single_failure_ham_test(driver, "MAPIMsgStoreMsg.SetField", -2146644781)
        _do_single_failure_ham_test(driver, "MAPIMsgStoreMsg.Save", -2146644781)
        _do_single_failure_ham_test(driver, "MAPIMsgStoreMsg.Save",
                                    mapi.MAPI_E_OBJECT_CHANGED, fail_count=1)
        # SetReadState???
        _do_single_failure_spam_test(driver, "MAPIMsgStoreMsg._DoCopyMove", mapi.MAPI_E_TABLE_TOO_BIG)

    finally:
        manager.verbose = old_verbose

def run_failure_tests(manager):
    "Forced MAPI failure tests"
    apply_with_new_config(manager,
                          {"Filter.timer_enabled": True,
                          },
                          do_failure_tests, manager)
    apply_with_new_config(manager,
                          {"Filter.timer_enabled": False,
                          },
                          do_failure_tests, manager)

def filter_message_with_event(msg, mgr, all_actions=True):
    import filter
    ret = filter._original_filter_message(msg, mgr, all_actions)
    if ret != "Failed":
        filter_event.set() # only set if it works
    return ret

def test(manager):
    from dialogs import SetWaitCursor
    SetWaitCursor(1)

    import filter
    if "_original_filter_message" not in filter.__dict__:
        filter._original_filter_message = filter.filter_message
        filter.filter_message = filter_message_with_event

    try: # restore the plugin config at exit.
        assert not msgstore.test_suite_running, "already running??"
        msgstore.test_suite_running = True
        assert not manager.test_suite_running, "already running??"
        manager.test_suite_running = True
        run_filter_tests(manager)
        run_failure_tests(manager)
        run_invalid_id_tests(manager)
        # non-filter tests take alot of time - ask if you want to do them
        if manager.AskQuestion("Do you want to run the non-filter tests?" \
                               "\r\n\r\nThese may take some time"):
            run_nonfilter_tests(manager)
        print "*" * 20
        print "Test suite finished without error!"
        print "*" * 20
    finally:
        print "Restoring standard configuration..."
        # Always restore configuration to how we started.
        msgstore.test_suite_running = False
        manager.test_suite_running = False
        manager.LoadConfig()
        manager.addin.FiltersChanged() # restore original filters.
        manager.addin.ProcessMissedMessages()
        SetWaitCursor(0)

if __name__=='__main__':
    print "NOTE: This will NOT work from the command line"
    print "(it nearly will, and is useful for debugging the tests"
    print "themselves, so we will run them anyway!)"
    test()
