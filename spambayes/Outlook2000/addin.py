# Mark's Outlook addin


import warnings
warnings.filterwarnings("ignore", category=FutureWarning, append=1) # sick off the new hex() warnings!

import sys

from win32com import universal
from win32com.server.exception import COMException
from win32com.client import gencache, DispatchWithEvents, Dispatch
import winerror
import win32api
import pythoncom
from win32com.client import constants

# If we are not running in a console, redirect all print statements to the
# win32traceutil collector.
# You can view output either from Pythonwin's "Tools->Trace Collector Debugging Tool",
# or simply run "win32traceutil.py" from a command prompt.
try:
    win32api.GetConsoleTitle()
except win32api.error:
    # No console - redirect
    import win32traceutil
    print "Outlook Spam Addin module loading"


# A lovely big block that attempts to catch the most common errors - COM objects not installed.
try:
    # Support for COM objects we use.
    gencache.EnsureModule('{00062FFF-0000-0000-C000-000000000046}', 0, 9, 0, bForDemand=True) # Outlook 9
    gencache.EnsureModule('{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}', 0, 2, 1, bForDemand=True) # Office 9
    gencache.EnsureModule('{3FA7DEA7-6438-101B-ACC1-00AA00423326}', 0, 1, 21, bForDemand = True) # CDO

    # The TLB defiining the interfaces we implement
    universal.RegisterInterfaces('{AC0714F2-3D04-11D1-AE7D-00A0C90F26F4}', 0, 1, 0, ["_IDTExtensibility2"])
except pythoncom.com_error, (hr, msg, exc, arg):
    if __name__ != '__main__':
        # Error when not running as a script - eeek - just let it go.
        raise
    try:
        pythoncom.MakeIID("MAPI.Session")
        have_cdo = True
    except pythoncom.com_error:
        have_cdo = False
    print "This Addin requires that Outlook 2000 with CDO be installed on this machine."
    print
    if have_cdo:
        print "However, these appear to be installed.  Error details:"
        print "COM Error 0x%x (%s)" % (hr, msg)
        if exc:
            print "Exception: %s" % (exc)
        print 
        print "Sorry, I can't be more help, but I can't continue while I have this error."
    else:
        print "CDO is not currently installed.  To install CDO, you must locate the"
        print "media from which you installed Outlook (such as Office 2000 CD or "
        print "sharepoint), re-run setup, select Outlook, enable CDO."
        print
        print "Please install CDO then attempt this registration again."
    sys.exit(1)

# Whew - we seem to have all the COM support we need - let's rock!

class ButtonEvent:
    def Init(self, handler, args = ()):
        self.handler = handler
        self.args = args

    def OnClick(self, button, cancel):
        self.handler(*self.args)

class FolderItemsEvent:
    def __del__(self):
        print "Event dieing"

    def Init(self, target, application, manager):
        self.application = application
        self.manager = manager
        self.target = target

    def OnItemAdd(self, item):
        if self.manager.config.filter.enabled:
            mapi_message = self.manager.mapi.GetMessage(item.EntryID)
            import filter
            num_rules = filter.filter_message(mapi_message, self.manager)
            print "%d Spam rules fired for message '%s'" % (num_rules, item.Subject.encode("ascii", "replace"))
        else:
            print "Spam filtering is disabled - ignoring new message"


class OutlookAddin:
    _com_interfaces_ = ['_IDTExtensibility2']
    _public_methods_ = []
    _reg_clsctx_ = pythoncom.CLSCTX_INPROC_SERVER
    _reg_clsid_ = "{3556EDEE-FC91-4cf2-A0E4-7489747BAB10}"
    _reg_progid_ = "SpamBayes.OutlookAddin"
    _reg_policy_spec_ = "win32com.server.policy.EventHandlerPolicy"

    def __init__(self):
        self.folder_hooks = {}
        self.application = None

    def OnConnection(self, application, connectMode, addin, custom):
        print "SpamAddin - Connecting to Outlook"
        self.application = application

        # Create our bayes manager
        import manager
        self.manager = manager.GetManager()
        assert self.manager.addin is None, "Should not already have an addin"
        self.manager.addin = self
        
        # ActiveExplorer may be none when started without a UI (eg, WinCE synchronisation)
        activeExplorer = application.ActiveExplorer()
        if activeExplorer is not None:
            bars = activeExplorer.CommandBars
            toolbar = bars.Item("Standard")
            item = toolbar.Controls.Add(Type=constants.msoControlButton, Temporary=True)
            # Hook events for the item
            item = self.toolbarButton = DispatchWithEvents(item, ButtonEvent)
            item.Init(manager.ShowManager, (self.manager,))
            item.Caption="Anti-Spam"
            item.TooltipText = "Define anti-spam filters"
            item.Enabled = True

        self.FiltersChanged()

    def FiltersChanged(self):
        # Create a notification hook for all folders we filter.
        self.UpdateFolderHooks()
        
    def UpdateFolderHooks(self):
        new_hooks = {}
        for mapi_folder in self.manager.BuildFolderList(self.manager.config.filter.folder_ids, self.manager.config.filter.include_sub):
            eid = mapi_folder.ID
            existing = self.folder_hooks.get(eid)
            if existing is None:
                folder = self.application.GetNamespace("MAPI").GetFolderFromID(eid)
                try:
                    new_hook = DispatchWithEvents(folder.Items, FolderItemsEvent)
                except ValueError:
                    print "WARNING: Folder '%s' can not hook events" % (folder.Name,)
                    new_hook = None
                if new_hook is not None:
                    new_hook.Init(folder, self.application, self.manager)
                    new_hooks[eid] = new_hook
                    print "AntiSpam: Watching for new messages in folder", folder.Name
            else:
                new_hooks[eid] = existing
        for k in self.folder_hooks.keys():
            if not new_hooks.has_key(k):
                self.folder_hooks[k]._obj_.close()
        self.folder_hooks = new_hooks
            
    def OnDisconnection(self, mode, custom):
        print "SpamAddin - Disconnecting from Outlook"
        self.folder_hooks = None
        self.application = None
        if self.manager is not None:
            self.manager.Save()
            self.manager.Close()
            self.manager = None

    def OnAddInsUpdate(self, custom):
        print "SpamAddin - OnAddInsUpdate", custom
    def OnStartupComplete(self, custom):
        print "SpamAddin - OnStartupComplete", custom
    def OnBeginShutdown(self, custom):
        print "SpamAddin - OnBeginShutdown", custom

def RegisterAddin(klass):
    import _winreg
    key = _winreg.CreateKey(_winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Office\\Outlook\\Addins")
    subkey = _winreg.CreateKey(key, klass._reg_progid_)
    _winreg.SetValueEx(subkey, "CommandLineSafe", 0, _winreg.REG_DWORD, 0)
    _winreg.SetValueEx(subkey, "LoadBehavior", 0, _winreg.REG_DWORD, 3)
    _winreg.SetValueEx(subkey, "Description", 0, _winreg.REG_SZ, klass._reg_progid_)
    _winreg.SetValueEx(subkey, "FriendlyName", 0, _winreg.REG_SZ, klass._reg_progid_)

def UnregisterAddin(klass):
    import _winreg
    try:
        _winreg.DeleteKey(_winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Office\\Outlook\\Addins\\" + klass._reg_progid_)
    except WindowsError:
        pass

if __name__ == '__main__':
    import win32com.server.register
    win32com.server.register.UseCommandLine(OutlookAddin)
    if "--unregister" in sys.argv:
        UnregisterAddin(OutlookAddin)
    else:
        RegisterAddin(OutlookAddin)
