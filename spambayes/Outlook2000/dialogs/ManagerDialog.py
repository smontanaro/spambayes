import os, sys
import operator

from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api
import pythoncom

from DialogGlobals import *

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


IDC_BUT_ABOUT = 1024
IDC_BUT_TRAIN_FROM_SPAM_FOLDER = 1025
IDC_BUT_TRAIN_TO_SPAM_FOLDER = 1026
IDC_BUT_TRAIN_NOW = 1027
IDC_BUT_FILTER_NOW = 1028
IDC_BUT_FILTER_DEFINE= 1029
IDC_BUT_FILTER_ENABLE = 1030
IDC_BUT_ADVANCED= 1031
IDC_TRAINING_STATUS = 1032
IDC_FILTER_STATUS = 1033
IDC_VERSION = 1034

class ManagerDialog(dialog.Dialog):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    csts = cs | win32con.WS_TABSTOP
    training_intro = "Training is the process of giving examples of both good and bad email to the system so it can classify future email"
    filtering_intro = "Filtering defines how spam is handled as it arrives"

    dt = [
        # Dialog itself.
        ["SpamBayes", (0, 0, 242, 201), style, None, (8, "MS Sans Serif")],
        [STATIC,          "",                   IDC_VERSION,         (8,4,230,11),   cs | win32con.SS_LEFTNOWORDWRAP],
        # Training
        [BUTTON,          "Training",           -1,                  (8,17,227,103), cs   | win32con.BS_GROUPBOX],
        [STATIC,          training_intro,       -1,                  (15,27,215,17), cs],
        [STATIC,          "Automatically train that a message is good when",
                                                -1,                  (15,50,208,10), cs],
        [BUTTON,          "It is moved from a spam folder back to the Inbox",
                                                IDC_BUT_TRAIN_FROM_SPAM_FOLDER,(20,60,204,9), csts | win32con.BS_AUTOCHECKBOX],

        [STATIC,          "Automatically train that a message is spam when",
                                                -1,                  (15,74,208,10), cs],
        [BUTTON,          "It is moved to the certain-spam folder",
                                                IDC_BUT_TRAIN_TO_SPAM_FOLDER,(20,85,204,9), csts | win32con.BS_AUTOCHECKBOX],

        [STATIC,          "",                   IDC_TRAINING_STATUS, (15,98,146,14),       cs   | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],
        [BUTTON,          'Train Now...',       IDC_BUT_TRAIN_NOW,   (167,98,63,14),       csts | win32con.BS_PUSHBUTTON],

        # Filter
        [BUTTON,          "Filtering",          -1,                   (7,122,228,57), cs   | win32con.BS_GROUPBOX],
        [STATIC,          filtering_intro,      -1,                   (15,131,202,8), cs],
        [BUTTON,          'Enable &filtering',  IDC_BUT_FILTER_ENABLE,(20,143,120,11),csts | win32con.BS_AUTOCHECKBOX],
        [STATIC,          "",                   IDC_FILTER_STATUS,    (15,157,146,18),cs   | win32con.SS_SUNKEN],
        [BUTTON,          'Filter Now...',      IDC_BUT_FILTER_NOW,   (167,141,63,14),   csts | win32con.BS_PUSHBUTTON],
        [BUTTON,          'Define filters...',  IDC_BUT_FILTER_DEFINE,(167,160,63,14),csts | win32con.BS_PUSHBUTTON],

        #[BUTTON,         'Advanced...',         IDC_BUT_ADVANCED,     (15,184,62,14), csts | win32con.BS_PUSHBUTTON | win32con.WS_DISABLED ],
        [BUTTON,         'About...',            IDC_BUT_ABOUT,        (99,184,62,14), csts | win32con.BS_PUSHBUTTON],
        [BUTTON,         'Close',               win32con.IDOK,        (167,184,62,14),csts | win32con.BS_DEFPUSHBUTTON],
    ]

    def __init__(self, mgr, do_train, do_filter, define_filter):
        self.mgr = mgr
        self.do_train = do_train
        self.do_filter = do_filter
        self.define_filter = define_filter

        self.checkbox_items = [
            (IDC_BUT_FILTER_ENABLE, "self.mgr.config.filter.enabled"),
            (IDC_BUT_TRAIN_FROM_SPAM_FOLDER,
                     "self.mgr.config.training.train_recovered_spam"),
            (IDC_BUT_TRAIN_TO_SPAM_FOLDER,
                     "self.mgr.config.training.train_manual_spam"),
        ]

        dialog.Dialog.__init__(self, self.dt)

    def OnInitDialog(self):
        from spambayes.Version import get_version_string
        version_key = "Full Description"
        if hasattr(sys, "frozen"):
            version_key += " Binary"
        self.SetDlgItemText(IDC_VERSION, get_version_string("Outlook", version_key))
        
