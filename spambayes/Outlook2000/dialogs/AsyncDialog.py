# Base class for an "async" dialog.
from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api


IDC_START = 1100
IDC_PROGRESS = 1101
IDC_PROGRESS_TEXT = 1102

def MAKELPARAM(low, high):
    return ((0x0000FFFF & high) << 16) | (0x0000FFFF & low)

MYWM_SETSTATUS = win32con.WM_USER+11
MYWM_SETWARNING = win32con.WM_USER+12
MYWM_SETERROR = win32con.WM_USER+13
MYWM_FINISHED = win32con.WM_USER+14

# This is called from another thread - hence we need to jump through hoops!
class _Progress:
    def __init__(self, dlg):
        self.hprogress = dlg.GetDlgItem(IDC_PROGRESS).GetSafeHwnd()
        self.hdlg = dlg.GetSafeHwnd()
        self.dlg = dlg
        self.stopping = False
    def set_max_ticks(self, m):
        win32api.PostMessage(self.hprogress, commctrl.PBM_SETRANGE, 0, MAKELPARAM(0,m))
        win32api.PostMessage(self.hprogress, commctrl.PBM_SETSTEP, 1, 0)
        win32api.PostMessage(self.hprogress, commctrl.PBM_SETPOS, 0, 0)
    def tick(self):
        win32api.PostMessage(self.hprogress, commctrl.PBM_STEPIT, 0, 0)
        #self.p.StepIt()
    def set_status(self, text):
        self.dlg.progress_status = text
        win32api.PostMessage(self.hdlg, MYWM_SETSTATUS)
    def warning(self, text):
        self.dlg.progress_warning = text
        win32api.PostMessage(self.hdlg, MYWM_SETWARNING)
    def error(self, text):
        self.dlg.progress_error = text
        win32api.PostMessage(self.hdlg, MYWM_SETERROR)
    def request_stop(self):
        self.stopping = True
    def stop_requested(self):
        return self.stopping


class AsyncDialogBase(dialog.Dialog):
    def __init__ (self, dt):
        dialog.Dialog.__init__ (self, dt)
        self.progress_status = ""
        self.progress_error = ""
        self.progress_warning = ""
        self.running = False

    def OnInitDialog(self):
        self.GetDlgItem(IDC_PROGRESS).ShowWindow(win32con.SW_HIDE)
        self.HookMessage(self.OnProgressStatus, MYWM_SETSTATUS)
        self.HookMessage(self.OnProgressError, MYWM_SETERROR)
        self.HookMessage(self.OnProgressWarning, MYWM_SETWARNING)
        self.HookMessage(self.OnFinished, MYWM_FINISHED)
        self.HookCommand(self.OnStart, IDC_START)
        return dialog.Dialog.OnInitDialog (self)

    def OnFinished(self, msg):
        self.seen_finished = True
        wasCancelled = msg[2]
        for id in self.disable_while_running_ids:
            self.GetDlgItem(id).EnableWindow(1)

        self.SetDlgItemText(IDC_START, self.process_start_text)
        self.GetDlgItem(IDC_PROGRESS).ShowWindow(win32con.SW_HIDE)
        if wasCancelled:
            self.SetDlgItemText(IDC_PROGRESS_TEXT, "Cancelled")

    def OnProgressStatus(self, msg):
        self.SetDlgItemText(IDC_PROGRESS_TEXT, self.progress_status)

    def OnProgressError(self, msg):
        self.SetDlgItemText(IDC_PROGRESS_TEXT, self.progress_error)
        self.MessageBox(self.progress_error)
        if not self.running and not self.seen_finished:
            self.OnFinished( (0,0,0) )

    def OnProgressWarning(self, msg):
        pass

    def OnStart(self, id, code):
        if id == IDC_START:
            self.StartProcess()

    def StartProcess(self):
        if self.running:
            self.progress.request_stop()
        else:
            for id in self.disable_while_running_ids:
                self.GetDlgItem(id).EnableWindow(0)
            self.SetDlgItemText(IDC_START, self.process_stop_text)
            self.SetDlgItemText(IDC_PROGRESS_TEXT, "")
            self.GetDlgItem(IDC_PROGRESS).ShowWindow(win32con.SW_SHOW)
            # Local function for the thread target that notifies us when finished.
            def thread_target(h, progress):
                try:
                    self.progress = progress
                    self.seen_finished = False
                    self.running = True
                    self._DoProcess()
                finally:
                    win32api.PostMessage(h, MYWM_FINISHED, self.progress.stop_requested())
                    self.running = False
                    self.progress = None

            # back to the program :)
            import threading
            t = threading.Thread(target=thread_target, args =(self.GetSafeHwnd(), _Progress(self)))
            t.start()
