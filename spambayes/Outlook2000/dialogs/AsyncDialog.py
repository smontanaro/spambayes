# Base class for an "async" dialog.
from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


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
        self.total_control_ticks = 100
        self.current_stage = 0
        self.set_stages( (("", 1.0),) )

    def set_stages(self, stages):
        self.stages = []
        start_pos = 0.0
        for name, prop in stages:
            stage = name, start_pos, prop
            start_pos += prop
            self.stages.append(stage)
        assert abs(start_pos-1.0) < 0.001, (
               "Proportions must add to 1.0 (%r,%r,%r)" %
                   (start_pos, stages, start_pos-1.0))

    def _next_stage(self):
        if self.current_stage == 0:
            win32api.PostMessage(self.hprogress, commctrl.PBM_SETRANGE, 0, MAKELPARAM(0,self.total_control_ticks))
            win32api.PostMessage(self.hprogress, commctrl.PBM_SETSTEP, 1, 0)
            win32api.PostMessage(self.hprogress, commctrl.PBM_SETPOS, 0, 0)
            self.current_control_tick = 0

        self.current_stage += 1
        assert self.current_stage <= len(self.stages)

    def _get_current_stage(self):
        return self.stages[self.current_stage-1]

    def set_max_ticks(self, m):
        self._next_stage()
        self.current_stage_tick = 0
        self.current_stage_max = m

    def tick(self):
        self.current_stage_tick += 1
        # Calc how far through this stage.
        this_prop = float(self.current_stage_tick) / self.current_stage_max
        # How far through the total.
        stage_name, start, end = self._get_current_stage()
        # Calc the perc of the total control.
        stage_name, start, prop = self._get_current_stage()
        total_prop = start + this_prop * prop
        # How may ticks is this on the control
        control_tick = int(total_prop * self.total_control_ticks)
        #print "Tick", self.current_stage_tick, "is", this_prop, "through the stage,", total_prop, "through the total - ctrl tick is", control_tick
        while self.current_control_tick < control_tick:
            self.current_control_tick += 1
            #print "ticking control", self.current_control_tick
            win32api.PostMessage(self.hprogress, commctrl.PBM_STEPIT, 0, 0)

    def _get_stage_text(self, text):
        stage_name, start, end = self._get_current_stage()
        if stage_name:
            text = stage_name + ": " + text
        return text
    def set_status(self, text):
        self.dlg.progress_status = self._get_stage_text(text)
        win32api.PostMessage(self.hdlg, MYWM_SETSTATUS)
    def warning(self, text):
        self.dlg.progress_warning = self._get_stage_text(text)
        win32api.PostMessage(self.hdlg, MYWM_SETWARNING)
    def error(self, text):
        self.dlg.progress_error = self._get_stage_text(text)
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
            # Do anything likely to fail before we screw around with the
            # control states - this way the dialog doesn't look as 'dead'
            progress=_Progress(self)
            # Now screw around with the control states, restored when
            # the thread terminates.
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
                    # Drop my thread priority, so outlook can keep repainting
                    # and doing its stuff without getting stressed.
                    import win32process, win32api
                    THREAD_PRIORITY_BELOW_NORMAL=-1
                    win32process.SetThreadPriority(win32api.GetCurrentThread(), THREAD_PRIORITY_BELOW_NORMAL)
                    self._DoProcess()
                finally:
                    win32api.PostMessage(h, MYWM_FINISHED, self.progress.stop_requested())
                    self.running = False
                    self.progress = None

            # back to the program :)
            import threading
            t = threading.Thread(target=thread_target, args =(self.GetSafeHwnd(), progress))
            t.start()

if __name__=='__main__':
    # Test my "multi-stage" code
    class HackProgress(_Progress):
        def __init__(self): # dont use dlg
            self.hprogress = self.hdlg = 0
            self.dlg = None
            self.stopping = False
            self.total_control_ticks = 100
            self.current_stage = 0
            self.set_stages( (("", 1.0),) )

    p = HackProgress()
    p.set_max_ticks(10)
    for i in range(10):
        p.tick()

    p = HackProgress()
    stages = ("Stage 1", 0.2), ("Stage 2", 0.8)
    p.set_stages(stages)
    # Do stage 1
    p.set_max_ticks(10)
    for i in range(10):
        p.tick()
    # Do stage 2
    p.set_max_ticks(1000)
    for i in range(1000):
        p.tick()

