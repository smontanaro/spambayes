# Train a classifier from Outlook Mail folders
# Author: Sean D. True, WebReply.Com
# October, 2002
# Copyright PSF, license under the PSF license

import sys, os, os.path, getopt, cPickle, string
import win32com.client
import pythoncom
import win32con

import classifier
from tokenizer import tokenize

def train_folder( f, isspam, mgr, progress):
    for message in mgr.YieldMessageList(f):
        if progress.stop_requested():
            break
        progress.tick()
        try:
            # work with MAPI until we work out how to get headers from outlook
            message = mgr.mapi.GetMessage(message.ID)
            headers = message.Fields[0x7D001E].Value
            headers = headers.encode('ascii', 'replace')
            body = message.Text.encode('ascii', 'replace')
        except pythoncom.com_error:
            progress.warning("failed to get a message")
            continue
        text = headers + body
        mgr.bayes.learn(tokenize(text), isspam, False)

# Called back from the dialog to do the actual training.
def trainer(mgr, progress):
    pythoncom.CoInitialize()
    config = mgr.config
    mgr.InitNewBayes()
    bayes = mgr.bayes
    session = mgr.mapi

    if not config.training.ham_folder_ids or not config.training.spam_folder_ids:
        progress.error("You must specify at least one spam, and one good folder")
        return
    progress.set_status("Counting messages")
    ham_folders = mgr.BuildFolderList(config.training.ham_folder_ids, config.training.ham_include_sub)
    spam_folders = mgr.BuildFolderList(config.training.spam_folder_ids, config.training.ham_include_sub)
    num_msgs = 0
    for f in ham_folders + spam_folders:
        num_msgs += f.Messages.Count + 1
    progress.set_max_ticks(num_msgs+3)

    for f in ham_folders:
        progress.set_status("Processing good folder '%s'" % (f.Name.encode("ascii", "replace"),))
        train_folder(f, 0, mgr, progress)
        if progress.stop_requested():
            return

    for f in spam_folders:
        progress.set_status("Processing spam folder '%s'" % (f.Name.encode("ascii", "replace"),))
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
