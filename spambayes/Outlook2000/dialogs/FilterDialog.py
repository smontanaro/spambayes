from __future__ import generators

from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api
import pythoncom
from win32com.client import constants

from DialogGlobals import *

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


IDC_FOLDER_WATCH = 1024
IDC_BROWSE_WATCH = 1025
IDC_SLIDER_CERTAIN = 1026
IDC_EDIT_CERTAIN = 1027
IDC_ACTION_CERTAIN = 1028
IDC_FOLDER_CERTAIN = 1029
IDC_BROWSE_CERTAIN = 1030
IDC_SLIDER_UNSURE = 1031
IDC_EDIT_UNSURE = 1032
IDC_ACTION_UNSURE = 1033
IDC_FOLDER_UNSURE = 1034
IDC_BROWSE_UNSURE = 1035
IDC_TOFOLDER_CERTAIN = 1036
IDC_TOFOLDER_UNDURE = 1037
IDC_BUT_FILTERNOW=1038

class FilterArrivalsDialog(dialog.Dialog):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    csts = cs | win32con.WS_TABSTOP
    treestyle = csts | win32con.WS_BORDER | commctrl.TVS_CHECKBOXES | commctrl.TVS_DISABLEDRAGDROP | commctrl.TVS_SHOWSELALWAYS
    filter_msg = "Filter the following folders as messages arrive"
    certain_spam_msg = "To be considered certain spam, a message must score at least"
    unsure_msg = "To be considered uncertain, a message must score at least"
    good_msg = "All other messages are considered good, and are not filtered."
    dt = [
        # Dialog itself.
        ["Filter Rules", (0, 0, 249, 239), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          filter_msg,           -1,                  (8,9,168,11),     cs],
        [STATIC,          "",                   IDC_FOLDER_WATCH,    (7,20,177,12),    cs   | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],
        [BUTTON,          '&Browse',            IDC_BROWSE_WATCH,    (192,19,50,14),   csts | win32con.BS_PUSHBUTTON],

        [BUTTON,          "Certain Spam",       -1,                  (7,43,235,65),    cs   | win32con.BS_GROUPBOX],
        [STATIC,          certain_spam_msg,     -1,                  (13,52,212,10),   cs],
        ["msctls_trackbar32", "",               IDC_SLIDER_CERTAIN,  (13,62,165,12),   cs   | commctrl.TBS_BOTH | commctrl.TBS_AUTOTICKS ],
        [EDIT,            "",                   IDC_EDIT_CERTAIN,    (184,63,51,14),   csts | win32con.ES_AUTOHSCROLL | win32con.WS_BORDER],
        [STATIC,          "and these messages should be", -1,        (13,76,107,10),   cs],
        [COMBOBOX,        "",                   IDC_ACTION_CERTAIN,  (13,88,55,40),    csts | win32con.CBS_DROPDOWNLIST | win32con.WS_VSCROLL],
        [STATIC,          "to folder",          IDC_TOFOLDER_CERTAIN,(75,90,31,10),    cs],
        [STATIC,          "",                   IDC_FOLDER_CERTAIN,  (120,88,59,14),   cs   | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],
        [BUTTON,          '&Browse',            IDC_BROWSE_CERTAIN,  (184,88,50,14),   csts | win32con.BS_PUSHBUTTON],

        [BUTTON,          "Possible Spam",      -1,                  (7,114,235,68),   cs   | win32con.BS_GROUPBOX],
        [STATIC,          unsure_msg,           -1,                  (13,124,212,10),  cs],
        ["msctls_trackbar32", "",               IDC_SLIDER_UNSURE,   (13,137,165,12),  cs   | commctrl.TBS_BOTH | commctrl.TBS_AUTOTICKS],
        [EDIT,            "",                   IDC_EDIT_UNSURE,     (184,137,54,14),  csts | win32con.ES_AUTOHSCROLL | win32con.WS_BORDER],
        [STATIC,          "and these messages should be", -1,        (13,150,107,10),  cs],
        [COMBOBOX,        "",                   IDC_ACTION_UNSURE,   (13,161,55,40),   csts | win32con.CBS_DROPDOWNLIST | win32con.WS_VSCROLL],
        [STATIC,          "to folder",          IDC_TOFOLDER_UNDURE, (75,164,31,10),   cs],
        [STATIC,          "",                   IDC_FOLDER_UNSURE,   (120,161,59,14),  cs   | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],
        [BUTTON,          '&Browse',            IDC_BROWSE_UNSURE,   (184,161,50,14),  csts | win32con.BS_PUSHBUTTON],

        [BUTTON,          "Good messages",      -1,                  (7,185,235,25),   cs   | win32con.BS_GROUPBOX],
        [STATIC,          good_msg,             -1,                  (14,196,212,10),  cs],

        [BUTTON,         'Filter Now...',       IDC_BUT_FILTERNOW,   (7,218,50,14),    csts | win32con.BS_PUSHBUTTON],
        [BUTTON,         'OK',                  win32con.IDOK,       (134,218,50,14),  csts | win32con.BS_DEFPUSHBUTTON],
        [BUTTON,         'Cancel',              win32con.IDCANCEL,   (192,218,50,14),  csts | win32con.BS_PUSHBUTTON],
    ]

    def __init__(self, mgr, filterer):
        self.mgr = mgr
        self.filterer = filterer
        self.watch_folder_ids = mgr.config.filter.watch_folder_ids
        self.watch_include_sub = mgr.config.filter.watch_include_sub
        # If we have no watch folder, suggest the Inbox.
        if len(self.watch_folder_ids)==0 and mgr.outlook is not None:
            inbox = self.mgr.outlook.Session.GetDefaultFolder(constants.olFolderInbox)
            self.watch_folder_ids = [(inbox.StoreID, inbox.EntryID)]

        self.spam_folder_id = mgr.config.filter.spam_folder_id
        self.unsure_folder_id = mgr.config.filter.unsure_folder_id
        dialog.Dialog.__init__(self, self.dt)

    def OnInitDialog(self):
        self.SetDlgItemText(IDC_EDIT_CERTAIN, "%d" % self.mgr.config.filter.spam_threshold)
        self.HookCommand(self.OnEditChange, IDC_EDIT_CERTAIN)
        self.SetDlgItemText(IDC_EDIT_UNSURE, "%d" % self.mgr.config.filter.unsure_threshold)
        self.HookCommand(self.OnEditChange, IDC_EDIT_UNSURE)

        self.HookCommand(self.OnButBrowse, IDC_BROWSE_WATCH)
        self.HookCommand(self.OnButBrowse, IDC_BROWSE_CERTAIN)
        self.HookCommand(self.OnButBrowse, IDC_BROWSE_UNSURE)

        self.HookCommand(self.OnButFilterNow, IDC_BUT_FILTERNOW)

        self._InitSlider(IDC_SLIDER_CERTAIN, IDC_EDIT_CERTAIN)
        self._InitSlider(IDC_SLIDER_UNSURE, IDC_EDIT_UNSURE)
        self.HookMessage(self.OnSlider, win32con.WM_HSCROLL)

        for idc, attr in [ (IDC_ACTION_CERTAIN, "spam_action"), (IDC_ACTION_UNSURE, "unsure_action")]:
            index = sel_index = 0
            combo = self.GetDlgItem(idc)
            for s in ["Untouched", "Moved", "Copied"]:
                combo.AddString(s)
                if getattr(self.mgr.config.filter, attr).startswith(s):
                    sel_index = index
                index += 1
            combo.SetCurSel(sel_index)
        self.HookCommand(self.OnComboSelChange, IDC_ACTION_CERTAIN)
        self.OnComboSelChange(IDC_ACTION_CERTAIN, win32con.LBN_SELCHANGE)
        self.HookCommand(self.OnComboSelChange, IDC_ACTION_UNSURE)
        self.OnComboSelChange(IDC_ACTION_UNSURE, win32con.LBN_SELCHANGE)

        self.UpdateFolderNames()
        return dialog.Dialog.OnInitDialog(self)

    def OnDestroy(self,msg):
        self.mgr = None
        self.filterer = None
        dialog.Dialog.OnDestroy(self, msg)

    def UpdateFolderNames(self):
        self._DoUpdateFolderNames(self.watch_folder_ids, self.watch_include_sub, IDC_FOLDER_WATCH)
        if self.spam_folder_id is not None:
            self._DoUpdateFolderNames([self.spam_folder_id], False, IDC_FOLDER_CERTAIN)
        if self.unsure_folder_id is not None:
            self._DoUpdateFolderNames([self.unsure_folder_id], False, IDC_FOLDER_UNSURE)

    def OnOK(self):
        if not self._CheckEdits():
            return True
        config = self.mgr.config.filter
        combo_certain = self.GetDlgItem(IDC_ACTION_CERTAIN)
        combo_unsure = self.GetDlgItem(IDC_ACTION_UNSURE)
        if combo_certain.GetCurSel()!=0 and not self.spam_folder_id or \
           combo_certain.GetCurSel()!=0 and not self.spam_folder_id:
            self.MessageBox("You must enter a destination folder")
            return True
        config.spam_action = combo_certain.GetLBText(combo_certain.GetCurSel())
        config.unsure_action = combo_unsure.GetLBText(combo_unsure.GetCurSel())

        self.mgr.config.filter.watch_folder_ids = self.watch_folder_ids
        self.mgr.config.filter.spam_folder_id = self.spam_folder_id
        self.mgr.config.filter.unsure_folder_id = self.unsure_folder_id
        return self._obj_.OnOK()

    def _DoUpdateFolderNames(self, folder_ids, include_sub, idc):
        self.SetDlgItemText(idc, self.mgr.FormatFolderNames(folder_ids, include_sub))

    def OnEditChange(self, controlid, code):
        if code==win32con.EN_CHANGE:
            if controlid == IDC_EDIT_CERTAIN:
                sliderid = IDC_SLIDER_CERTAIN
            else:
                sliderid = IDC_SLIDER_UNSURE
            self._AdjustSliderToEdit(sliderid, controlid)
        return 1 # I handled this, so no need to call defaults!

    def OnComboSelChange(self, id, code):
        if code == win32con.LBN_SELCHANGE:
            if id == IDC_ACTION_CERTAIN:
                controls = [IDC_FOLDER_CERTAIN, IDC_BROWSE_CERTAIN, IDC_TOFOLDER_CERTAIN]
            else:
                controls = [IDC_FOLDER_UNSURE, IDC_BROWSE_UNSURE, IDC_TOFOLDER_UNDURE]
            cb = self.GetDlgItem(id)
            enabled = cb.GetCurSel() != 0
            for control in controls:
                self.GetDlgItem(control).EnableWindow(enabled)

    def OnButFilterNow(self, id, code):
        if code == win32con.BN_CLICKED:
            d = FilterNowDialog(self.mgr, self.filterer)
            d.DoModal()

    def OnButBrowse(self, id, code):
        if code == win32con.BN_CLICKED:
            ids_are_list = False
            if id == IDC_BROWSE_CERTAIN:
                attr_ids = "spam_folder_id"
            elif id == IDC_BROWSE_UNSURE:
                attr_ids = "unsure_folder_id"
            elif id == IDC_BROWSE_WATCH:
                attr_ids = "watch_folder_ids"
                ids_are_list = True
            else:
                raise RuntimeError, "Dont know about this button!"
            import FolderSelector
            ids = getattr(self, attr_ids)
            if not ids_are_list:
                ids = [ids]
            single_select = not ids_are_list
            d = FolderSelector.FolderSelector(self.mgr, ids, checkbox_state=None, single_select=single_select)
            if d.DoModal()==win32con.IDOK:
                new_ids, include_sub = d.GetSelectedIDs()
                if not ids_are_list:
                    new_ids = new_ids[0]
                setattr(self, attr_ids, new_ids)
                self.UpdateFolderNames()

    def OnSlider(self, params):
        lParam = params[3]
        slider = self.GetDlgItem(IDC_SLIDER_CERTAIN)
        if slider.GetSafeHwnd() == lParam:
            idc_edit = IDC_EDIT_CERTAIN
        else:
            slider = self.GetDlgItem(IDC_SLIDER_UNSURE)
            assert slider.GetSafeHwnd() == lParam
            idc_edit = IDC_EDIT_UNSURE
        slider_pos = slider.GetPos()
        self.SetDlgItemText(idc_edit, "%d" % slider_pos)

    def _InitSlider(self, idc_slider, idc_edit):
        slider = self.GetDlgItem(idc_slider)
        slider.SetRange(0, 100, 0)
        slider.SetLineSize(1)
        slider.SetPageSize(5)
        slider.SetTicFreq(10)
        self._AdjustSliderToEdit(idc_slider, idc_edit)

    def _AdjustSliderToEdit(self, idc_slider, idc_edit):
        slider = self.GetDlgItem(idc_slider)
        edit = self.GetDlgItem(idc_edit)
        try:
            val = int(edit.GetWindowText())
        except ValueError:
            return
        slider.SetPos(val)

    def _CheckEdits(self):
        try:
            idc_error = IDC_EDIT_CERTAIN
            val_certain = float(self.GetDlgItemText(IDC_EDIT_CERTAIN))
            if val_certain < 0 or val_certain > 100:
                raise ValueError
            idc_error = IDC_EDIT_UNSURE
            val_unsure = float(self.GetDlgItemText(IDC_EDIT_UNSURE))
            if val_unsure < 0 or val_unsure > 100:
                raise ValueError
        except ValueError:
            self.MessageBox("Please enter a number between 0 and 100")
            self.GetDlgItem(idc_error).SetFocus()
            return False
        if val_unsure > val_certain:
            self.MessageBox("The unsure value must not be greater than the certain value")
            self.SetDlgItemText(IDC_EDIT_UNSURE, str(val_certain))
            self.GetDlgItem(IDC_EDIT_UNSURE).SetFocus()

        self.mgr.config.filter.spam_threshold = val_certain
        self.mgr.config.filter.unsure_threshold = val_unsure
        return True

