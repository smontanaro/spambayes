# This module is part of the spambayes project, which is Copyright 2003
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

from processors import *
from opt_processors import *

from dialogs import ShowDialog

# "dialog specific" processors:
class VersionStringProcessor(ControlProcessor):
    def Init(self):
        from spambayes.Version import get_version_string
        import sys
        version_key = "Full Description"
        if hasattr(sys, "frozen"):
            version_key += " Binary"
        version_string = get_version_string("Outlook", version_key)
        win32gui.SendMessage(self.GetControl(), win32con.WM_SETTEXT,
                             0, version_string)

    def GetPopupHelpText(self, cid):
        return "The version of SpamBayes running"

class TrainingStatusProcessor(ControlProcessor):
    def Init(self):
        bayes = self.window.manager.bayes
        nspam = bayes.nspam
        nham = bayes.nham
        if nspam > 0 and nham > 0:
            db_status = "Database has %d good and %d spam" % (nham, nspam)
        else:
            db_status = "Database has no training information"
        win32gui.SendMessage(self.GetControl(), win32con.WM_SETTEXT,
                             0, db_status)

class FilterEnableProcessor(BoolButtonProcessor):
    def UpdateValue_FromControl(self):
        check = win32gui.SendMessage(self.GetControl(), win32con.BM_GETCHECK)
        if check:
            reason = self.window.manager.GetDisabledReason()
            if reason is not None:
                win32gui.SendMessage(self.GetControl(), win32con.BM_SETCHECK, 0)
                raise ValueError, reason
        check = not not check # force bool!
        self.SetOptionValue(check)
    
class FilterStatusProcessor(ControlProcessor):
    def OnOptionChanged(self, option):
        self.Init()

    def Init(self):
        manager = self.window.manager
        reason = manager.GetDisabledReason()
        if reason is not None:
            win32gui.SendMessage(self.GetControl(), win32con.WM_SETTEXT,
                                 0, reason)
            return
        if not manager.config.filter.enabled:
            status = "Filtering is disabled.  Select 'Enable Filtering' to enable"
            win32gui.SendMessage(self.GetControl(), win32con.WM_SETTEXT,
                                 0, status)
            return
        # ok, enabled and working - put together the status text.
        config = manager.config.filter
        certain_spam_name = manager.FormatFolderNames(
                                      [config.spam_folder_id], False)
        if config.unsure_folder_id:
            unsure_name = manager.FormatFolderNames(
                                    [config.unsure_folder_id], False)
            unsure_text = "unsure managed in '%s'" % (unsure_name,)
        else:
            unsure_text = "unsure messages untouched"
            
        watch_names = manager.FormatFolderNames(
                        config.watch_folder_ids, config.watch_include_sub)
        filter_status = "Watching '%s'. Spam managed in '%s', %s" \
                                % (watch_names,
                                   certain_spam_name,
                                   unsure_text)
        win32gui.SendMessage(self.GetControl(), win32con.WM_SETTEXT,
                             0, filter_status)
def ShowAbout(mgr):
    mgr.ShowHtml("about.html")

class DialogCommand(ButtonProcessor):
    def __init__(self, window, control_ids, idd):
        self.idd = idd
        ButtonProcessor.__init__(self, window, control_ids)
    def OnClicked(self, id):
        parent = self.window.hwnd
        # Thos form and the other form may "share" options, or at least
        # depend on others.  So we must save the current form back to the
        # options object, display the new dialog, then reload the current
        # form from the options object/
        self.window.SaveAllControls()
        ShowDialog(parent, self.window.manager, self.idd)
        self.window.LoadAllControls()
        
    def GetPopupHelpText(self, id):
        dd = self.window.manager.dialog_parser.dialogs[self.idd]
        return "Displays the %s dialog" % dd.caption

from async_processor import AsyncCommandProcessor
import filter, train

