# Filter, dump messages to and from Outlook Mail folders
# Author: Sean D. True, WebReply.Com
# October, 2002
# Copyright PSF, license under the PSF license

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


def filter_message(msg, mgr, all_actions=True):
    config = mgr.config.filter
    prob = mgr.score(msg)
    prob_perc = prob * 100
    if prob_perc >= config.spam_threshold:
        disposition = "Yes"
        attr_prefix = "spam"
    elif prob_perc >= config.unsure_threshold:
        disposition = "Unsure"
        attr_prefix = "unsure"
    else:
        disposition = "No"
        attr_prefix = None

    try:
        # Save the score
        msg.SetField(mgr.config.field_score_name, prob)
        # and the ID of the folder we were in when scored.
        # (but only if we want to perform all actions)
        # Note we must do this, and the Save, before the
        # filter, else the save will fail.
        if all_actions:
            msg.RememberMessageCurrentFolder()
        msg.Save()

        if all_actions and attr_prefix is not None:
            folder_id = getattr(config, attr_prefix + "_folder_id")
            action = getattr(config, attr_prefix + "_action").lower()
            if action.startswith("un"): # untouched
                pass
            elif action.startswith("co"): # copied
                dest_folder = mgr.message_store.GetFolder(folder_id)
                if dest_folder is None:
                    print "ERROR: Unable to open the folder to Copy the " \
                          "message - this message was not copied"
                else:
                    msg.CopyTo(dest_folder)
            elif action.startswith("mo"): # Moved
                dest_folder = mgr.message_store.GetFolder(folder_id)
                if dest_folder is None:
                    print "ERROR: Unable to open the folder to Move the " \
                          "message - this message was not moved"
                else:
                    msg.MoveTo(dest_folder)
            else:
                raise RuntimeError, "Eeek - bad action '%r'" % (action,)

        return disposition
    except:
        print "Failed filtering message!", msg
        import traceback
        traceback.print_exc()
        return "Failed"

def filter_folder(f, mgr, progress):
    config = mgr.config.filter_now
    only_unread = config.only_unread
    only_unseen = config.only_unseen
    all_actions = config.action_all
    dispositions = {}
    for message in f.GetMessageGenerator():
        if progress.stop_requested():
            break
        progress.tick()
        if only_unread and not message.unread or \
           only_unseen and message.GetField(mgr.config.field_score_name) is not None:
            continue
        disposition = filter_message(message, mgr, all_actions)
        dispositions[disposition] = dispositions.get(disposition, 0) + 1

    return dispositions

# Called for "filter now"
def filterer(mgr, progress):
    config = mgr.config.filter_now
    if not config.folder_ids:
        progress.error("You must specify at least one folder")
        return

    progress.set_status("Counting messages")
    num_msgs = 0
    for f in mgr.message_store.GetFolderGenerator(config.folder_ids, config.include_sub):
        num_msgs += f.count
    progress.set_max_ticks(num_msgs+3)
    dispositions = {}
    for f in mgr.message_store.GetFolderGenerator(config.folder_ids, config.include_sub):
        progress.set_status("Filtering folder '%s'" % (f.name))
        this_dispositions = filter_folder(f, mgr, progress)
        dispositions.update(this_dispositions)
        if progress.stop_requested():
            return
    # All done - report what we did.
    err_text = ""
    if dispositions.has_key("Error"):
        err_text = " (%d errors)" % dispositions["Error"]
    dget = dispositions.get
    text = "Found %d spam, %d unsure and %d good messages%s" % \
                (dget("Yes",0), dget("Unsure",0), dget("No",0), err_text)
    progress.set_status(text)

def main():
    import manager
    mgr = manager.GetManager()

    import dialogs.FilterDialog
    d = dialogs.FilterDialog.FilterArrivalsDialog(mgr, filterer)
    d.DoModal()
    mgr.Save()
    mgr.Close()

if __name__ == "__main__":
    main()