from AsyncDialog import *
IDC_FOLDER_NAMES=1024
IDC_BROWSE=1025
IDC_BUT_UNREAD=1027
IDC_BUT_UNSEEN=1028
IDC_BUT_ACT_ALL = 1029
IDC_BUT_ACT_SCORE = 1030

class FilterNowDialog(AsyncDialogBase):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    csts = cs | win32con.WS_TABSTOP
    only_group = "Restrict the filter to"
    only_unread = "Unread mail"
    only_unseen = "Mail never previously spam filtered"

    action_all = "Perform all filter actions"
    action_score = "Score messages, but don't perform filter action"
    process_start_text = "&Start filtering"
    process_stop_text = "&Stop filtering"
    dt = [
        # Dialog itself.
        ["Filter Now", (0, 0, 244, 182), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          "Filter the following folders", -1,        (8,9,168,11),   cs],
        [STATIC,          "",                   IDC_FOLDER_NAMES,    (7,20,172,12),  cs   | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],
        [BUTTON,          '&Browse',            IDC_BROWSE,          (187,19,50,14), csts | win32con.BS_PUSHBUTTON],

        [BUTTON,          "Filter Action",      -1,                  (7,38,230,40),  cs   | win32con.BS_GROUPBOX | win32con.WS_GROUP],
        [BUTTON,          action_all,           IDC_BUT_ACT_ALL,     (15,49,126,10), csts | win32con.BS_AUTORADIOBUTTON],
        [BUTTON,          action_score,         IDC_BUT_ACT_SCORE,   (15,62,203,10), csts | win32con.BS_AUTORADIOBUTTON],


        [BUTTON,          only_group,           -1,                  (7,84,230,35),  cs   | win32con.BS_GROUPBOX | win32con.WS_GROUP],
        [BUTTON,          only_unread,          IDC_BUT_UNREAD,      (15,94,149,9),  csts | win32con.BS_AUTOCHECKBOX],
        [BUTTON,          only_unseen,          IDC_BUT_UNSEEN,      (15,106,149,9), csts | win32con.BS_AUTOCHECKBOX],

        ["msctls_progress32", '',               IDC_PROGRESS,        (7,129,230,11), cs | win32con.WS_BORDER],
        [STATIC,          '',                   IDC_PROGRESS_TEXT,   (7,144,227,10), cs ],

        [BUTTON,         process_start_text,    IDC_START,           (7,161,50,14),   csts | win32con.BS_DEFPUSHBUTTON],
        [BUTTON,         'Close',               win32con.IDCANCEL,   (187,161,50,14), csts | win32con.BS_PUSHBUTTON],
    ]
    disable_while_running_ids = [IDC_BUT_UNSEEN, IDC_BUT_UNREAD,
                                 IDC_BROWSE, win32con.IDCANCEL,
                                 IDC_BUT_ACT_SCORE, IDC_BUT_ACT_SCORE]

    def __init__(self, mgr, filterer):
        self.mgr = mgr
        self.filterer = filterer
        AsyncDialogBase.__init__ (self, self.dt)

    def OnInitDialog(self):
        self.HookCommand(self.OnButBrowse, IDC_BROWSE)
        self.HookCommand(self.OnButUnread, IDC_BUT_UNREAD)
        self.HookCommand(self.OnButUnseen, IDC_BUT_UNSEEN)
        self.HookCommand(self.OnButAction, IDC_BUT_ACT_SCORE)
        self.HookCommand(self.OnButAction, IDC_BUT_ACT_ALL)
        self.GetDlgItem(IDC_BUT_UNREAD).SetCheck(self.mgr.config.filter_now.only_unread)
        self.GetDlgItem(IDC_BUT_UNSEEN).SetCheck(self.mgr.config.filter_now.only_unseen)
        if self.mgr.config.filter_now.action_all:
            self.GetDlgItem(IDC_BUT_ACT_ALL).SetCheck(True)
        else:
            self.GetDlgItem(IDC_BUT_ACT_SCORE).SetCheck(True)
        self.UpdateFolderNames()
        return AsyncDialogBase.OnInitDialog(self)

    def UpdateFolderNames(self):
        names = []
        for eid in self.mgr.config.filter_now.folder_ids:
            try:
                name = self.mgr.message_store.GetFolder(eid).name
            except pythoncom.com_error:
                name = "<unknown folder>"
            names.append(name)
        self.SetDlgItemText(IDC_FOLDER_NAMES, "; ".join(names))

    def OnButBrowse(self, id, code):
        if code == win32con.BN_CLICKED:
            import FolderSelector
            filter = self.mgr.config.filter_now
            d = FolderSelector.FolderSelector(self.mgr,
                                              filter.folder_ids,
                                              checkbox_state=filter.include_sub)
            if d.DoModal() == win32con.IDOK:
                filter.folder_ids, filter.include_sub = d.GetSelectedIDs()
                self.UpdateFolderNames()

    def OnButAction(self, id, code):
        if code == win32con.BN_CLICKED:
            self.mgr.config.filter_now.action_all = self.GetDlgItem(IDC_BUT_ACT_ALL).GetCheck() != 0
    def OnButUnread(self, id, code):
        if code == win32con.BN_CLICKED:
            self.mgr.config.filter_now.only_unread = self.GetDlgItem(IDC_BUT_UNREAD).GetCheck() != 0
    def OnButUnseen(self, id, code):
        if code == win32con.BN_CLICKED:
            self.mgr.config.filter_now.only_unseen = self.GetDlgItem(IDC_BUT_UNSEEN).GetCheck() != 0

    def StartProcess(self):
        # Must do this here, as we are still in the main thread.
        # Outlook gets upset when used from a different thread.
        config = self.mgr.config.filter_now
        for folder_id in config.folder_ids:
            self.mgr.EnsureOutlookFieldsForFolder(folder_id, config.include_sub)
        return AsyncDialogBase.StartProcess(self)

    def _DoProcess(self):
        if self.filterer is None:
            print "Testing, testing, 1...2...3..."
        else:
            self.mgr.WorkerThreadStarting()
            try:
                self.filterer(self.mgr, self.progress)
            finally:
                self.mgr.WorkerThreadEnding()

