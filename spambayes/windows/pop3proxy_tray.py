#!/usr/bin/env python

"""A script to provide an icon in the Windows taskbar tray to control the
POP3 proxy.
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>, Adam Walker"
__credits__ = "Mark Hammond, all the Spambayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

# Heavily based on the win32gui_taskbar.py demo from Mark Hammond's
# win32 extensions.

import os
import sys
import webbrowser
import thread

import win32con
from win32api import *
from win32gui import *
from win32api import error as win32api_error

# If we are not running in a console, redirect all print statements to the
# win32traceutil collector.
# You can view output either from Pythonwin's "Tools->Trace Collector Debugging Tool",
# or simply run "win32traceutil.py" from a command prompt.
try:
    GetConsoleTitle()
except win32api_error:
    # No console - if we are running from Python sources,
    # redirect to win32traceutil, but if running from a binary
    # install, redirect to a log file.
    # Want to move to logging module later, so for now, we
    # hack together a simple logging strategy.
    if hasattr(sys, "frozen"):
        temp_dir = GetTempPath()
        for i in range(3,0,-1):
            try: os.unlink(os.path.join(temp_dir, "SpamBayesServer%d.log" % (i+1)))
            except os.error: pass
            try:
                os.rename(
                    os.path.join(temp_dir, "SpamBayesServer%d.log" % i),
                    os.path.join(temp_dir, "SpamBayesServer%d.log" % (i+1))
                    )
            except os.error: pass
        # Open this log, as unbuffered so crashes still get written.
        sys.stdout = open(os.path.join(temp_dir,"SpamBayesServer1.log"), "wt", 0)
        sys.stderr = sys.stdout
    else:
        import win32traceutil

# Work out our "application directory", which is
# the directory of our main .py/.exe file we
# are running from.
try:
    if hasattr(sys, "frozen"):
        if sys.frozen == "dll":
            # Don't think we will ever run as a .DLL, but...
            this_filename = win32api.GetModuleFileName(sys.frozendllhandle)
        else:
            this_filename = os.path.abspath(sys.argv[0])
    else:
        this_filename = os.path.abspath(__file__)
except NameError: # no __file__
    this_filename = os.path.abspath(sys.argv[0])

this_dir = os.path.dirname(this_filename)
if not hasattr(sys, "frozen"):
    # Allow for those without SpamBayes on the PYTHONPATH
    sys.path.insert(-1, this_dir)
    sys.path.insert(-1, os.path.dirname(this_dir))
    sys.path.insert(-1, os.path.join(os.path.dirname(this_dir),"scripts"))

import sb_server
from spambayes import Dibbler
from spambayes.Options import options

WM_TASKBAR_NOTIFY = win32con.WM_USER + 20

START_STOP_ID = 1024

class MainWindow(object):
    def __init__(self):
        # The ordering here is important - it is the order that they will
        # appear in the menu.  As dicts don't have an order, this means
        # that the order is controlled by the id.  Any items where the
        # function is None will appear as separators.
        self.control_functions = {START_STOP_ID : ("Stop SpamBayes", self.StartStop),
                                  1025 : ("-", None),
                                  1026 : ("View information ...", self.OpenInterface),
                                  1027 : ("Configure ...", self.OpenConfig),
                                  1028 : ("-", None),
                                  1029 : ("Exit SpamBayes", self.OnExit),
                                  }
        message_map = {
            win32con.WM_DESTROY: self.OnDestroy,
            win32con.WM_COMMAND: self.OnCommand,
            WM_TASKBAR_NOTIFY : self.OnTaskbarNotify,
        }

        # Create the Window.
        hinst = GetModuleHandle(None)
        # This will replaced with a real configure dialog later
        # This is mainly to work around not being able to register a window
        # class with Python 2.3
        dialogTemplate = [['SpamBayes', (14, 10, 246, 187),
                           -1865809852 & ~win32con.WS_VISIBLE, None,
                           (8, 'Tahoma')],]
        self.hwnd = CreateDialogIndirect(hinst, dialogTemplate, 0,
                                         message_map)

        # Get the custom icon
        startedIconPathName = "%s\\..\\windows\\resources\\sb-started.ico" % \
                       (os.path.dirname(sb_server.__file__),)
        stoppedIconPathName = "%s\\..\\windows\\resources\\sb-stopped.ico" % \
                       (os.path.dirname(sb_server.__file__),)
        # When 1.0a6 is released, the above line will need to change to:
##        iconPathName = "%s\\..\\windows\\resources\\sbicon.ico" % \
##                       (os.path.dirname(sb_server.__file__),)
        if hasattr(sys, "frozen"):
            self.hstartedicon = self.hstoppedicon = None
            hexe = GetModuleHandle(None)
            icon_flags = win32con.LR_DEFAULTSIZE
            self.hstartedicon = LoadImage(hexe, 1000, win32con.IMAGE_ICON, 0,
                                          0, icon_flags)
            self.hstopped = LoadImage(hexe, 1010, win32con.IMAGE_ICON, 0,
                                          0, icon_flags)
        else:
            # If we have no icon we fail in all sorts of places - so may as
            # well make it here :)
            icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
            self.hstartedicon = LoadImage(hinst, startedIconPathName, win32con.IMAGE_ICON, 0,
                                          0, icon_flags)
            self.hstoppedicon = LoadImage(hinst, stoppedIconPathName, win32con.IMAGE_ICON, 0,
                                          0, icon_flags)

        flags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid = (self.hwnd, 0, flags, WM_TASKBAR_NOTIFY, self.hstartedicon, "SpamBayes")
        Shell_NotifyIcon(NIM_ADD, nid)
        self.started = False
        self.tip = None

        # Start up sb_server
        # XXX This needs to be finished off.
        # XXX This should determine if we are using the service, and if so
        # XXX start that, and if not kick sb_server off in a separate thread.
        sb_server.prepare(state=sb_server.state)
        self.StartStop()

    def BuildToolTip(self):
        tip = None
        if self.started == True:
            #%i spam %i unsure %i session %i active
            tip = "SpamBayes %i spam %i ham %i unsure %i sessions %i active" %\
            (sb_server.state.numSpams, sb_server.state.numHams, sb_server.state.numUnsure,
             sb_server.state.totalSessions, sb_server.state.activeSessions)
        else:
            tip = "SpamBayes is not running"
        return tip
            

    def UpdateIcon(self, hicon=None):
        flags = NIF_TIP
        if hicon is not None:
            flags |= NIF_ICON
        else:
            hicon = 0
        self.tip = self.BuildToolTip()
        nid = (self.hwnd, 0, flags, WM_TASKBAR_NOTIFY, hicon, self.tip)
        Shell_NotifyIcon(NIM_MODIFY, nid)

    def OnDestroy(self, hwnd, msg, wparam, lparam):
        nid = (self.hwnd, 0)
        Shell_NotifyIcon(NIM_DELETE, nid)
        PostQuitMessage(0)

    def OnTaskbarNotify(self, hwnd, msg, wparam, lparam):
        if lparam==win32con.WM_MOUSEMOVE:
            if self.tip != self.BuildToolTip():
                self.UpdateIcon()
        if lparam==win32con.WM_LBUTTONUP:
            # We ignore left clicks
            pass
        elif lparam==win32con.WM_LBUTTONDBLCLK:
            # Default behaviour is to open up the web interface
            # XXX This should be set as the default (which then means bold
            # XXX text) through the win32 calls, but win32all doesn't
            # XXX include SetDefault(), which it needs to...
            self.OpenInterface()
        elif lparam==win32con.WM_RBUTTONUP:
            menu = CreatePopupMenu()
            ids = self.control_functions.keys()
            ids.sort()
            for id in ids:
                (wording, function) = self.control_functions[id]
                if function:
                    AppendMenu( menu, win32con.MF_STRING, id, wording)
                else:
                    AppendMenu( menu, win32con.MF_SEPARATOR, id, wording)
            pos = GetCursorPos()
            SetForegroundWindow(self.hwnd)
            TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0,
                           self.hwnd, None)
            PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        return 1

    def OnCommand(self, hwnd, msg, wparam, lparam):
        id = LOWORD(wparam)
        try:
            unused, function = self.control_functions[id]
        except KeyError:
            print "Unknown command -", id
            return
        function()

    def OnExit(self):
        if self.started:
            sb_server.stop(sb_server.state)
            self.started = False
        DestroyWindow(self.hwnd)
        sys.exit()
        
    def StartProxyThread(self):
        args = (sb_server.state,)
        thread.start_new_thread(sb_server.start, args)
        self.started = True

    def StartStop(self):
        # XXX This needs to be finished off.
        # XXX This should determine if we are using the service, and if so
        # XXX start/stop that, and if not kick sb_server off in a separate
        # XXX thread, or stop the thread that was started.
        if self.started:
            sb_server.stop(sb_server.state)
            self.started = False
            self.control_functions[START_STOP_ID] = ("Start SpamBayes",
                                                     self.StartStop)
            self.UpdateIcon(self.hstoppedicon)
        else:
            self.StartProxyThread()
            self.control_functions[START_STOP_ID] = ("Stop SpamBayes",
                                                     self.StartStop)
            self.UpdateIcon(self.hstartedicon)

    def OpenInterface(self):
        webbrowser.open_new("http://localhost:%d/" % \
                            (options["html_ui", "port"],))

    def OpenConfig(self):		
        webbrowser.open_new("http://localhost:%d/config" % \
                            (options["html_ui", "port"],))

def main():
	w = MainWindow()
	PumpMessages()

if __name__=='__main__':
	main()
