from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api
import pythoncom

from DialogGlobals import *

IDC_RULE_NAME = 1024
IDC_SLIDER_LOW = 1025
IDC_EDIT_LOW = 1026
IDC_SLIDER_HIGH = 1027
IDC_EDIT_HIGH = 1028
IDC_ACTION = 1029
IDC_FOLDER_NAME = 1030
IDC_BROWSE = 1031
IDC_FLAG = 1032
IDC_FIELD_NAME = 1033
IDC_WRITE_FIELD = 1034

class RuleDialog(dialog.Dialog):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    csts = cs | win32con.WS_TABSTOP
    treestyle = cs | win32con.WS_BORDER | commctrl.TVS_CHECKBOXES | commctrl.TVS_DISABLEDRAGDROP | commctrl.TVS_SHOWSELALWAYS
    filter_msg = "Filter the following folders as messages arrive"
    dt = [
        # Dialog itself.
        ["Define Rule", (0, 0, 249, 199), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          "Enter a name for the filter", -1,         (  7,   6,  94,  11), cs],
        [EDIT,            "",                   IDC_RULE_NAME,       (120,   6, 118,  14), csts | win32con.ES_AUTOHSCROLL | win32con.WS_BORDER],
        [STATIC,          "When the spam rating is between", -1,     (  7,  23, 107,  10), cs],
        ["msctls_trackbar32", "",               IDC_SLIDER_LOW,      (  7,  38, 112,   8), cs   | commctrl.TBS_BOTH | commctrl.TBS_NOTICKS],
        [EDIT,            "",                   IDC_EDIT_LOW,        (120,  34,  59,  14), csts | win32con.ES_AUTOHSCROLL | win32con.WS_BORDER],
        [STATIC,          "and",                -1,                  (  7,  46, 107,  10), cs],
        ["msctls_trackbar32", "",               IDC_SLIDER_HIGH,     (  7,  57, 112,   8), cs   | commctrl.TBS_BOTH | commctrl.TBS_NOTICKS],
        [EDIT,            "",                   IDC_EDIT_HIGH,       (120,  54,  59,  14), csts | win32con.ES_AUTOHSCROLL | win32con.WS_BORDER],

        [STATIC,          "Take the following actions", -1,          (  7,  72, 107,  10), cs],

        [BUTTON,          "Copy/Move message",  -1,                  (  7,  86, 235,  35), cs   | win32con.BS_GROUPBOX],
        [COMBOBOX,        "",                   IDC_ACTION,          ( 14,  97,  55,  40), csts | win32con.CBS_DROPDOWNLIST | win32con.WS_VSCROLL],
        [STATIC,          "to folder",          -1,                  ( 79,  99,  31,  10), cs],
        [STATIC,          "",                   IDC_FOLDER_NAME,     ( 120, 97,  59,  14), cs   | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],
        [BUTTON,          '&Browse',            IDC_BROWSE,          (186,  97,  50,  14), csts | win32con.BS_PUSHBUTTON],

        [BUTTON,          "Modify message",     -1,                  (  7, 129, 235,  45), cs   | win32con.BS_GROUPBOX],
        [BUTTON,          "Create a flag on the message", IDC_FLAG,  ( 11, 137, 109,  16), csts | win32con.BS_AUTOCHECKBOX],
        [BUTTON,          "Write spam score to field", IDC_WRITE_FIELD, (11,151,108,  15), csts | win32con.BS_AUTOCHECKBOX],
        [EDIT,            "",                   IDC_FIELD_NAME,      (120, 152,  59,  14), csts | win32con.ES_AUTOHSCROLL | win32con.WS_BORDER],

        [BUTTON,         'OK',                  win32con.IDOK,       (129, 178,  50,  14), csts | win32con.BS_DEFPUSHBUTTON],
        [BUTTON,         'Cancel',              win32con.IDCANCEL,   (192, 178,  50,  14), csts | win32con.BS_PUSHBUTTON],
    ]

    def __init__(self, rule, mgr = None):
        self.rule = rule
        self.mgr = mgr
        self.folder_id = rule.folder_id
        dialog.Dialog.__init__ (self, self.dt)

    def OnInitDialog(self):
        rule = self.rule
        self.SetDlgItemText(IDC_RULE_NAME, rule.name)
        self.SetDlgItemText(IDC_EDIT_LOW, "%.2f" % rule.min)
        self.SetDlgItemText(IDC_EDIT_HIGH, "%.2f" % rule.max)
        self.GetDlgItem(IDC_FLAG).SetCheck(rule.flag_message)
        self.GetDlgItem(IDC_WRITE_FIELD).SetCheck(rule.write_field)
        edit = self.GetDlgItem(IDC_FIELD_NAME)
        edit.SetWindowText(rule.write_field_name)
        edit.EnableWindow(rule.write_field)

        self._InitSlider(IDC_SLIDER_HIGH, IDC_EDIT_HIGH)
        self._InitSlider(IDC_SLIDER_LOW, IDC_EDIT_LOW)
        self.HookMessage (self.OnSlider, win32con.WM_HSCROLL)
        self.HookCommand(self.OnEditChange, IDC_EDIT_HIGH)
        self.HookCommand(self.OnEditChange, IDC_EDIT_LOW)
        self.HookCommand(self.OnButWriteField, IDC_WRITE_FIELD)
        self.HookCommand(self.OnButBrowse, IDC_BROWSE)
        self._UpdateFolderName()

        combo = self.GetDlgItem(IDC_ACTION)
        index = sel_index = 0
        for s in ["None", "Move", "Copy"]:
            combo.AddString(s)
            if s == rule.action: sel_index = index
            index+=1
        combo.SetCurSel(sel_index)
        return dialog.Dialog.OnInitDialog(self)

    def _UpdateFolderName(self):
        try:
            if not self.folder_id:
                name = ""
            elif self.mgr.mapi is None:
                name = "<no mapi!>"
            else:
                name = self.mgr.mapi.GetFolder(self.folder_id).Name.encode("ascii", "replace")
        except pythoncom.com_error:
            name = "<unknown folder>"
        self.SetDlgItemText(IDC_FOLDER_NAME, name)

    def OnEditChange(self, controlid, code):
        if code==win32con.EN_CHANGE:
            if controlid == IDC_EDIT_HIGH:
                sliderid = IDC_SLIDER_HIGH
            else:
                sliderid = IDC_SLIDER_LOW
            self._AdjustSliderToEdit(sliderid, controlid)
        return 1 # I handled this, so no need to call defaults!

    def OnButWriteField(self, id, code):
        if code == win32con.BN_CLICKED:
            edit = self.GetDlgItem(IDC_FIELD_NAME)
            edit.EnableWindow( self.GetDlgItem(IDC_WRITE_FIELD).GetCheck() )
        return 1

    def OnButBrowse(self, id, code):
        if code == win32con.BN_CLICKED:
            import FolderSelector
            ids = [self.folder_id]
            d = FolderSelector.FolderSelector(self.mgr.mapi, ids,single_select=True,checkbox_state=None)#, allow_multi=False)
            if d.DoModal()==win32con.IDOK:
                new_ids, cb_state = d.GetSelectedIDs()
                if new_ids:
                    self.folder_id = new_ids[0]
                    self._UpdateFolderName()
        return 1

    def OnSlider(self, params):
        lParam = params[3]
        slider = self.GetDlgItem(IDC_SLIDER_HIGH)
        if slider.GetSafeHwnd() == lParam:
            idc_edit = IDC_EDIT_HIGH
        else:
            slider = self.GetDlgItem(IDC_SLIDER_LOW)
            assert slider.GetSafeHwnd() == lParam
            idc_edit = IDC_EDIT_LOW
        self.SetDlgItemText(idc_edit, "%.2f" % (slider.GetPos() / 100.0))

    def _InitSlider(self, idc_slider, idc_edit):
        slider = self.GetDlgItem(idc_slider)
        slider.SetRange(0, 100, 0)
        slider.SetLineSize(1)
        slider.SetPageSize(5)
        self._AdjustSliderToEdit(idc_slider, idc_edit)

    def _AdjustSliderToEdit(self, idc_slider, idc_edit):
        slider = self.GetDlgItem(idc_slider)
        edit = self.GetDlgItem(idc_edit)
        try:
            fval = float(edit.GetWindowText())
        except ValueError:
            return
        slider.SetPos(int(fval*100))

    def _CheckEdit(self, idc, rule, attr):
        try:
            val = float(self.GetDlgItemText(idc))
            if val < 0 or val > 1.0:
                raise ValueError
        except ValueError:
            self.MessageBox("Please enter a number between 0 and 1")
            self.GetDlgItem(idc).SetFocus()
            return False
        setattr(rule, attr, val)
        return True

    def OnOK(self):
        rule = self.rule
        if not self._CheckEdit(IDC_EDIT_HIGH, rule, "max") or \
           not self._CheckEdit(IDC_EDIT_LOW, rule, "min"):
            return 1
        combo = self.GetDlgItem(IDC_ACTION)
        rule.name = self.GetDlgItemText(IDC_RULE_NAME)
        rule.action = combo.GetLBText(combo.GetCurSel())
        rule.flag_message = self.GetDlgItem(IDC_FLAG).GetCheck()
        rule.write_field = self.GetDlgItem(IDC_WRITE_FIELD).GetCheck()
        rule.write_field_name = self.GetDlgItemText(IDC_FIELD_NAME)
        rule.folder_id = self.folder_id
        problem = rule.GetProblem(self.mgr)
        if problem is not None:
            self.MessageBox(problem)
            return 1
        return self._obj_.OnOK()
    def OnCancel(self):
        return self._obj_.OnCancel()

if __name__=='__main__':
    from win32com.client import Dispatch
    try:
        mapi = Dispatch("MAPI.Session")
        mapi.Logon()
    except pythoncom.com_error:
        mapi = None
    class Rule:
        def __init__(self):
            self.name = "My Rule"
            self.min = 0.1
            self.max = 0.9
            self.action = "Move"
            self.flag_message = True
            self.write_field = True
            self.write_field_name = "SpamProb"
            self.folder_id = ""
        def GetProblem(self, mgr):
            if self.min > self.max:
                return "max must be > min"

    class Manager: pass
    mgr = Manager()
    mgr.mapi = mapi


    rule = Rule()
    d = RuleDialog(rule, mgr)
    if d.DoModal() == win32con.IDOK:
        print "Name:", rule.name
        print "min,max:", rule.min, rule.max
        print "Action:", rule.action
        print "Write Field:", rule.write_field, ", to:", rule.write_field_name
        print "Flag message:", rule.flag_message