if __name__=='__main__':
    from win32com.client import Dispatch
    outlook = Dispatch("Outlook.Application")

    import sys; sys.path.append('..')
    import msgstore

    class Config: pass
    class Manager:
        def FormatFolderNames(self, folder_ids, include_sub):
            return "Folder 1; Folder 2"

    mgr = Manager()
    mgr.message_store = msgstore.MAPIMsgStore()
    mgr.config = config = Config()
    config.filter = Config()
    inbox = outlook.Session.GetDefaultFolder(constants.olFolderInbox)
    config.filter.watch_folder_ids = [(inbox.StoreID, inbox.EntryID)]
    config.filter.watch_include_sub = True
    config.filter.spam_folder_id = ""
    config.filter.spam_action = "Mo"
    config.filter.spam_threshold = 80
    config.filter.unsure_folder_id = ""
    config.filter.unsure_action = "No"
    config.filter.unsure_threshold = 20
    config.filter_now=Config()
    inbox = outlook.Session.GetDefaultFolder(constants.olFolderInbox)
    config.filter_now.folder_ids = [(inbox.StoreID, inbox.EntryID)]
    config.filter_now.include_sub = True
    config.filter_now.only_unread = False
    config.filter_now.only_unseen = True
    config.filter_now.action_all = True

    tester = FilterArrivalsDialog
##    tester = FilterNowDialog
    d = tester(mgr, None)
    if d.DoModal() == win32con.IDOK:
        # do it again to make sure all config data is reflected.
        d = tester(mgr, None)
        d.DoModal()
