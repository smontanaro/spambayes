# Train a classifier from Outlook Mail folders
# Author: Sean D. True, WebReply.Com
# October, 2002
# Copyright PSF, license under the PSF license

import sys, os, os.path, getopt, cPickle, string
from win32com.client import Dispatch, constants
import pythoncom
import win32con

def classify_folder( f, mgr, config, progress):
    hammie = mgr.MakeHammie()
    messages = f.Messages
    pythoncom.CoInitialize() # We are called on a different thread.
    # We must get outlook in this thread - can't use the main thread :(
    outlook_ns = mgr.GetOutlookForCurrentThread().GetNamespace("MAPI")

    if not messages:
        progress.warning("Can't find messages in folder '%s'" % (f.Name,))
        return
    message = messages.GetFirst()
    while not progress.stop_requested() and message:
        try:
            progress.tick()
            headers = message.Fields[0x7D001E].Value
            headers = headers.encode('ascii', 'replace')
            body = message.Text.encode('ascii', 'replace')
            text = headers + body
            prob = hammie.score(text, evidence=False)
            added_prop = False
            try:
                if outlook_ns is not None:
                    outlookItem = outlook_ns.GetItemFromID(message.ID)
                    format = 4 # 4=2 decimal, 3=1 decimal - index in "field chooser" combo when type=Number.
                    prop = outlookItem.UserProperties.Add(config.field_name, constants.olNumber, True, format)
                    prop.Value = prob
                    outlookItem.Save()
                    added_prop = True
            except "foo": # pythoncom.com_error, d:
                # Hrm - don't seem able to use outlook - use MAPI - but this
                # means the field doesn't automatically appear in the outlook "Field Chooser"
                # Tried explicity adding the field to the folder but still no go.
                added_prop = False
            if not  added_prop:
                message.Fields.Add(config.field_name, 5, prob)

            message.Update()
        except pythoncom.com_error, d:
            progress.warning("Failed to get a message: %s" % (str(d),) )
        message = messages.GetNext()

# Called back from the dialog to do the actual training.
def classifier(mgr, progress):
    session = mgr.mapi
    config = mgr.config.classify
    if not config.folder_ids:
        progress.error("You must specify at least one folder")
        return
    progress.set_status("Counting messages")
    folders = mgr.BuildFolderList(config.folder_ids, config.include_sub)
    num_msgs = 0
    for f in folders:
        num_msgs += f.Messages.Count + 1
    progress.set_max_ticks(num_msgs+3)

    for f in folders:
        progress.set_status("Processing folder '%s'" % (f.Name.encode("ascii", "replace"),))
        classify_folder(f, mgr, config, progress)
        if progress.stop_requested():
            return


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
