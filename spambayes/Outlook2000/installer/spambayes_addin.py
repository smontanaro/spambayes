import sys
import string
import os

import pythoncom
pythoncom.frozen = 1

inprocess = getattr(sys, 'frozen', None)

import addin
klasses = (addin.OutlookAddin,)

def DllRegisterServer():
    import win32com.server.register
    win32com.server.register.RegisterClasses(*klasses)
    addin.RegisterAddin(addin.OutlookAddin)
    return 0

def DllUnregisterServer():
    import win32com.server.register
    win32com.server.register.UnregisterClasses(*klasses)
    addin.UnregisterAddin(addin.OutlookAddin)
    return 0

if sys.frozen!="dll":
    import win32com.server.localserver
    for i in range(1, len(sys.argv)):
        arg = string.lower(sys.argv[i])
        if string.find(arg, "/reg") > -1 or string.find(arg, "--reg") > -1:
            DllRegisterServer()
            break

        if string.find(arg, "/unreg") > -1 or string.find(arg, "--unreg") > -1:
            DllUnregisterServer()
            break

        # MS seems to like /automate to run the class factories.
        if string.find(arg, "/automate") > -1:
            clsids = []
            for k in klasses:
                clsids.append(k._reg_clsid_)
            win32com.server.localserver.serve(clsids)
            break
    else:
        # You could do something else useful here.
        import win32api
        win32api.MessageBox(0, "This program hosts a COM Object and\r\nis started automatically", "COM Object")
