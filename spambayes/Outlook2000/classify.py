# Classify a folder with a field
# Authors: Sean D. True, WebReply.Com, Mark Hammond.
# October, 2002
# Copyright PSF, license under the PSF license

import sys, os, traceback
from win32com.client import Dispatch, constants
import pythoncom
import win32con

def classify_folder( f, mgr, config, progress):
    for message in f.GetMessageGenerator():
        if progress.stop_requested():
            break
        progress.tick()
        try:
            prob = mgr.score(message)
            message.SetField(config.field_name, prob)
            message.Save()
        except:
            print "Error classifying message '%s'" % (message,)
            traceback.print_exc()

# Called back from the dialog to do the actual training.
def classifier(mgr, progress):
    config = mgr.config.classify
    if not config.folder_ids:
        progress.error("You must specify at least one folder")
        return
    progress.set_status("Counting messages")
    num_msgs = 0
    for f in mgr.message_store.GetFolderGenerator(config.folder_ids, config.include_sub):
        num_msgs += f.count
    progress.set_max_ticks(num_msgs+3)

    for f in mgr.message_store.GetFolderGenerator(config.folder_ids, config.include_sub):
        progress.set_status("Processing folder '%s'" % (f.name,))
        classify_folder(f, mgr, config, progress)
        if progress.stop_requested():
            return
    progress.set_status("Classified %d messages." % (num_msgs,))


def main():
    import manager
    mgr = manager.GetManager()

    import dialogs.ClassifyDialog
    d = dialogs.ClassifyDialog.ClassifyDialog(mgr, classifier)
    d.DoModal()
    mgr.Save()
    mgr.Close()

if __name__ == "__main__":
    main()
