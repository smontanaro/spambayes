import os

from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api
from win32com.client import constants

#these are the atom numbers defined by Windows for basic dialog controls
BUTTON    = 0x80
EDIT      = 0x81
STATIC    = 0x82
LISTBOX   = 0x83
SCROLLBAR = 0x84
COMBOBOX  = 0x85

IDC_STATIC_HAM = 1001
IDC_BROWSE_HAM = 1002
IDC_STATIC_SPAM = 1003
IDC_BROWSE_SPAM = 1004
IDC_BUT_REBUILD = 1005
IDC_BUT_RESCORE = 1006
from AsyncDialog import IDC_START, IDC_PROGRESS, IDC_PROGRESS_TEXT, AsyncDialogBase


class TrainingDialog(AsyncDialogBase):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    ham_title = "Folders with known good messages"
    spam_title = "Folders with known spam or other junk messages"
    process_start_text = "&Train now"
    process_stop_text = "Stop &training"
    dt = [
        # Dialog itself.
        ["Training", (0, 0, 241, 140), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          ham_title,            -1,                   (  7,   6, 131,  11), cs ],
        [STATIC,          "",                   IDC_STATIC_HAM,       (  7,  17, 167,  12), cs | win32con.SS_SUNKEN | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE],
        [BUTTON,          '&Browse',            IDC_BROWSE_HAM,       (184,  17,  50,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],

        [STATIC,          spam_title,           -1,                   (  7,  36, 171,   9), cs ],
        [STATIC,          "",                   IDC_STATIC_SPAM,      (  7,  47, 167,  12), cs | win32con.SS_SUNKEN | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE],
        [BUTTON,          'Brow&se',            IDC_BROWSE_SPAM,      (184,  47,  50,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],
        [BUTTON,          'Rebuild entire database',IDC_BUT_REBUILD,  (  7,  67, 174,  10), cs | win32con.BS_AUTOCHECKBOX | win32con.WS_TABSTOP],
        [BUTTON,          'Score messages after training',IDC_BUT_RESCORE,(  7,  77, 174,  10), cs | win32con.BS_AUTOCHECKBOX | win32con.WS_TABSTOP],

        [BUTTON,         process_start_text,    IDC_START,            (  7, 119,  50,  14), cs | win32con.BS_DEFPUSHBUTTON | win32con.WS_TABSTOP],
        ["msctls_progress32", '',               IDC_PROGRESS,         (  7,  92, 166,  11), cs | win32con.WS_BORDER],
        [STATIC,          '',                   IDC_PROGRESS_TEXT,    (  7, 108, 227,  10), cs ],

        [BUTTON,          'Close',              win32con.IDOK,        (184, 119,  50,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],

    ]
    disable_while_running_ids = [IDC_BROWSE_HAM,
                                 IDC_BROWSE_SPAM,
                                 IDC_BUT_REBUILD,
                                 IDC_BUT_RESCORE,
                                 win32con.IDOK]

    def __init__ (self, mgr, trainer):
        self.mgr = mgr
        self.trainer = trainer
        self.config = mgr.config.training
        AsyncDialogBase.__init__ (self, self.dt)

    def OnInitDialog(self):
        self.HookCommand(self.OnBrowse, IDC_BROWSE_SPAM)
        self.HookCommand(self.OnBrowse, IDC_BROWSE_HAM)
        self.UpdateStatus()
        return AsyncDialogBase.OnInitDialog (self)

    def UpdateStatus(self):
        # Set some defaults.
        # If we have no known ham folders, suggest the folder we watch
        if len(self.config.ham_folder_ids)==0 and self.mgr.outlook is not None:
            self.config.ham_folder_ids = self.mgr.config.filter.watch_folder_ids[:]
        # If we have no known spam folders, but do have a spam folder
        # defined in the filters, use it.
        if len(self.config.spam_folder_ids)==0 and self.mgr.config.filter.spam_folder_id:
            self.config.spam_folder_ids = [self.mgr.config.filter.spam_folder_id]

        names = []
        for eid in self.config.ham_folder_ids:
            folder = self.mgr.message_store.GetFolder(eid)
            if folder is None:
                name = "<unknown folder>"
            else:
                name = folder.name
            names.append(name)
        self.SetDlgItemText(IDC_STATIC_HAM, "; ".join(names))

        names = []
        for eid in self.config.spam_folder_ids:
            folder = self.mgr.message_store.GetFolder(eid)
            if folder is None:
                name = "<unknown folder>"
            else:
                name = folder.name
            names.append(name)
        self.SetDlgItemText(IDC_STATIC_SPAM, "; ".join(names))
        if self.config.rescore:
            self.GetDlgItem(IDC_BUT_RESCORE).SetCheck(1)
        else:
            self.GetDlgItem(IDC_BUT_RESCORE).SetCheck(0)

    def OnBrowse(self, id, code):
        if code == win32con.BN_CLICKED:
            import FolderSelector
            if id==IDC_BROWSE_SPAM:
                l = self.config.spam_folder_ids
                sub_attr = "spam_include_sub"
            else:
                l = self.config.ham_folder_ids
                sub_attr = "ham_include_sub"
            include_sub = getattr(self.config, sub_attr)
            d = FolderSelector.FolderSelector(self.mgr, l, checkbox_state=include_sub)
            if d.DoModal()==win32con.IDOK:
                l[:], include_sub = d.GetSelectedIDs()[:]
                setattr(self.config, sub_attr, include_sub)
                self.UpdateStatus()

    def StartProcess(self):
        self.rebuild = self.GetDlgItem(IDC_BUT_REBUILD).GetCheck() != 0
        self.rescore = self.GetDlgItem(IDC_BUT_RESCORE).GetCheck() != 0
        self.config.rescore = self.rescore
        return AsyncDialogBase.StartProcess(self)

    def _DoProcess(self):
        self.mgr.WorkerThreadStarting()
        try:
            self.trainer(self.mgr, self.progress, self.rebuild, self.rescore)
        finally:
            self.mgr.WorkerThreadEnding()

##if __name__=='__main__':
##    d=TrainingDialog(None)
##    d.DoModal()
