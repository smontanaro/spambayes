#!/usr/bin/env python

"""A script to provide an icon in the Windows taskbar tray to control the
POP3 proxy.
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
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

import win32con
from win32api import *
from win32gui import *

# Allow for those without SpamBayes on the PYTHONPATH
sys.path.insert(-1, os.getcwd())
sys.path.insert(-1, os.path.dirname(os.getcwd()))

import pop3proxy
from spambayes import Dibbler
from spambayes.Options import options

class MainWindow(object):
    def __init__(self):
        # The ordering here is important - it is the order that they will
        # appear in the menu.  As dicts don't have an order, this means
        # that the order is controlled by the id.  Any items were the
        # function is None will appear as separators.
        self.control_functions = {1024 : ("Start SpamBayes", self.StartStop),
                                  1025 : ("-", None),
                                  1026 : ("View information ...", self.OpenInterface),
                                  1027 : ("Configure ...", self.OpenConfig),
                                  1028 : ("-", None),
                                  1029 : ("Exit SpamBayes", self.OnExit),
                                  }
        message_map = {
            win32con.WM_DESTROY: self.OnDestroy,
            win32con.WM_COMMAND: self.OnCommand,
            win32con.WM_USER+20 : self.OnTaskbarNotify,
        }

        # Register the Window class.
        wc = WNDCLASS()
        hinst = wc.hInstance = GetModuleHandle(None)
        wc.lpszClassName = "SpambayesTaskbar"
        wc.style = win32con.CS_VREDRAW | win32con.CS_HREDRAW;
        wc.hCursor = LoadCursor( 0, win32con.IDC_ARROW )
        wc.hbrBackground = win32con.COLOR_WINDOW
        wc.lpfnWndProc = message_map
        classAtom = RegisterClass(wc)

        # Create the Window.
        style = win32con.WS_OVERLAPPED | win32con.WS_SYSMENU
        self.hwnd = CreateWindow(classAtom, "SpamBayes", style,
                                 0, 0, win32con.CW_USEDEFAULT,
                                 win32con.CW_USEDEFAULT, 0, 0, hinst, None)
        UpdateWindow(self.hwnd)

        # Try and find a custom icon
        # XXX This needs to be done, but first someone needs to make a wee
        # XXX spambayes icon
        iconPathName = os.path.abspath(os.path.join( os.path.split(sys.executable)[0], "pyc.ico" ))
        if not os.path.isfile(iconPathName):
            # Look in the source tree.
            iconPathName = os.path.abspath(os.path.join( os.path.split(sys.executable)[0], "..\\PC\\pyc.ico" ))
        if os.path.isfile(iconPathName):
            icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
            hicon = LoadImage(hinst, iconPathName, win32con.IMAGE_ICON, 0, 0, icon_flags)
        else:
            print "Can't find a spambayes icon file - using default"
            hicon = LoadIcon(0, win32con.IDI_APPLICATION)

        flags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid = (self.hwnd, 0, flags, win32con.WM_USER+20, hicon, "SpamBayes")
        Shell_NotifyIcon(NIM_ADD, nid)

        # Start up pop3proxy
        # XXX This needs to be finished off.
        # XXX This should determine if we are using the service, and if so
        # XXX start that, and if not kick pop3proxy off in a separate thread.
        #pop3proxy.prepare(state=pop3proxy.state)
        #pop3proxy.start(pop3proxy.state)
        #self.started = True

    def OnDestroy(self, hwnd, msg, wparam, lparam):
		nid = (self.hwnd, 0)
		Shell_NotifyIcon(NIM_DELETE, nid)
		PostQuitMessage(0)

    def OnTaskbarNotify(self, hwnd, msg, wparam, lparam):
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
        function()

    def OnExit(self):
        DestroyWindow(self.hwnd)
        sys.exit()

    def StartStop(self):
        # XXX This needs to be finished off.
        # XXX This should determine if we are using the service, and if so
        # XXX start/stop that, and if not kick pop3proxy off in a separate
        # XXX thread, or stop the thread that was started.
        if self.started:
            pop3proxy.stop(pop3proxy.state)
            self.started = False
        else:
            pop3proxy.start(pop3proxy.state)
            self.started = True

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
