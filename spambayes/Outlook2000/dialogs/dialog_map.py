# This module is part of the spambayes project, which is Copyright 2003
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

from processors import *
from opt_processors import *

from dialogs import ShowDialog, MakePropertyPage

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

class IntProcessor(OptionControlProcessor):
    def UpdateControl_FromValue(self):
        win32gui.SendMessage(self.GetControl(), win32con.WM_SETTEXT, 0, str(self.option.get()))
    def UpdateValue_FromControl(self):
        buf_size = 100
        buf = win32gui.PyMakeBuffer(buf_size)
        nchars = win32gui.SendMessage(self.GetControl(), win32con.WM_GETTEXT,
                                      buf_size, buf)
        str_val = buf[:nchars]
        val = int(str_val)
        if val < 0 or val > 10:
            raise ValueError, "Value must be between 0 and 10"
        self.SetOptionValue(val)
    def OnCommand(self, wparam, lparam):
        code = win32api.HIWORD(wparam)
        if code==win32con.EN_CHANGE:
            try:
                self.UpdateValue_FromControl()
            except ValueError:
                # They are typing - value may be currently invalid
                pass

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

# This class will likely go away when the real options are made for
# delay timers
class MsSliderProcessor(EditNumberProcessor):
    def __init__(self, window, control_ids, option):
        EditNumberProcessor.__init__(self, window, control_ids, option)
    def InitSlider(self):
        slider = self.GetControl(self.slider_id)
        win32gui.SendMessage(slider, commctrl.TBM_SETRANGE, 0, MAKELONG(0, 10))
        win32gui.SendMessage(slider, commctrl.TBM_SETLINESIZE, 0, 1)
        win32gui.SendMessage(slider, commctrl.TBM_SETPAGESIZE, 0, 1)
        win32gui.SendMessage(slider, commctrl.TBM_SETTICFREQ, 1, 0)
        self.UpdateSlider_FromEdit()
    def OnMessage(self, msg, wparam, lparam):
        slider = self.GetControl(self.slider_id)
        if slider == lparam:
            slider_pos = win32gui.SendMessage(slider, commctrl.TBM_GETPOS, 0, 0)
            slider_pos = int(slider_pos)
            str_val = str(slider_pos)
            edit = self.GetControl()
            win32gui.SendMessage(edit, win32con.WM_SETTEXT, 0, str_val)
    def UpdateSlider_FromEdit(self):
        slider = self.GetControl(self.slider_id)
        try:
            # Get as float so we dont fail should the .0 be there, but
            # then convert to int as the slider only works with ints
            val = int(float(self.option.get()/1000))
        except ValueError:
            return
        win32gui.SendMessage(slider, commctrl.TBM_SETPOS, 1, val)

    def UpdateControl_FromValue(self):
        value = self.option.get()/1000
        win32gui.SendMessage(self.GetControl(), win32con.WM_SETTEXT, 0, str(value))
        self.UpdateSlider_FromEdit()
    def UpdateValue_FromControl(self):
        buf_size = 100
        buf = win32gui.PyMakeBuffer(buf_size)
        nchars = win32gui.SendMessage(self.GetControl(), win32con.WM_GETTEXT,
                                      buf_size, buf)
        str_val = buf[:nchars]
        val = int(str_val)
        if val < 0 or val > 10:
            raise ValueError, "Value must be between 0 and 10"
        self.SetOptionValue(val*1000)

    
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
class TabProcessor(ControlProcessor):
    def Init(self):
        self.pages = {}
        self.currentPage = None
        self.currentPageIndex = -1
        self.currentPageHwnd = None
        self.addPage(0, "IDD_GENERAL", "General")
        self.addPage(1, "IDD_TRAINING", "Training")
        self.addPage(2, "IDD_FILTER_SPAM", "Spam")
        self.addPage(3, "IDD_FILTER_UNSURE", "Possible Spam")
        self.addPage(4, "IDD_FILTER_NOW", "Filter Now")
        self.addPage(5, "IDD_ADVANCED", "Advanced")
        self.switchToPage(0)
    def OnNotify(self, nmhdr, wparam, lparam):
        # this does not appear to be in commctrl module
        selChangedCode =  5177342
        code = nmhdr[2]
        if code==selChangedCode:
            index = win32gui.SendMessage(self.GetControl(), commctrl.TCM_GETCURSEL, 0,0)
            if index!=self.currentPageIndex:
                self.switchToPage(index)

    def switchToPage(self, index):
        if self.currentPageHwnd is not None:
            if not self.currentPage.SaveAllControls():
                win32gui.SendMessage(self.GetControl(), commctrl.TCM_SETCURSEL, self.currentPageIndex,0)
                return 1
            win32gui.DestroyWindow(self.currentPageHwnd)
        self.currentPage = MakePropertyPage(self.GetControl(), self.window.manager, self.pages[index])
        self.currentPageHwnd = self.currentPage.CreateWindow()
        self.currentPageIndex = index
        return 0
        
    def addPage(self, item, idName, label):
        format = "iiiiiii"
        lbuf = win32gui.PyMakeBuffer(len(label)+1)
        address,l = win32gui.PyGetBufferAddressAndLen(lbuf)
        win32gui.PySetString(address, label)
        
        buf = struct.pack(format,
            commctrl.TCIF_TEXT, # mask
            0, # state
            0, # state mask
            address,
            0, #unused
            0, #image
            item
            )
        item = win32gui.SendMessage(self.GetControl(),
                             commctrl.TCM_INSERTITEM,
                             item,
                             buf)
        self.pages[item] = idName
        

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
        (ImageProcessor,          "IDC_LOGO_GRAPHIC"),
        (CloseButtonProcessor,    "IDOK IDCANCEL"),
        (TabProcessor,            "IDC_TAB"),
        (VersionStringProcessor,  "IDC_VERSION"),
        (CommandButtonProcessor,  "IDC_ABOUT_BTN", ShowAbout, ()),
    ),
    "IDD_GENERAL": (
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
        (DialogCommand,           "IDC_ADVANCED_BTN", "IDD_ADVANCED"),
        (BoolButtonProcessor,     "IDC_SAVE_SPAM_SCORE",    "Filter.save_spam_info"),
        ),
    "IDD_FILTER_NOW" : (
        (BoolButtonProcessor,     "IDC_BUT_UNREAD",    "Filter_Now.only_unread"),
        (BoolButtonProcessor,     "IDC_BUT_UNSEEN",    "Filter_Now.only_unseen"),
        (BoolButtonProcessor,     "IDC_BUT_ACT_ALL IDC_BUT_ACT_SCORE",
                                                       "Filter_Now.action_all"),
        (FolderIDProcessor,       "IDC_FOLDER_NAMES IDC_BROWSE",
                                  "Filter_Now.folder_ids",
                                  "Filter_Now.include_sub"),
        (AsyncCommandProcessor,   "IDC_START IDC_PROGRESS IDC_PROGRESS_TEXT",
                                  filter.filterer, "Start Filtering", "Stop Filtering",
                                  "IDOK IDCANCEL IDC_TAB IDC_BUT_UNSEEN IDC_BUT_UNREAD IDC_BROWSE " \
                                  "IDC_BUT_ACT_SCORE IDC_BUT_ACT_ALL"),
    ),
    "IDD_FILTER_SPAM" : (
        (FolderIDProcessor,       "IDC_FOLDER_WATCH IDC_BROWSE_WATCH",
                                  "Filter.watch_folder_ids",
                                  "Filter.watch_include_sub"),
        (ComboProcessor,          "IDC_ACTION_CERTAIN", "Filter.spam_action"),
        (FolderIDProcessor,       "IDC_FOLDER_CERTAIN IDC_BROWSE_CERTAIN",
                                  "Filter.spam_folder_id"),
        (EditNumberProcessor,     "IDC_EDIT_CERTAIN IDC_SLIDER_CERTAIN",
                                  "Filter.spam_threshold"),
        (BoolButtonProcessor,     "IDC_MARK_SPAM_AS_READ",    "Filter.spam_mark_as_read"),
        ),
    "IDD_FILTER_UNSURE" : (
        (FolderIDProcessor,       "IDC_FOLDER_UNSURE IDC_BROWSE_UNSURE",
                                  "Filter.unsure_folder_id"),
        (EditNumberProcessor,     "IDC_EDIT_UNSURE IDC_SLIDER_UNSURE",
                                  "Filter.unsure_threshold"),
        
        (ComboProcessor,          "IDC_ACTION_UNSURE", "Filter.unsure_action"),
        (BoolButtonProcessor,     "IDC_MARK_UNSURE_AS_READ",    "Filter.unsure_mark_as_read"),
        ),
    "IDD_TRAINING" : (
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
                                  "IDOK IDCANCEL IDC_TAB IDC_BROWSE_HAM IDC_BROWSE_SPAM " \
                                  "IDC_BUT_REBUILD IDC_BUT_RESCORE"),
    ),
    "IDD_ADVANCED" : (
        (IntProcessor,   "IDC_VERBOSE_LOG",  "General.verbose"),
        (MsSliderProcessor,   "IDC_DELAY1_TEXT IDC_DELAY1_SLIDER", "Experimental.timer_start_delay"),
        (MsSliderProcessor,   "IDC_DELAY2_TEXT IDC_DELAY2_SLIDER", "Experimental.timer_interval"),
        (BoolButtonProcessor,   "IDC_INBOX_TIMER_ONLY", "Experimental.timer_only_receive_folders"),
        (ComboProcessor,          "IDC_DEL_SPAM_RS", "General.delete_as_spam_message_state"),
        (ComboProcessor,          "IDC_RECOVER_RS", "General.recover_from_spam_message_state"),
        )
}