# Train a classifier from Outlook Mail folders
# Authors: Sean D. True, WebReply.Com, Mark Hammond
# October, 2002
# Copyright PSF, license under the PSF license

import sys, os, traceback

def train_folder( f, isspam, mgr, progress):
    from tokenizer import tokenize
    num = 0
    for message in f.GetMessageGenerator():
        if progress.stop_requested():
            break
        progress.tick()
        try:
            stream = message.GetEmailPackageObject()
            mgr.bayes.learn(tokenize(stream), isspam, False)
        except:
            print "Error training message '%s'" % (message,)
            traceback.print_exc()
        num += 1
    print "Trained over", num, "in folder", f.name

# Called back from the dialog to do the actual training.
def trainer(mgr, progress):
    config = mgr.config
    mgr.InitNewBayes()
    bayes = mgr.bayes

    if not config.training.ham_folder_ids or not config.training.spam_folder_ids:
        progress.error("You must specify at least one spam, and one good folder")
        return
    progress.set_status("Counting messages")

    num_msgs = 0
    for f in mgr.message_store.GetFolderGenerator(config.training.ham_folder_ids, config.training.ham_include_sub):
        num_msgs += f.count
    for f in mgr.message_store.GetFolderGenerator(config.training.spam_folder_ids, config.training.spam_include_sub):
        num_msgs += f.count

    progress.set_max_ticks(num_msgs+3)

    for f in mgr.message_store.GetFolderGenerator(config.training.ham_folder_ids, config.training.ham_include_sub):
        progress.set_status("Processing good folder '%s'" % (f.name,))
        train_folder(f, 0, mgr, progress)
        if progress.stop_requested():
            return

    for f in mgr.message_store.GetFolderGenerator(config.training.spam_folder_ids, config.training.spam_include_sub):
        progress.set_status("Processing spam folder '%s'" % (f.name,))
        train_folder(f, 1, mgr, progress)
        if progress.stop_requested():
            return

    progress.tick()
    progress.set_status('Updating probabilities...')
    bayes.update_probabilities()
    progress.tick()
    if progress.stop_requested():
        return
    mgr.bayes_dirty = True
    progress.set_status("Completed training with %d spam and %d good messages" % (bayes.nspam, bayes.nham))

def main():
    import manager
    mgr = manager.GetManager()

    import dialogs.TrainingDialog
    d = dialogs.TrainingDialog.TrainingDialog(mgr, trainer)
    d.DoModal()

    mgr.Save()
    mgr.Close()

if __name__ == "__main__":
    main()
