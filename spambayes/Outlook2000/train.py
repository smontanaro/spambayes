#! /usr/bin/env python
# Train a classifier from Outlook Mail folders
# Authors: Sean D. True, WebReply.Com, Mark Hammond
# October, 2002
# Copyright PSF, license under the PSF license

import sys
import traceback
from win32com.mapi import mapi

# Note our Message Database uses PR_SEARCH_KEY, *not* PR_ENTRYID, as the
# latter changes after a Move operation - see msgstore.py
def been_trained_as_ham(msg):
    if msg.t is None:
        return False
    return msg.t == False

def been_trained_as_spam(msg):
    if msg.t is None:
        return False
    return msg.t == True

def train_message(msg, is_spam, cdata):
    # Train an individual message.
    # Returns True if newly added (message will be correctly
    # untrained if it was in the wrong category), False if already
    # in the correct category.  Catch your own damn exceptions.
    # If re-classified AND rescore = True, then a new score will
    # be written to the message (so the user can see some effects)
    from spambayes.tokenizer import tokenize

    cdata.message_db.load_msg(msg)
    was_spam = msg.t
    if was_spam == is_spam:
        return False    # already correctly classified

    # Brand new (was_spam is None), or incorrectly classified.
    stream = msg.GetEmailPackageObject()
    if was_spam is not None:
        # The classification has changed; unlearn the old classification.
        cdata.bayes.unlearn(tokenize(stream), was_spam)

    # Learn the correct classification.
    cdata.bayes.learn(tokenize(stream), is_spam)
    msg.t = is_spam
    cdata.message_db.store_msg(msg)
    cdata.dirty = True
    return True

# Untrain a message.
# Return: None == not previously trained
#         True == was_spam
#         False == was_ham
def untrain_message(msg, cdata):
    from spambayes.tokenizer import tokenize
    stream = msg.GetEmailPackageObject()
    cdata.message_db.load_msg(msg)
    if been_trained_as_spam(msg):
        assert not been_trained_as_ham(msg), "Can't have been both!"
        cdata.bayes.unlearn(tokenize(stream), True)
        cdata.message_db.remove_msg(msg)
        cdata.dirty = True
        return True
    if been_trained_as_ham(msg):
        assert not been_trained_as_spam(msg), "Can't have been both!"
        cdata.bayes.unlearn(tokenize(stream), False)
        cdata.message_db.remove_msg(msg)
        cdata.dirty = True
        return False
    return None

def train_folder(f, isspam, cdata, progress):
    num = num_added = 0
    for message in f.GetMessageGenerator():
        if progress.stop_requested():
            break
        progress.tick()
        try:
            if train_message(message, isspam, cdata):
                num_added += 1
        except:
            print "Error training message '%s'" % (message,)
            traceback.print_exc()
        num += 1
    print "Checked", num, "in folder", f.name, "-", num_added, "new entries found."


def real_trainer(classifier_data, config, message_store, progress):
    progress.set_status(_("Counting messages"))

    num_msgs = 0
    for f in message_store.GetFolderGenerator(config.training.ham_folder_ids, config.training.ham_include_sub):
        num_msgs += f.count
    for f in message_store.GetFolderGenerator(config.training.spam_folder_ids, config.training.spam_include_sub):
        num_msgs += f.count

    progress.set_max_ticks(num_msgs+3)

    for f in message_store.GetFolderGenerator(config.training.ham_folder_ids, config.training.ham_include_sub):
        progress.set_status(_("Processing good folder '%s'") % (f.name,))
        train_folder(f, 0, classifier_data, progress)
        if progress.stop_requested():
            return

    for f in message_store.GetFolderGenerator(config.training.spam_folder_ids, config.training.spam_include_sub):
        progress.set_status(_("Processing spam folder '%s'") % (f.name,))
        train_folder(f, 1, classifier_data, progress)
        if progress.stop_requested():
            return

    progress.tick()
    if progress.stop_requested():
        return
    # Completed training - save the database
    # Setup the next "stage" in the progress dialog.
    progress.set_max_ticks(1)
    progress.set_status(_("Writing the database..."))
    classifier_data.Save()

# Called back from the dialog to do the actual training.
def trainer(mgr, config, progress):
    rebuild = config.training.rebuild
    rescore = config.training.rescore

    if not config.training.ham_folder_ids and not config.training.spam_folder_ids:
        progress.error(_("You must specify at least one spam or one good folder"))
        return

    if rebuild:
        # Make a new temporary bayes database to use for training.
        # If we complete, then the manager "adopts" it.
        # This prevents cancelled training from leaving a "bad" db, and
        # also prevents mail coming in during training from being classified
        # with the partial database.
        import os, manager
        bayes_base = os.path.join(mgr.data_directory, "$sbtemp$default_bayes_database")
        mdb_base = os.path.join(mgr.data_directory, "$sbtemp$default_message_database")
        # determine which db manager to use, and create it.
        ManagerClass = manager.GetStorageManagerClass()
        db_manager = ManagerClass(bayes_base, mdb_base)
        classifier_data = manager.ClassifierData(db_manager, mgr)
        classifier_data.InitNew()
    else:
        classifier_data = mgr.classifier_data

    # We do this in possibly 3 stages - train, filter, save
    # re-scoring is much slower than training (as we actually have to save
    # the message back.)
    # Saving is really slow sometimes, but we only have 1 tick for that anyway
    if rescore:
        stages = (_("Training"), .3), (_("Saving"), .1), (_("Scoring"), .6)
    else:
        stages = (_("Training"), .9), (_("Saving"), .1)
    progress.set_stages(stages)

    real_trainer(classifier_data, config, mgr.message_store, progress)

    if progress.stop_requested():
        return

    if rebuild:
        assert mgr.classifier_data is not classifier_data
        mgr.AdoptClassifierData(classifier_data)
        classifier_data = mgr.classifier_data
        # If we are rebuilding, then we reset the statistics, too.
        # (But output them to the log for reference).
        mgr.LogDebug(1, "Session:" + "\r\n".join(\
            mgr.stats.GetStats(session_only=True)))
        mgr.LogDebug(1, "Total:" + "\r\n".join(mgr.stats.GetStats()))
        mgr.stats.Reset()
        mgr.stats.ResetTotal(permanently=True)

    progress.tick()

    if rescore:
        # Setup the "filter now" config to what we want.
        config = mgr.config.filter_now
        config.only_unread = False
        config.only_unseen = False
        config.action_all = False
        config.folder_ids = mgr.config.training.ham_folder_ids + mgr.config.training.spam_folder_ids
        config.include_sub = mgr.config.training.ham_include_sub or mgr.config.training.spam_include_sub
        import filter
        filter.filterer(mgr, mgr.config, progress)

    bayes = classifier_data.bayes
    progress.set_status(_("Completed training with %d spam and %d good messages") % (bayes.nspam, bayes.nham))


def main():
    print "Sorry - we don't do anything here any more"

if __name__ == "__main__":
    main()
