# SpamBayes Outlook Addin

import sys, os
import warnings

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


if sys.version_info >= (2, 3):
    # sick off the new hex() warnings!
    warnings.filterwarnings("ignore", category=FutureWarning, append=1)

from win32com import universal
from win32com.server.exception import COMException
from win32com.client import gencache, DispatchWithEvents, Dispatch
import win32api
import pythoncom
from win32com.client import constants, getevents
import win32ui

import win32gui, win32con, win32clipboard # for button images!

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


# Attempt to catch the most common errors - COM objects not installed.
try:
    # Generate support so we get complete support including events
    gencache.EnsureModule('{00062FFF-0000-0000-C000-000000000046}', 0, 9, 0, bForDemand=True) # Outlook 9
    gencache.EnsureModule('{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}', 0, 2, 1, bForDemand=True) # Office 9

    # Register what vtable based interfaces we need to implement.
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
    print "Sorry I can't be more help, but I can't continue while I have this error."
    sys.exit(1)

# A couple of functions that are in new win32all, but we dont want to
# force people to ugrade if we can avoid it.
# NOTE: Most docstrings and comments removed - see the win32all version
def CastToClone(ob, target):
    """'Cast' a COM object to another type"""
    if hasattr(target, "index"): # string like
    # for now, we assume makepy for this to work.
        if not ob.__class__.__dict__.has_key("CLSID"):
            ob = gencache.EnsureDispatch(ob)
        if not ob.__class__.__dict__.has_key("CLSID"):
            raise ValueError, "Must be a makepy-able object for this to work"
        clsid = ob.CLSID
        mod = gencache.GetModuleForCLSID(clsid)
        mod = gencache.GetModuleForTypelib(mod.CLSID, mod.LCID,
                                           mod.MajorVersion, mod.MinorVersion)
        # XXX - should not be looking in VTables..., but no general map currently exists
        # (Fixed in win32all!)
        target_clsid = mod.VTablesNamesToIIDMap.get(target)
        if target_clsid is None:
            raise ValueError, "The interface name '%s' does not appear in the " \
                              "same library as object '%r'" % (target, ob)
        mod = gencache.GetModuleForCLSID(target_clsid)
        target_class = getattr(mod, target)
        target_class = getattr(target_class, "default_interface", target_class)
        return target_class(ob) # auto QI magic happens
    raise ValueError, "Don't know what to do with '%r'" % (ob,)
try:
    from win32com.client import CastTo
except ImportError: # appears in 151 and later.
    CastTo = CastToClone

# Something else in later win32alls - like "DispatchWithEvents", but the
# returned object is not both the Dispatch *and* the event handler
def WithEventsClone(clsid, user_event_class):
    clsid = getattr(clsid, "_oleobj_", clsid)
    disp = Dispatch(clsid)
    if not disp.__dict__.get("CLSID"): # Eeek - no makepy support - try and build it.
        try:
            ti = disp._oleobj_.GetTypeInfo()
            disp_clsid = ti.GetTypeAttr()[0]
            tlb, index = ti.GetContainingTypeLib()
            tla = tlb.GetLibAttr()
            mod = gencache.EnsureModule(tla[0], tla[1], tla[3], tla[4])
            disp_class = gencache.GetClassForProgID(str(disp_clsid))
        except pythoncom.com_error:
            raise TypeError, "This COM object can not automate the makepy process - please run makepy manually for this object"
    else:
        disp_class = disp.__class__
    clsid = disp_class.CLSID
    import new
    events_class = getevents(clsid)
    if events_class is None:
        raise ValueError, "This COM object does not support events."
    result_class = new.classobj("COMEventClass", (events_class, user_event_class), {})
    instance = result_class(disp) # This only calls the first base class __init__.
    if hasattr(user_event_class, "__init__"):
        user_event_class.__init__(instance)
    return instance

try:
    from win32com.client import WithEvents
except ImportError: # appears in 151 and later.
    WithEvents = WithEventsClone

# Whew - we seem to have all the COM support we need - let's rock!

# Button/Menu and other UI event handler classes
class ButtonEvent:
    def Init(self, handler, args = ()):
        self.handler = handler
        self.args = args
    def Close(self):
        self.handler = self.args = None
    def OnClick(self, button, cancel):
        self.handler(*self.args)

