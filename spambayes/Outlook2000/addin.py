# SpamBayes Outlook Addin

import sys
import warnings

if sys.version_info >= (2, 3):
    # sick off the new hex() warnings!
    warnings.filterwarnings("ignore", category=FutureWarning, append=1)

from win32com import universal
from win32com.server.exception import COMException
from win32com.client import gencache, DispatchWithEvents, Dispatch
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

    # The TLB defiining the interfaces we implement
    universal.RegisterInterfaces('{AC0714F2-3D04-11D1-AE7D-00A0C90F26F4}', 0, 1, 0, ["_IDTExtensibility2"])
except pythoncom.com_error, (hr, msg, exc, arg):
    if __name__ != '__main__':
        # Error when not running as a script - eeek - just let it go.
        raise
    print "This Addin requires that Outlook 2000 be installed on this machine."
    print
    print "This appears to not be installed due to the following error:"
    print "COM Error 0x%x (%s)" % (hr, msg)
    if exc:
        print "Exception: %s" % (exc)
    print "Sorry, I can't be more help, but I can't continue while I have this error."
    sys.exit(1)

# Something that should be in win32com in some form or another.
def CastToClone(ob, target):
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
        # (Fixed in win32all!)
        target_clsid = mod.VTablesNamesToIIDMap.get(target)
        if target_clsid is None:
            raise ValueError, "The interface name '%s' does not appear in the " \
                              "same library as object '%r'" % (target, ob)
        mod = gencache.GetModuleForCLSID(target_clsid)
        target_class = getattr(mod, target)
        # resolve coclass to interface
        target_class = getattr(target_class, "default_interface", target_class)
        return target_class(ob) # auto QI magic happens
    raise ValueError, "Don't know what to do with '%r'" % (ob,)
try:
    from win32com.client import CastTo
except ImportError: # appears in 151 and later.
    CastTo = CastToClone

# Whew - we seem to have all the COM support we need - let's rock!

# Button/Menu and other UI event handler classes
class ButtonEvent:
    def Init(self, handler, args = ()):
        self.handler = handler
        self.args = args

    def OnClick(self, button, cancel):
        self.handler(*self.args)

# Folder event handler classes
class _BaseItemsEvent:
    def Init(self, target, application, manager):
        self.application = application
        self.manager = manager
        self.target = target

class FolderItemsEvent(_BaseItemsEvent):
    def OnItemAdd(self, item):
        # Note:  There's no distinction made here between msgs that have
        # been received, and, e.g., msgs that were sent and moved from the
        # Sent Items folder.  It would be good not to train on the latter,
        # since it's simply not received email.  An article on the web said
        # the distinction can't be made with 100% certainty, but that a good
        # heuristic is to believe that a msg has been received iff at least
        # one of these properties has a sensible value:
        #     PR_RECEIVED_BY_EMAIL_ADDRESS
        #     PR_RECEIVED_BY_NAME
        #     PR_RECEIVED_BY_ENTRYID
        #     PR_TRANSPORT_MESSAGE_HEADERS
        msgstore_message = self.manager.message_store.GetMessage(item.EntryID)
        if msgstore_message.GetField(self.manager.config.field_score_name) is not None:
            # Already seem this message - user probably moving it back
            # after incorrect classification.
            # If enabled, re-train as Ham
            # otherwise just ignore.
            if self.manager.config.training.train_recovered_spam:
                subject = item.Subject.encode("mbcs", "replace")
                import train
                print "Training on message '%s' - " % subject,
                if train.train_message(msgstore_message, False, self.manager):
                    print "trained as good"
                else:
                    print "already was trained as good"
                assert train.been_trained_as_ham(msgstore_message, self.manager)
            return
        if self.manager.config.filter.enabled:
            import filter
            disposition = filter.filter_message(msgstore_message, self.manager)
            print "Message '%s' had a Spam classification of '%s'" \
                  % (item.Subject.encode("ascii", "replace"), disposition)
        else:
            print "Spam filtering is disabled - ignoring new message"

# Event fired when item moved into the Spam folder.
class SpamFolderItemsEvent(_BaseItemsEvent):
    def OnItemAdd(self, item):
        # Not sure what the best heuristics are here - for
        # now, we assume that if the calculated spam prob
        # was *not* certain-spam, or it is in the ham corpa,
        # then it should be trained as such.
        if not self.manager.config.training.train_manual_spam:
            return
        msgstore_message = self.manager.message_store.GetMessage(item.EntryID)
        prop = msgstore_message.GetField(self.manager.config.field_score_name)
        if prop is not None:
            import train
            trained_as_good = train.been_trained_as_ham(msgstore_message, self.manager)
            if self.manager.config.filter.spam_threshold > prop or \
               trained_as_good:
                subject = item.Subject.encode("mbcs", "replace")
                print "Training on message '%s' - " % subject,
                if train.train_message(msgstore_message, True, self.manager):
                    print "trained as spam"
                else:
                    # This shouldn't really happen, but strange shit does
                    # (and there are cases where it could given a big enough
                    # idiot at the other end of the mouse <wink>)
                    print "already was trained as spam"
                assert train.been_trained_as_spam(msgstore_message, self.manager)

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
    score, clues = mgr.score(msgstore_message, evidence=True, scale=False)
    new_msg = app.CreateItem(0)
    body = ["<h2>Spam Score: %g</h2><br>" % score]
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
    msg = msgstore_message.GetEmailPackageObject(strip_mime_headers=False)
    push(escape(msg.as_string(), True))
    push("</PRE>\n")
    body = ''.join(body)

    new_msg.Subject = "Spam Clues: " + item.Subject
    # Stupid outlook always switches to RTF :( Work-around
##    new_msg.Body = body
    new_msg.HTMLBody = "<HTML><BODY>" + body + "</BODY></HTML>"
    # Attach the source message to it
    new_msg.Attachments.Add(item, constants.olByValue,
                            DisplayName="Original Message")
    new_msg.Display()

# The outlook Plugin COM object itself.
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
        config = self.manager.config.filter
        new_hooks = {}
        new_hooks.update(
            self._HookFolderEvents(config.watch_folder_ids,
                                   config.watch_include_sub,
                                   FolderItemsEvent)
            )
        # For spam manually moved
        if config.spam_folder_id:
            new_hooks.update(
                self._HookFolderEvents([config.spam_folder_id],
                                       False,
                                       SpamFolderItemsEvent)
                )
        for k in self.folder_hooks.keys():
            if not new_hooks.has_key(k):
                self.folder_hooks[k]._obj_.close()
        self.folder_hooks = new_hooks
        
    def _HookFolderEvents(self, folder_ids, include_sub, HandlerClass):
        new_hooks = {}
        for msgstore_folder in self.manager.message_store.GetFolderGenerator(
                    folder_ids, include_sub):
            eid = msgstore_folder.GetOutlookEntryID()
            existing = self.folder_hooks.get(eid)
            if existing is None or existing.__class__ != HandlerClass:
                folder = self.application.Session.GetFolderFromID(eid)
                name = folder.Name.encode("mbcs", "replace")
                try:
                    new_hook = DispatchWithEvents(folder.Items, HandlerClass)
                except ValueError:
                    print "WARNING: Folder '%s' can not hook events" % (name,)
                    new_hook = None
                if new_hook is not None:
                    new_hook.Init(folder, self.application, self.manager)
                    new_hooks[eid] = new_hook
                    self.manager.EnsureOutlookFieldsForFolder(eid)
                    print "AntiSpam: Watching for new messages in folder", name
            else:
                new_hooks[eid] = existing
        return new_hooks

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
