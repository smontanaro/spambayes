import os

from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api

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
        ["Training", (0, 0, 241, 118), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          ham_title,            -1,                   (  7,   6, 131,  11), cs ],
        [STATIC,          "",                   IDC_STATIC_HAM,       (  7,  17, 167,  12), cs | win32con.SS_SUNKEN | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE],
        [BUTTON,          '&Browse',            IDC_BROWSE_HAM,       (184,  17,  50,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],

        [STATIC,          spam_title,           -1,                   (  7,  36, 171,   9), cs ],
        [STATIC,          "",                   IDC_STATIC_SPAM,      (  7,  47, 167,  12), cs | win32con.SS_SUNKEN | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE],
        [BUTTON,          'Brow&se',            IDC_BROWSE_SPAM,      (184,  47,  50,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],

        [BUTTON,         process_start_text,    IDC_START,            (  7,  97,  50,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],
        ["msctls_progress32", '',               IDC_PROGRESS,         (  7,  68, 166,  11), cs | win32con.WS_BORDER],
        [STATIC,          '',                   IDC_PROGRESS_TEXT,    (  7,  84, 227,  10), cs ],

        [BUTTON,          'Close',              win32con.IDOK,        (184,  97,  50,  14), cs | win32con.BS_DEFPUSHBUTTON | win32con.WS_TABSTOP],

    ]
    disable_while_running_ids = [IDC_BROWSE_HAM, IDC_BROWSE_SPAM, win32con.IDOK]

    def __init__ (self, mgr, trainer):
        self.mgr = mgr
        self.trainer = trainer
        self.config = mgr.config.training
        self.mapi = mgr.mapi
        AsyncDialogBase.__init__ (self, self.dt)

    def OnInitDialog(self):
        self.HookCommand(self.OnBrowse, IDC_BROWSE_SPAM)
        self.HookCommand(self.OnBrowse, IDC_BROWSE_HAM)
        self.UpdateStatus()
        return AsyncDialogBase.OnInitDialog (self)

    def UpdateStatus(self):
        names = []
        cwd = os.getcwd()  # mapi.GetFolder() switches to the system MAPI dir
        for eid in self.config.ham_folder_ids:
            try:
                name = self.mapi.GetFolder(eid).Name.encode("ascii", "replace")
            except pythoncom.com_error:
                name = "<unknown folder>"
            names.append(name)
        self.SetDlgItemText(IDC_STATIC_HAM, "; ".join(names))

        names = []
        for eid in self.config.spam_folder_ids:
            try:
                name = self.mapi.GetFolder(eid).Name.encode("ascii", "replace")
            except pythoncom.com_error:
                name = "<unknown folder>"
            names.append(name)
        self.SetDlgItemText(IDC_STATIC_SPAM, "; ".join(names))
        os.chdir(cwd)

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
            d = FolderSelector.FolderSelector(self.mapi, l, checkbox_state=include_sub)
            if d.DoModal()==win32con.IDOK:
                l[:], include_sub = d.GetSelectedIDs()[:]
                setattr(self.config, sub_attr, include_sub)
                self.UpdateStatus()

    def _DoProcess(self):
        self.mgr.WorkerThreadStarting()
        try:
            self.trainer(self.mgr, self.progress)
        finally:
            self.mgr.WorkerThreadEnding()

##if __name__=='__main__':
##    d=TrainingDialog(None)
##    d.DoModal()
