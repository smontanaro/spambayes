# SpamBayes Outlook Addin

import sys
import warnings

if sys.version_info >= (2, 3):
    # sick off the new hex() warnings!
    warnings.filterwarnings("ignore", category=FutureWarning, append=1)

from win32com import universal
from win32com.server.exception import COMException
from win32com.client import gencache, DispatchWithEvents, Dispatch
import winerror
import win32api
import pythoncom
from win32com.client import constants
import win32ui

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

# Something that should be in win32com in some form or another.
def CastTo(ob, target):
    """'Cast' a COM object to another type"""
    # todo - should support target being an IID
    if hasattr(target, "index"): # string like
    # for now, we assume makepy for this to work.
        if not ob.__class__.__dict__.has_key("CLSID"):
            # Eeek - no makepy support - try and build it.
            ob = gencache.EnsureDispatch(ob)
        if not ob.__class__.__dict__.has_key("CLSID"):
            raise ValueError, "Must be a makepy-able object for this to work"
        clsid = ob.CLSID
        # Lots of hoops to support "demand-build" - ie, generating
        # code for an interface first time it is used.  We assume the
        # interface name exists in the same library as the object.
        # This is generally the case - only referenced typelibs may be
        # a problem, and we can handle that later.  Maybe <wink>
        # So get the generated module for the library itself, then
        # find the interface CLSID there.
        mod = gencache.GetModuleForCLSID(clsid)
        # Get the 'root' module.
        mod = gencache.GetModuleForTypelib(mod.CLSID, mod.LCID,
                                           mod.MajorVersion, mod.MinorVersion)
        # Find the CLSID of the target
        # XXX - should not be looking in VTables..., but no general map currently exists
        target_clsid = mod.VTablesNamesToIIDMap.get(target)
        if target_clsid is None:
            raise ValueError, "The interface name '%s' does not appear in the " \
                              "same library as object '%r'" % (target, ob)
        mod = gencache.GetModuleForCLSID(target_clsid)
        target_class = getattr(mod, target)
        # resolve coclass to interface
        target_class = getattr(target_class, "default_interface", target_class)
        return target_class(ob) # auto QI magic happens

# Whew - we seem to have all the COM support we need - let's rock!

class ButtonEvent:
    def Init(self, handler, args = ()):
        self.handler = handler
        self.args = args

    def OnClick(self, button, cancel):
        self.handler(*self.args)

class FolderItemsEvent:
    def Init(self, target, application, manager):
        self.application = application
        self.manager = manager
        self.target = target

    def OnItemAdd(self, item):
        if self.manager.config.filter.enabled:
            msgstore_message = self.manager.message_store.GetMessage(item.EntryID)
            import filter
            num_rules = filter.filter_message(msgstore_message, self.manager)
            print "%d Spam rules fired for message '%s'" \
                  % (num_rules, item.Subject.encode("ascii", "replace"))
        else:
            print "Spam filtering is disabled - ignoring new message"

def ShowClues(mgr, app):
    from cgi import escape

    sel = app.ActiveExplorer().Selection
    if sel.Count == 0:
        win32ui.MessageBox("No items are selected", "No selection")
        return
    if sel.Count > 1:
        win32ui.MessageBox("Please select a single item", "Large selection")
        return

    item = sel.Item(1)
    if item.Class != constants.olMail:
        win32ui.MessageBox("This function can only be performed on mail items",
                           "Not a mail message")
        return

    msgstore_message = mgr.message_store.GetMessage(item.EntryID)
    prob, clues = mgr.score(msgstore_message, evidence=True)
    new_msg = app.CreateItem(0)
    body = ["<h2>Spam Score: %g</h2><br>" % prob]
    push = body.append
    # Format the clues.
    push("<PRE>\n")
    for word, prob in clues:
        word = repr(word)
        push(escape(word) + ' ' * (30 - len(word)))
        push(' %g\n' % prob)
    push("</PRE>\n")
    # Now the raw text of the message, as best we can
    push("<h2>Message Stream:</h2><br>")
    push("<PRE>\n")
    txt = msgstore_message.GetEmailPackageObject().as_string()
    push(escape(txt, True))
    push("</PRE>\n")
    body = ''.join(body)

    new_msg.Subject = "Spam Clues: " + item.Subject
    # Stupid outlook always switches to RTF :( Work-around