# Folder event handler classes
class _BaseItemsEvent:
    def Init(self, target, application, manager):
        self.application = application
        self.manager = manager
        self.target = target
    def Close(self):
        self.application = self.manager = self.target = None

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
        msgstore_message = self.manager.message_store.GetMessage(item)
        if msgstore_message.GetField(self.manager.config.field_score_name) is not None:
            # Already seem this message - user probably moving it back
            # after incorrect classification.
            # If enabled, re-train as Ham
            # otherwise just ignore.
            if self.manager.config.training.train_recovered_spam:
                subject = item.Subject.encode("mbcs", "replace")
                import train
                print "Training on message '%s' - " % subject,
                if train.train_message(msgstore_message, False, self.manager, rescore = True):
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
        msgstore_message = self.manager.message_store.GetMessage(item)
        prop = msgstore_message.GetField(self.manager.config.field_score_name)
        if prop is not None:
            import train
            trained_as_good = train.been_trained_as_ham(msgstore_message, self.manager)
            if self.manager.config.filter.spam_threshold > prop or \
               trained_as_good:
                subject = item.Subject.encode("mbcs", "replace")
                print "Training on message '%s' - " % subject,
                if train.train_message(msgstore_message, True, self.manager, rescore = True):
                    print "trained as spam"
                else:
                    # This shouldn't really happen, but strange shit does
                    # (and there are cases where it could given a big enough
                    # idiot at the other end of the mouse <wink>)
                    print "already was trained as spam"
                assert train.been_trained_as_spam(msgstore_message, self.manager)

# Event function fired from the "Show Clues" UI items.
def ShowClues(mgr, app):
    from cgi import escape

    msgstore_message = mgr.addin.GetSelectedMessages(False)
    if msgstore_message is None:
        return
    item = msgstore_message.GetOutlookItem()
    score, clues = mgr.score(msgstore_message, evidence=True, scale=False)
    new_msg = app.CreateItem(0)
    # NOTE: Silly Outlook always switches the message editor back to RTF
    # once the Body property has been set.  Thus, there is no reasonable
    # way to get this as text only.  Next best then is to use HTML, 'cos at
    # least we know how to exploit it!
    body = ["<h2>Spam Score: %g</h2><br>" % score]
    push = body.append
    # Format the clues.
    push("<PRE>\n")
    push("word                                spamprob         #ham  #spam\n")
    format = " %-12g %8s %6s\n"
    c = mgr.GetClassifier()
    fetchword = c.wordinfo.get
    for word, prob in clues:
        record = fetchword(word)
        if record:
            nham = record.hamcount
            nspam = record.spamcount
        else:
            nham = nspam = "-"
        word = repr(word)
        push(escape(word) + " " * (35-len(word)))
        push(format % (prob, nham, nspam))
    push("</PRE>\n")

    # Now the raw text of the message, as best we can
    push("<h2>Message Stream:</h2><br>")
    push("<PRE>\n")
    msg = msgstore_message.GetEmailPackageObject()
    push(escape(msg.as_string(), True))
    push("</PRE>\n")
    body = ''.join(body)

    new_msg.Subject = "Spam Clues: " + item.Subject
    # As above, use HTMLBody else Outlook refuses to behave.
    new_msg.HTMLBody = "<HTML><BODY>" + body + "</BODY></HTML>"
    # Attach the source message to it
    new_msg.Attachments.Add(item, constants.olByValue,
                            DisplayName="Original Message")
    new_msg.Display()

# Events from our Explorer instance - currently used to enable/disable
# controls
class ExplorerEvent:
    def Init(self, manager, application, but_delete_as, but_recover_as):
        self.manager = manager
        self.application = application
        self.but_delete_as = but_delete_as
        self.but_recover_as = but_recover_as
    def Close(self):
        self.but_delete_as = self.but_recover_as = None
    def OnFolderSwitch(self):
        # Work out what folder we are in.
        explorer = self.application.ActiveExplorer()
        if explorer is None:
            print "** Folder Change, but don't have an explorer"
            return

        outlook_folder = explorer.CurrentFolder
        show_delete_as = True
        show_recover_as = False
        if outlook_folder is not None:
            mapi_folder = self.manager.message_store.GetFolder(outlook_folder)
            look_id = self.manager.config.filter.spam_folder_id
            if look_id:
                look_folder = self.manager.message_store.GetFolder(look_id)
                if mapi_folder == look_folder:
                    # This is the Spam folder - only show "recover"
                    show_recover_as = True
                    show_delete_as = False
            # Check if uncertain
            look_id = self.manager.config.filter.unsure_folder_id
            if look_id:
                look_folder = self.manager.message_store.GetFolder(look_id)
                if mapi_folder == look_folder:
                    show_recover_as = True
                    show_delete_as = True
        self.but_recover_as.Visible = show_recover_as
        self.but_delete_as.Visible = show_delete_as