##        self.HookCommand(self.OnButAdvanced, IDC_BUT_ADVANCED)
        self.HookCommand(self.OnButAbout, IDC_BUT_ABOUT)
        self.HookCommand(self.OnButDoSomething, IDC_BUT_TRAIN_NOW)
        self.HookCommand(self.OnButDoSomething, IDC_BUT_FILTER_DEFINE)
        self.HookCommand(self.OnButDoSomething, IDC_BUT_FILTER_NOW)

        for cid, expr in self.checkbox_items:
            self.HookCommand(self.OnButCheckbox, cid)
            val = eval(expr)
            self.GetDlgItem(cid).SetCheck(val)
        self.UpdateControlStatus()
        return dialog.Dialog.OnInitDialog(self)

    def UpdateControlStatus(self):
        nspam = self.mgr.bayes.nspam
        nham = self.mgr.bayes.nham
        config = self.mgr.config.filter
        if nspam > 0 and nham > 0:
            db_status = "Database has %d good and %d spam" % (nham, nspam)
        else:
            db_status = "Database has no training information"
        self.SetDlgItemText(IDC_TRAINING_STATUS, db_status)
        # For the sake of getting reasonable results, let's insist
        # on 5 spam and 5 ham messages before we can allow filtering
        # to be enabled.
        min_ham = 5
        min_spam = 5
        ok_to_enable = operator.truth(config.watch_folder_ids)
        if not ok_to_enable:
            filter_status = "You must define folders to watch "\
                            "for new messages"
        if ok_to_enable:
            ok_to_enable = nspam >= min_spam and nham >= min_ham
            if not ok_to_enable:
                filter_status = "There must be %d good and %d spam  " \
                                "messages\ntrained before filtering " \
                                "can be enabled" \
                                % (min_ham, min_spam)
        if ok_to_enable:
            self.GetDlgItem(IDC_BUT_FILTER_ENABLE).SetCheck(config.enabled)
            ok_to_enable = operator.truth(config.spam_folder_id)
            if ok_to_enable:
                certain_spam_name = self.mgr.FormatFolderNames(
                                        [config.spam_folder_id], False)
                if config.unsure_folder_id:
                    unsure_name = self.mgr.FormatFolderNames(
                                        [config.unsure_folder_id], False)
                    unsure_text = "unsure managed in '%s'" % (unsure_name,)
                else:
                    unsure_text = "unsure messages untouched"
            else:
                filter_status = "You must define the folder to " \
                                "receive your certain spam"

            # whew
            if ok_to_enable:
                watch_names = self.mgr.FormatFolderNames(
                        config.watch_folder_ids, config.watch_include_sub)
                filter_status = "Watching '%s'. Spam managed in '%s', %s" \
                                % (watch_names,
                                   certain_spam_name,
                                   unsure_text)

        self.GetDlgItem(IDC_BUT_FILTER_ENABLE).EnableWindow(ok_to_enable)
        enabled = config.enabled
        self.GetDlgItem(IDC_BUT_FILTER_ENABLE).SetCheck(
                                                ok_to_enable and enabled)
        self.SetDlgItemText(IDC_FILTER_STATUS, filter_status)

    def OnButAbout(self, id, code):
        if code == win32con.BN_CLICKED:
            if hasattr(sys, "frozen"):
                # Same directory as to the executable.
                fname = os.path.join(os.path.dirname(sys.argv[0]),
                                     "about.html")
            else:
                # In the parent (ie, main Outlook2000) dir
                fname = os.path.join(os.path.dirname(__file__),
                                     os.pardir,
                                     "about.html")
            fname = os.path.abspath(fname)
            if os.path.isfile(fname):
                win32ui.DoWaitCursor(1)
                os.startfile(fname)
                win32ui.DoWaitCursor(0)
            else:
                self.MessageBox("Can't find about.html")

    def OnButDoSomething(self, id, code):
        if code == win32con.BN_CLICKED:
            if id == IDC_BUT_TRAIN_NOW:
                doer = self.do_train
            elif id == IDC_BUT_FILTER_NOW:
                doer = self.do_filter
            elif id == IDC_BUT_FILTER_DEFINE:
                doer = self.define_filter
            else:
                raise RuntimeError, "Unknown button ID!"
            doer(self)
            self.UpdateControlStatus()

    def OnButCheckbox(self, id, code):
        if code == win32con.BN_CLICKED:
            for look_id, expr in self.checkbox_items:
                if id == look_id:
                    break
            else:
                raise RuntimeError, "bad control ID '%d'" % (id,)
            item = self.GetDlgItem(id)
            exec expr + " = " + str(item.GetCheck()==1)

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
