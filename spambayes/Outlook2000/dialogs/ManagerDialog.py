from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api
import pythoncom

from DialogGlobals import *

IDC_BUT_MOREINFO = 1024
IDC_BUT_DB = 1025
IDC_BUT_TRAIN = 1026
IDC_DB_STATUS = 1027
IDC_BUT_ENABLE_FILTER = 1028
IDC_BUT_FILTER = 1029
IDC_FILTER_STATUS = 1030
IDC_BUT_CLASSIFY = 1031

class ManagerDialog(dialog.Dialog):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    csts = cs | win32con.WS_TABSTOP
    filter_msg = "Filter the following folders as messages arrive"
    intro_msg = "This application filters out spam by continually learning the characteristics of email you recieve and filtering spam from your regular email.  The system must be trained before it will be effective."
    training_intro = "Training is the process of giving examples of both good and bad email to the system so it can classify future email"
    filtering_intro = "Filtering is the process of deleting, moving or otherwise modifying messages based on their spam probability"
    classify_intro = "Classification is the process of adding properties to messages based on their Spam probability.  Creating a property with the spam rating allows you to select the field using the Outlook Field Chooser."
    
    dt = [
        # Dialog itself.
        ["Anti-Spam", (0, 0, 242, 277), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          intro_msg,            -1,                  (  7,   7, 228,  25), cs],
        [BUTTON,          'Details...',         IDC_BUT_MOREINFO,    (168,  33,  62,  14), csts | win32con.BS_PUSHBUTTON],

        [BUTTON,          "Database and Training", -1,               (  7,  49, 228,  62), cs   | win32con.BS_GROUPBOX],
        [STATIC,          training_intro,       -1,                  ( 15,  57, 215,  17), cs],
        [BUTTON,          'Database Options',   IDC_BUT_DB,          ( 15,  77,  62,  14), csts | win32con.BS_PUSHBUTTON | win32con.WS_DISABLED],
        [BUTTON,          '&Training',          IDC_BUT_TRAIN,       (168,  77,  62,  14), csts | win32con.BS_PUSHBUTTON],
        [STATIC,          "",                   IDC_DB_STATUS,       ( 15,  95, 215,  12), cs   | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],

        [BUTTON,          "Filtering",          -1,                  (  7, 116, 228,  68), cs   | win32con.BS_GROUPBOX],
        [STATIC,          filtering_intro,      -1,                  ( 15, 127, 215,  17), cs],
        [BUTTON,          'Enable &filtering',  IDC_BUT_ENABLE_FILTER,(24, 147, 131,  11), csts | win32con.BS_AUTOCHECKBOX],
        [BUTTON,          'Define filters...',  IDC_BUT_FILTER,      (168, 144,  62,  14), csts | win32con.BS_PUSHBUTTON],
        [STATIC,          "",                   IDC_FILTER_STATUS,   ( 15, 162, 215,  12), cs   | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],
         
        [BUTTON,          "Classification",     -1,                  (  7, 188, 228,  61), cs   | win32con.BS_GROUPBOX],
        [STATIC,          classify_intro,       -1,                  ( 15, 201, 215,  26), cs],
        [BUTTON,          'Classify...',        IDC_BUT_CLASSIFY,    (168, 228,  62,  14), csts | win32con.BS_PUSHBUTTON],

        [BUTTON,         'Close',               win32con.IDOK,       (168, 256,  62,  14), csts | win32con.BS_DEFPUSHBUTTON],
    ]

    def __init__(self, mgr, do_train, do_filter, do_classify):
        self.mgr = mgr
        self.do_train = do_train
        self.do_filter = do_filter
        self.do_classify = do_classify
        dialog.Dialog.__init__(self, self.dt)

    def OnInitDialog(self):
        self.HookCommand(self.OnButMoreInfo, IDC_BUT_MOREINFO)
        self.HookCommand(self.OnButDoSomething, IDC_BUT_TRAIN)
        self.HookCommand(self.OnButDoSomething, IDC_BUT_FILTER)
        self.HookCommand(self.OnButDoSomething, IDC_BUT_CLASSIFY)
        self.HookCommand(self.OnButEnableFilter, IDC_BUT_ENABLE_FILTER)
        self.UpdateControlStatus()
        return dialog.Dialog.OnInitDialog(self)

    def UpdateControlStatus(self):
        nspam = self.mgr.bayes.nspam
        nham = self.mgr.bayes.nham
        enable_buttons = nspam > 0 and nham > 0
        if enable_buttons:
            db_status = "Database has %d good and %d spam messages" % (nham, nspam)
        else:
            db_status = "Database must be trained before use"
        for id in [IDC_BUT_FILTER, IDC_BUT_CLASSIFY, IDC_BUT_ENABLE_FILTER]:
            self.GetDlgItem(id).EnableWindow(enable_buttons)
        self.SetDlgItemText(IDC_DB_STATUS, db_status)
        if not enable_buttons:
            self.mgr.config.filter.enabled = False
            self.GetDlgItem(IDC_BUT_ENABLE_FILTER).SetCheck(0)
            return

        # Build a filter-status string
        self.GetDlgItem(IDC_BUT_ENABLE_FILTER).SetCheck(self.mgr.config.filter.enabled)
        names = []
        for eid in self.mgr.config.filter.folder_ids:
            names.append(self.mgr.mapi.GetFolder(eid).Name.encode("ascii", "replace"))
        # count enabled rules
        num = len([r for r in self.mgr.config.rules if r.enabled ])
        if num == 0:
            num_rules_text = " with no active rules"
        elif num == 1:
            num_rules_text = " with 1 active rule"
        else:
            num_rules_text = " with %d active rules" % (num,)

        if not names:
            status = "No folders are being filtered"
        elif len(names) == 1:
            status = "Filtering %s%s." % (names[0], num_rules_text)
        elif len(names) == 2:
            status = "Filtering %s;%s%s." % (names[0], names[1], num_rules_text)
        else:
            status = "Filtering %d folders%s." % (len(names), num_rules_text)
        self.SetDlgItemText(IDC_FILTER_STATUS, status)

    def OnButMoreInfo(self, id, code):
        if code == win32con.BN_CLICKED:
            self.MessageBox("Contributions of HTML code to display here would be welcome :)")

    def OnButDoSomething(self, id, code):
        if code == win32con.BN_CLICKED:
            if id == IDC_BUT_TRAIN:
                doer = self.do_train
            elif id == IDC_BUT_CLASSIFY:
                doer = self.do_classify
            elif id == IDC_BUT_FILTER:
                doer = self.do_filter
            else:
                raise RuntimeError, "Unknown button ID!"
            doer(self)
            self.UpdateControlStatus()

    def OnButEnableFilter(self, id, code):
        if code == win32con.BN_CLICKED:
            self.mgr.config.filter.enabled = self.GetDlgItem(IDC_BUT_ENABLE_FILTER).GetCheck()==1
        
    def OnOK(self):
        return dialog.Dialog.OnOK(self)

if __name__=='__main__':
    def doer(dlg): print "doing something"
    class Generic: pass
    mgr = Generic()
    mgr.bayes = Generic()
    mgr.bayes.nham = 20
    mgr.bayes.nspam = 7
    d = ManagerDialog(mgr, doer, doer, doer)
    d.DoModal()