# The "Delete As Spam" and "Recover Spam" button
# The event from Outlook's explorer that our folder has changed.
class ButtonDeleteAsEventBase:
    def Init(self, manager, application):
        # NOTE - keeping a reference to 'explorer' in this event
        # appears to cause an Outlook circular reference, and outlook
        # never terminates (it does close, but the process remains alive)
        # This is why we needed to use WithEvents, so the event class
        # itself doesnt keep such a reference (and we need to keep a ref
        # to the event class so it doesn't auto-disconnect!)
        self.manager = manager
        self.application = application

    def Close(self):
        self.manager = self.application = None

class ButtonDeleteAsSpamEvent(ButtonDeleteAsEventBase):
    def Init(self, manager, application):
        ButtonDeleteAsEventBase.Init(self, manager, application)
        image = "delete_as_spam.bmp"
        self.Caption = "Delete As Spam"
        self.TooltipText = \
                        "Move the selected message to the Spam folder,\n" \
                        "and train the system that this is Spam."
        SetButtonImage(self, image)

    def OnClick(self, button, cancel):
        msgstore = self.manager.message_store
        msgstore_messages = self.manager.addin.GetSelectedMessages(True)
        if not msgstore_messages:
            return
        # Delete this item as spam.
        spam_folder_id = self.manager.config.filter.spam_folder_id
        spam_folder = msgstore.GetFolder(spam_folder_id)
        if not spam_folder:
            win32ui.MessageBox("You must configure the Spam folder",
                               "Invalid Configuration")
            return
        import train
        for msgstore_message in msgstore_messages:
            # Must train before moving, else we lose the message!
            print "Training on message - ",
            if train.train_message(msgstore_message, True, self.manager, rescore = True):
                print "trained as spam"
            else:
                print "already was trained as spam"
            # Now move it.
            msgstore_message.MoveTo(spam_folder)

class ButtonRecoverFromSpamEvent(ButtonDeleteAsEventBase):
    def Init(self, manager, application):
        ButtonDeleteAsEventBase.Init(self, manager, application)
        image = "recover_ham.bmp"
        self.Caption = "Recover from Spam"
        self.TooltipText = \
                "Recovers the selected item back to the folder\n" \
                "it was filtered from (or to the Inbox if this\n" \
                "folder is not known), and trains the system that\n" \
                "this is a good message\n"
        SetButtonImage(self, image)

    def OnClick(self, button, cancel):
        msgstore = self.manager.message_store
        msgstore_messages = self.manager.addin.GetSelectedMessages(True)
        if not msgstore_messages:
            return
        # Recover to where they were moved from
        # Get the inbox as the default place to restore to
        # (incase we dont know (early code) or folder removed etc
        inbox_folder = msgstore.GetFolder(
                    self.application.Session.GetDefaultFolder(
                        constants.olFolderInbox))
        import train
        for msgstore_message in msgstore_messages:
            # Must train before moving, else we lose the message!
            print "Training on message - ",
            if train.train_message(msgstore_message, False, self.manager, rescore = True):
                print "trained as ham"
            else:
                print "already was trained as ham"
            # Now move it.
            # XXX - still don't write the source, so no point looking :(
            msgstore_message.MoveTo(inbox_folder)