dialog_map = {
    "IDD_MANAGER" : (
        (CloseButtonProcessor,    "IDOK IDCANCEL"),
        (VersionStringProcessor,  "IDC_VERSION"),
        (TrainingStatusProcessor, "IDC_TRAINING_STATUS"),
        (FilterEnableProcessor,   "IDC_BUT_FILTER_ENABLE", "Filter.enabled"),
        (FilterStatusProcessor,   "IDC_FILTER_STATUS"),
        (BoolButtonProcessor,     "IDC_BUT_TRAIN_FROM_SPAM_FOLDER",
                                  "Training.train_recovered_spam"),
        (BoolButtonProcessor,     "IDC_BUT_TRAIN_TO_SPAM_FOLDER",
                                  "Training.train_manual_spam"),
        (DialogCommand,           "IDC_BUT_FILTER_NOW", "IDD_FILTER_NOW"),
        (DialogCommand,           "IDC_BUT_FILTER_DEFINE", "IDD_FILTER"),
        (DialogCommand,           "IDC_BUT_TRAIN_NOW", "IDD_TRAINING"),
        (CommandButtonProcessor,  "IDC_BUT_ABOUT", ShowAbout, ()),
    ),
    "IDD_FILTER_NOW" : (
        (CloseButtonProcessor,    "IDOK IDCANCEL"),
        (BoolButtonProcessor,     "IDC_BUT_UNREAD",    "Filter_Now.only_unread"),
        (BoolButtonProcessor,     "IDC_BUT_UNSEEN",    "Filter_Now.only_unseen"),
        (BoolButtonProcessor,     "IDC_BUT_ACT_ALL IDC_BUT_ACT_SCORE",
                                                       "Filter_Now.action_all"),
        (FolderIDProcessor,       "IDC_FOLDER_NAMES IDC_BROWSE",
                                  "Filter_Now.folder_ids",
                                  "Filter_Now.include_sub"),
        (AsyncCommandProcessor,   "IDC_START IDC_PROGRESS IDC_PROGRESS_TEXT",
                                  filter.filterer, "Start Filtering", "Stop Filtering",
                                  "IDC_BUT_UNSEEN IDC_BUT_UNREAD IDC_BROWSE " \
                                  "IDOK IDC_BUT_ACT_SCORE IDC_BUT_ACT_ALL"),
    ),
    "IDD_FILTER" : (
        (CloseButtonProcessor,    "IDOK IDCANCEL"),
        (FolderIDProcessor,       "IDC_FOLDER_WATCH IDC_BROWSE_WATCH",
                                  "Filter.watch_folder_ids",
                                  "Filter.watch_include_sub"),
        (ComboProcessor,          "IDC_ACTION_CERTAIN", "Filter.spam_action"),

        (FolderIDProcessor,       "IDC_FOLDER_CERTAIN IDC_BROWSE_CERTAIN",
                                  "Filter.spam_folder_id"),
        (EditNumberProcessor,     "IDC_EDIT_CERTAIN IDC_SLIDER_CERTAIN",
                                  "Filter.spam_threshold"),
        
        (FolderIDProcessor,       "IDC_FOLDER_UNSURE IDC_BROWSE_UNSURE",
                                  "Filter.unsure_folder_id"),
        (EditNumberProcessor,     "IDC_EDIT_UNSURE IDC_SLIDER_UNSURE",
                                  "Filter.unsure_threshold"),
        
        (ComboProcessor,          "IDC_ACTION_UNSURE", "Filter.unsure_action"),
        (DialogCommand,           "IDC_BUT_FILTER_NOW", "IDD_FILTER_NOW"),
    ),
    "IDD_TRAINING" : (
        (CloseButtonProcessor,    "IDOK IDCANCEL"),
        (FolderIDProcessor,       "IDC_STATIC_HAM IDC_BROWSE_HAM",
                                  "Training.ham_folder_ids",
                                  "Training.ham_include_sub"),
        (FolderIDProcessor,       "IDC_STATIC_SPAM IDC_BROWSE_SPAM",
                                  "Training.spam_folder_ids",
                                  "Training.spam_include_sub"),
        (BoolButtonProcessor,     "IDC_BUT_RESCORE",    "Training.rescore"),
        (BoolButtonProcessor,     "IDC_BUT_REBUILD",    "Training.rebuild"),
        (AsyncCommandProcessor,   "IDC_START IDC_PROGRESS IDC_PROGRESS_TEXT",
                                  train.trainer, "Start Training", "Stop",
                                  "IDC_BROWSE_HAM IDC_BROWSE_SPAM " \
                                  "IDC_BUT_REBUILD IDC_BUT_RESCORE"),
    )
}