##    new_msg.Body = body
    new_msg.HTMLBody = "<HTML><BODY>" + body + "</BODY></HTML>"
    # Attach the source message to it
    new_msg.Attachments.Add(item, constants.olByValue, DisplayName="Original Message")
    new_msg.Display()

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
        self.buttons = []

    def OnConnection(self, application, connectMode, addin, custom):
        print "SpamAddin - Connecting to Outlook"
        self.application = application

        # Create our bayes manager
        import manager
        self.manager = manager.GetManager(application)
        assert self.manager.addin is None, "Should not already have an addin"
        self.manager.addin = self

        # ActiveExplorer may be none when started without a UI (eg, WinCE synchronisation)
        activeExplorer = application.ActiveExplorer()
        if activeExplorer is not None:
            bars = activeExplorer.CommandBars
            toolbar = bars.Item("Standard")
            # Add a pop-up menu to the toolbar
            popup = toolbar.Controls.Add(Type=constants.msoControlPopup, Temporary=True)
            popup.Caption="Anti-Spam"
            popup.TooltipText = "Anti-Spam filters and functions"
            popup.Enabled = True
            # Convert from "CommandBarItem" to derived "CommandBarPopup"
            # Not sure if we should be able to work this out ourselves, but no
            # introspection I tried seemed to indicate we can.  VB does it via
            # strongly-typed declarations.
            popup = CastTo(popup, "CommandBarPopup")
            # And add our children.
            self._AddPopup(popup, ShowClues, (self.manager, application),
                           Caption="Show spam clues for current message",
                           Enabled=True)
            self._AddPopup(popup, manager.ShowManager, (self.manager,),
                           Caption="Anti-Spam Manager...",
                           TooltipText = "Show the Anti-Spam manager dialog.",
                           Enabled = True)

        self.FiltersChanged()

    def _AddPopup(self, parent, target, target_args, **item_attrs):
        item = parent.Controls.Add(Type=constants.msoControlButton, Temporary=True)
        # Hook events for the item
        item = DispatchWithEvents(item, ButtonEvent)
        item.Init(target, target_args)
        for attr, val in item_attrs.items():
            setattr(item, attr, val)
        self.buttons.append(item)

    def FiltersChanged(self):
        # Create a notification hook for all folders we filter.
        self.UpdateFolderHooks()

    def UpdateFolderHooks(self):
        new_hooks = {}
        for msgstore_folder in self.manager.message_store.GetFolderGenerator(
                    self.manager.config.filter.folder_ids,
                    self.manager.config.filter.include_sub):
            eid = msgstore_folder.GetOutlookEntryID()
            existing = self.folder_hooks.get(eid)
            if existing is None:
                folder = self.application.Session.GetFolderFromID(eid)
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
        self.buttons = None

        print "Addin terminating: %d COM client and %d COM servers exist." \
              % (pythoncom._GetInterfaceCount(), pythoncom._GetGatewayCount())
        try:
            # will be available if "python_d addin.py" is used to
            # register the addin.
            total_refs = sys.gettotalrefcount() # debug Python builds only
            print "%d Python references exist" % (total_refs,)
        except AttributeError:
            pass

    def OnAddInsUpdate(self, custom):
        print "SpamAddin - OnAddInsUpdate", custom
    def OnStartupComplete(self, custom):
        print "SpamAddin - OnStartupComplete", custom
    def OnBeginShutdown(self, custom):
        print "SpamAddin - OnBeginShutdown", custom

def RegisterAddin(klass):
    import _winreg
    key = _winreg.CreateKey(_winreg.HKEY_CURRENT_USER,
                            "Software\\Microsoft\\Office\\Outlook\\Addins")
    subkey = _winreg.CreateKey(key, klass._reg_progid_)
    _winreg.SetValueEx(subkey, "CommandLineSafe", 0, _winreg.REG_DWORD, 0)
    _winreg.SetValueEx(subkey, "LoadBehavior", 0, _winreg.REG_DWORD, 3)
    _winreg.SetValueEx(subkey, "Description", 0, _winreg.REG_SZ, klass._reg_progid_)
    _winreg.SetValueEx(subkey, "FriendlyName", 0, _winreg.REG_SZ, klass._reg_progid_)

def UnregisterAddin(klass):
    import _winreg
    try:
        _winreg.DeleteKey(_winreg.HKEY_CURRENT_USER,
                          "Software\\Microsoft\\Office\\Outlook\\Addins\\" \
                          + klass._reg_progid_)
    except WindowsError:
        pass

if __name__ == '__main__':
    import win32com.server.register
    win32com.server.register.UseCommandLine(OutlookAddin)
    if "--unregister" in sys.argv:
        UnregisterAddin(OutlookAddin)
    else:
        RegisterAddin(OutlookAddin)