# Helpers to work with images on buttons/toolbars.
def SetButtonImage(button, fname):
    # whew - http://support.microsoft.com/default.aspx?scid=KB;EN-US;q288771
    # shows how to make a transparent bmp.
    # Also note that the clipboard takes ownership of the handle -
    # this, we can not simply perform this load once and reuse the image.
    if not os.path.isabs(fname):
        fname = os.path.join( os.path.dirname(__file__), "images", fname)
    if not os.path.isfile(fname):
        print "WARNING - Trying to use image '%s', but it doesn't exist" % (fname,)
        return None
    handle = win32gui.LoadImage(0, fname, win32con.IMAGE_BITMAP, 0, 0, win32con.LR_DEFAULTSIZE | win32con.LR_LOADFROMFILE)
    win32clipboard.OpenClipboard()
    win32clipboard.SetClipboardData(win32con.CF_BITMAP, handle)
    win32clipboard.CloseClipboard()
    button.Style = constants.msoButtonIconAndCaption
    button.PasteFace()

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
        self.explorer_events = None

        # ActiveExplorer may be none when started without a UI (eg, WinCE synchronisation)
        activeExplorer = application.ActiveExplorer()
        if activeExplorer is not None:
            bars = activeExplorer.CommandBars
            toolbar = bars.Item("Standard")
            # Add our "Delete as ..." and "Recover as" buttons
            but_delete_as = button = toolbar.Controls.Add(
                                    Type=constants.msoControlButton,
                                    Temporary=True)
            # Hook events for the item
            button.BeginGroup = True
            button = DispatchWithEvents(button, ButtonDeleteAsSpamEvent)
            button.Init(self.manager, application)
            self.buttons.append(button)
            # And again for "Recover as"
            but_recover_as = button = toolbar.Controls.Add(
                                    Type=constants.msoControlButton,
                                    Temporary=True)
            button = DispatchWithEvents(button, ButtonRecoverFromSpamEvent)
            self.buttons.append(button)
            # Hook our explorer events, and pass the buttons.
            button.Init(self.manager, application)

            self.explorer_events = WithEvents(activeExplorer,
                                               ExplorerEvent)

            self.explorer_events.Init(self.manager, application, but_delete_as, but_recover_as)
            # And prime the event handler.
            self.explorer_events.OnFolderSwitch()

            # The main tool-bar dropdown with all out entries.
            # Add a pop-up menu to the toolbar
            popup = toolbar.Controls.Add(
                                Type=constants.msoControlPopup,
                                Temporary=True)
            popup.Caption="Anti-Spam"
            popup.TooltipText = "Anti-Spam filters and functions"
            popup.Enabled = True
            # Convert from "CommandBarItem" to derived
            # "CommandBarPopup" Not sure if we should be able to work
            # this out ourselves, but no introspection I tried seemed
            # to indicate we can.  VB does it via strongly-typed
            # declarations.
            popup = CastTo(popup, "CommandBarPopup")
            # And add our children.
            self._AddPopup(popup, manager.ShowManager, (self.manager,),
                           Caption="Anti-Spam Manager...",
                           TooltipText = "Show the Anti-Spam manager dialog.",
                           Enabled = True)
            self._AddPopup(popup, ShowClues, (self.manager, application),
                           Caption="Show spam clues for current message",
                           Enabled=True)

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
            existing = self.folder_hooks.get(msgstore_folder.id)
            if existing is None or existing.__class__ != HandlerClass:
                folder = msgstore_folder.GetOutlookItem()
                name = folder.Name.encode("mbcs", "replace")
                try:
                    new_hook = DispatchWithEvents(folder.Items, HandlerClass)
                except ValueError:
                    print "WARNING: Folder '%s' can not hook events" % (name,)
                    new_hook = None
                if new_hook is not None:
                    new_hook.Init(folder, self.application, self.manager)
                    new_hooks[msgstore_folder.id] = new_hook
                    self.manager.EnsureOutlookFieldsForFolder(msgstore_folder.GetID())
                    print "AntiSpam: Watching for new messages in folder", name
            else:
                new_hooks[msgstore_folder.id] = existing
        return new_hooks

    def GetSelectedMessages(self, allow_multi = True, explorer = None):
        if explorer is None:
            explorer = self.application.ActiveExplorer()
        sel = explorer.Selection
        if sel.Count > 1 and not allow_multi:
            win32ui.MessageBox("Please select a single item", "Large selection")
            return None

        ret = []
        for i in range(sel.Count):
            item = sel.Item(i+1)
            if item.Class == constants.olMail:
                msgstore_message = self.manager.message_store.GetMessage(item)
                ret.append(msgstore_message)

        if len(ret) == 0:
            win32ui.MessageBox("No mail items are selected", "No selection")
            return None
        if allow_multi:
            return ret
        return ret[0]

    def OnDisconnection(self, mode, custom):
        print "SpamAddin - Disconnecting from Outlook"
        self.folder_hooks = None
        self.application = None
        if self.manager is not None:
            self.manager.Save()
            self.manager.Close()
            self.manager = None

        if self.explorer_events is not None:
            self.explorer_events = None
        if self.buttons:
            for button in self.buttons:
                button.Close()
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
        pass
    def OnStartupComplete(self, custom):
        pass
    def OnBeginShutdown(self, custom):
        pass

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
