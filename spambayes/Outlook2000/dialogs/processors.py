# Control Processors for our dialog.

# This module is part of the spambayes project, which is Copyright 2003
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

import win32gui, win32api, win32con
import commctrl
import struct, array
from dlgutils import *

# A generic set of "ControlProcessors".  A control processor by itself only
# does a few basic things.
class ControlProcessor:
    def __init__(self, window, control_ids):
        self.control_id = control_ids[0]
        self.other_ids = control_ids[1:]
        self.window = window
    def Init(self):
        pass
    def Done(self):
        pass
    def GetControl(self, control_id = None):
        control_id = control_id or self.control_id
        return win32gui.GetDlgItem(self.window.hwnd, control_id)
    def GetPopupHelpText(self, idFrom):
        return None
    def OnCommand(self, wparam, lparam):
        pass
    def OnNotify(self, nmhdr, wparam, lparam):
        pass
    def GetMessages(self):
        return []
    def OnMessage(self, msg, wparam, lparam):
        raise RuntimeError, "I don't hook any messages, so I shouldn't be called"
    def OnOptionChanged(self, option):
        pass

class ButtonProcessor(ControlProcessor):
    def OnCommand(self, wparam, lparam):
        code = win32api.HIWORD(wparam)
        id = win32api.LOWORD(wparam)
        if code == win32con.BN_CLICKED:
            self.OnClicked(id)

class CloseButtonProcessor(ButtonProcessor):
    def OnClicked(self, id):
        print "clicked"
        win32gui.SendMessage(self.window.hwnd, win32con.WM_CLOSE, 0, 0)
    def GetPopupHelpText(self, ctrlid):
        return "Closes this dialog"

class CommandButtonProcessor(ButtonProcessor):
    def __init__(self, window, control_ids, func, args):
        assert len(control_ids)==1
        self.func = func
        self.args = args
        ControlProcessor.__init__(self, window, control_ids)

    def OnClicked(self, id):
        # Bit of a hack - always pass the manager as the first arg.
        args = (self.window.manager,) + self.args
        self.func(*args)
    
    def GetPopupHelpText(self, ctrlid):
        assert ctrlid == self.control_id
        return " ".join(self.func.__doc__.split())
