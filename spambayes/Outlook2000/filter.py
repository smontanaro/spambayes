# Filter, dump messages to and from Outlook Mail folders
# Author: Sean D. True, WebReply.Com
# October, 2002
# Copyright PSF, license under the PSF license

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

import pythoncom # for the exceptions.

def filter_message(msg, mgr, all_actions=True):
    config = mgr.config.filter
    prob = mgr.score(msg)
    mgr.stats.num_seen += 1
    prob_perc = prob * 100
    if prob_perc >= config.spam_threshold:
        disposition = "Yes"
        attr_prefix = "spam"
        mgr.stats.num_spam += 1
    elif prob_perc >= config.unsure_threshold:
        disposition = "Unsure"
        attr_prefix = "unsure"
        mgr.stats.num_unsure += 1
    else:
        disposition = "No"
        attr_prefix = None

    try:
        try:
            if config.save_spam_info:
                # Save the score
                # Catch this exception, as failing to save the score need not
                # be fatal - it may still be possible to perform the move.
                msg.SetField(mgr.config.general.field_score_name, prob)
                # and the ID of the folder we were in when scored.
                # (but only if we want to perform all actions)
                # Note we must do this, and the Save, before the
                # filter, else the save will fail.
                if all_actions:
                    msg.RememberMessageCurrentFolder()
                msg.Save()
        except pythoncom.com_error, (hr, exc_msg, exc, arg_err):
            # This seems to happen for IMAP mails (0x800cccd3)
            # and also for hotmail messages (0x8004dff7)
            known_failure_codes = -2146644781, -2147164169
            # I also heard a rumour hotmail works if we do 2 saves
            if hr not in known_failure_codes:
                print "Unexpected MAPI error saving the spam score for", msg
                print hr, exc_msg, exc
            else:
                # So we can see if it still happens :)
                mgr.LogDebug(1, "Note: known (but still not understood) " \
                                "error 0x%x saving the spam score." % hr)
            # No need for a traceback in this case.
            # Clear dirty flag anyway
            msg.dirty = False

        if all_actions and attr_prefix is not None:
            folder_id = getattr(config, attr_prefix + "_folder_id")
            action = getattr(config, attr_prefix + "_action").lower()
            mark_as_read = getattr(config, attr_prefix + "_mark_as_read")
            if mark_as_read:
                msg.SetReadState(True)
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
        # Have seen MAPI_E_TABLE_TOO_BIG errors reported here when doing the
        # move, but in what is probably a semi-corrupt pst.
        # However, this *is* a legitimate error to get if the target folder
        # has > 16,383 entries.
        print "Failed filtering message!", msg
        import traceback
        traceback.print_exc()
        return "Failed"

def filter_folder(f, mgr, config, progress):
    only_unread = config.only_unread
    only_unseen = config.only_unseen
    all_actions = config.action_all
    dispositions = {}
    field_name = mgr.config.general.field_score_name
    for message in f.GetMessageGenerator():
        if progress.stop_requested():
            break
        progress.tick()
        if only_unread and message.GetReadState() or \
           only_unseen and message.GetField(field_name) is not None:
            continue
        try:
            disposition = filter_message(message, mgr, all_actions)
        except:
            import traceback
            print "Error filtering message '%s'" % (message,)
            traceback.print_exc()
            disposition = "Error"

        dispositions[disposition] = dispositions.get(disposition, 0) + 1

    return dispositions

# Called for "filter now"
def filterer(mgr, config, progress):
    config = config.filter_now
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
        this_dispositions = filter_folder(f, mgr, config, progress)
        for key, val in this_dispositions.items():
            dispositions[key] = dispositions.get(key, 0) + val
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
