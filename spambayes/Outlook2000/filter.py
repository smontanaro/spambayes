# Filter, dump messages to and from Outlook Mail folders
# Author: Sean D. True, WebReply.Com
# October, 2002
# Copyright PSF, license under the PSF license

def filter_message(msg, mgr, all_actions = True):
    config = mgr.config.filter
    prob = mgr.score(msg)
    if prob >= config.spam_threshold:
        disposition = "Yes"
        attr_prefix = "spam"
    elif prob >= config.unsure_threshold:
        disposition = "Unsure"
        attr_prefix = "unsure"
    else:
        disposition = "No"
        attr_prefix = None

    try:
        msg.SetField(mgr.config.field_score_name, prob)
        msg.Save()

        if all_actions and attr_prefix is not None:
            folder_id = getattr(config, attr_prefix + "_folder_id")
            action = getattr(config, attr_prefix + "_action").lower()
            if action.startswith("no"):
                pass
            elif action.startswith("co"):
                dest_folder = mgr.message_store.GetFolder(folder_id)
                msg.CopyTo(dest_folder)
            elif action.startswith("mo"):
                dest_folder = mgr.message_store.GetFolder(folder_id)
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
