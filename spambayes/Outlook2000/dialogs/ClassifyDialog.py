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

IDC_STATIC_FOLDERS = 1001
IDC_BROWSE = 1002
IDC_FIELDNAME = 1003
from AsyncDialog import IDC_START, IDC_PROGRESS, IDC_PROGRESS_TEXT, AsyncDialogBase


class ClassifyDialog(AsyncDialogBase):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    info_text = "For every message in the selected folders, a new field will be created with the spam rating.  The Outlook 'Field Chooser' can show the field"
    classify_text = "Classify messages in the following folder"
    process_start_text = "&Classify now"
    process_stop_text = "Stop &classification"
    dt = [
        # Dialog itself.
        ["Classification", (0, 0, 241, 130), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          info_text,            -1,                   (  7,  6, 227,  16), cs ],
        [STATIC,          classify_text,        -1,                   (  7, 29, 131,  11), cs ],

        [STATIC,          "",                   IDC_STATIC_FOLDERS,   (  7,  40, 167,  12), cs | win32con.SS_SUNKEN | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE],
        [BUTTON,          '&Browse',            IDC_BROWSE,           (184,  40,  50,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],

        [STATIC,          "Field name to create",-1,                  (  7,  60,  67,  11), cs],
        [EDIT,            "",                    IDC_FIELDNAME,       ( 80,  57,  93,  14), cs | win32con.WS_BORDER | win32con.ES_AUTOHSCROLL],

        [BUTTON,         process_start_text,    IDC_START,            (  7, 109,  70,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],
        ["msctls_progress32", '',               IDC_PROGRESS,         (  7,  80, 166,  11), cs | win32con.WS_BORDER],
        [STATIC,          '',                   IDC_PROGRESS_TEXT,    (  7,  96, 227,  10), cs ],

        [BUTTON,          'Close',              win32con.IDOK,        (184, 109,  50,  14), cs | win32con.BS_DEFPUSHBUTTON | win32con.WS_TABSTOP],

    ]
    disable_while_running_ids = [IDC_FIELDNAME, IDC_BROWSE, win32con.IDOK]

    def __init__ (self, mgr, classifier):
        self.classifier = classifier
        self.config = mgr.config.classify
        self.mapi = mgr.mapi
        self.mgr = mgr
        AsyncDialogBase.__init__ (self, self.dt)

    def OnInitDialog(self):
        self.HookCommand(self.OnBrowse, IDC_BROWSE)
        self.SetDlgItemText(IDC_FIELDNAME, self.config.field_name)
        self.UpdateStatus()
        return AsyncDialogBase.OnInitDialog (self)

    def UpdateStatus(self):
        names = []
        for eid in self.config.folder_ids:
            try:
                name = self.mapi.GetFolder(eid).Name.encode("ascii", "replace")
            except pythoncom.com_error:
                name = "<unknown folder>"
            names.append(name)
        self.SetDlgItemText(IDC_STATIC_FOLDERS, "; ".join(names))

    def OnBrowse(self, id, code):
        if code == win32con.BN_CLICKED:
            import FolderSelector
            l = self.config.folder_ids
            d = FolderSelector.FolderSelector(self.mapi, l,checkbox_state=self.config.include_sub)
            if d.DoModal()==win32con.IDOK:
                l[:], self.config.include_sub = d.GetSelectedIDs()[:]
                self.UpdateStatus()

    def _DoProcess(self):
        fieldName = self.GetDlgItemText(IDC_FIELDNAME)
        if not fieldName:
            self.progress.error("You must specify a field name")
            return
        self.config.field_name = fieldName
        self.mgr.WorkerThreadStarting()
        try:
            self.classifier(self.mgr, self.progress)
        finally:
            self.mgr.WorkerThreadEnding()
