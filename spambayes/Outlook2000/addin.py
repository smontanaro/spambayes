# SpamBayes Outlook Addin

import sys, os
import warnings
import traceback

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

toolbar_name = "SpamBayes"

# If we are not running in a console, redirect all print statements to the
# win32traceutil collector.
# You can view output either from Pythonwin's "Tools->Trace Collector Debugging Tool",
# or simply run "win32traceutil.py" from a command prompt.
try:
    win32api.GetConsoleTitle()
except win32api.error:
    # No console - if we are running from Python sources,
    # redirect to win32traceutil, but if running from a binary
    # install, redirect to a log file.
    # Want to move to logging module later, so for now, we
    # hack together a simple logging strategy.
    if hasattr(sys, "frozen"):
        dir = win32api.GetTempPath()
        for i in range(3,0,-1):
            try: os.unlink(os.path.join(dir, "spambayes%d.log" % (i+1)))
            except os.error: pass
            try:
                os.rename(
                    os.path.join(dir, "spambayes%d.log" % i),
                    os.path.join(dir, "spambayes%d.log" % (i+1))
                    )
            except os.error: pass
        # Open this log, as unbuffered so crashes still get written.
        sys.stdout = open(os.path.join(dir,"spambayes1.log"), "wt", 0)
        sys.stderr = sys.stdout
    else:
        import win32traceutil

# Set our locale to be English, so our config parser works OK
# (This should almost certainly be done elsewhere, but as no one
# else seems to have an opinion on where this is, here is as good
# as any!
import locale
locale.setlocale(locale.LC_NUMERIC, "en")

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
            gencache.EnsureModule(tla[0], tla[1], tla[3], tla[4])
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

# Function to filter a message - note it is a msgstore msg, not an
# outlook one
def ProcessMessage(msgstore_message, manager):
    if msgstore_message.GetField(manager.config.general.field_score_name) is not None:
        # Already seem this message - user probably moving it back
        # after incorrect classification.
        # If enabled, re-train as Ham
        # otherwise just ignore.
        if manager.config.training.train_recovered_spam:
            subject = msgstore_message.GetSubject()
            import train
            print "Training on message '%s' - " % subject,
            if train.train_message(msgstore_message, False, manager, rescore = True):
                print "trained as good"
            else:
                print "already was trained as good"
            assert train.been_trained_as_ham(msgstore_message, manager)
            manager.SaveBayesPostIncrementalTrain()
        return
    if manager.config.filter.enabled:
        import filter
        disposition = filter.filter_message(msgstore_message, manager)
        print "Message '%s' had a Spam classification of '%s'" \
              % (msgstore_message.GetSubject(), disposition)
    else:
        print "Spam filtering is disabled - ignoring new message"

# Button/Menu and other UI event handler classes
class ButtonEvent:
    def Init(self, handler, *args):
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
        if msgstore_message is not None:
            ProcessMessage(msgstore_message, self.manager)

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
        prop = msgstore_message.GetField(self.manager.config.general.field_score_name)
        if prop is not None:
            import train
            trained_as_good = train.been_trained_as_ham(msgstore_message, self.manager)
            if self.manager.config.filter.spam_threshold > prop * 100 or \
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
                # And if the DB can save itself incrementally, do it now
                self.manager.SaveBayesPostIncrementalTrain()

# Event function fired from the "Show Clues" UI items.
def ShowClues(mgr, explorer):
    from cgi import escape

    app = explorer.Application
    msgstore_message = explorer.GetSelectedMessages(False)
    if msgstore_message is None:
        return

    item = msgstore_message.GetOutlookItem()
    score, clues = mgr.score(msgstore_message, evidence=True)
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
    msg = msgstore_message.GetEmailPackageObject(strip_mime_headers=False)
    push(escape(msg.as_string(), True))
    push("</PRE>\n")

    # Show all the tokens in the message
    from spambayes.tokenizer import tokenize
    from spambayes.classifier import Set # whatever classifier uses
    push("<h2>Message Tokens:</h2><br>")
    # need to re-fetch, as the tokens we see may be different based on
    # header stripping.
    toks = Set(tokenize(
        msgstore_message.GetEmailPackageObject(strip_mime_headers=True)))
    # create a sorted list
    toks = list(toks)
    toks.sort()
    push("%d unique tokens<br><br>" % len(toks))
    # Use <code> instead of <pre>, as <pre> is not word-wrapped by IE
    # However, <code> does not require escaping.
    # could use pprint, but not worth it.
    for token in toks:
        push("<code>" + repr(token) + "</code><br>\n")

    # Put the body together, then the rest of the message.
    body = ''.join(body)
    new_msg.Subject = "Spam Clues: " + item.Subject
    # As above, use HTMLBody else Outlook refuses to behave.
    new_msg.HTMLBody = "<HTML><BODY>" + body + "</BODY></HTML>"
    # Attach the source message to it
    # Using the original message has the side-effect of marking the original
    # as unread.  Tried to make a copy, but the copy then refused to delete
    # itself.
    # And the "UnRead" property of the message is not reflected in the object
    # model (we need to "refresh" the message).  Oh well.
    new_msg.Attachments.Add(item, constants.olByValue,
                            DisplayName="Original Message")
    new_msg.Display()

# A hook for whatever tests we have setup
def Tester(manager):
    import tester, traceback
    try:
        print "Executing automated tests..."
        tester.test(manager)
        print "Tests worked."
    except:
        traceback.print_exc()
        print "Tests FAILED.  Sorry about that.  If I were you, I would do a full re-train ASAP"
        print "Please delete any test messages from your Spam, Unsure or Inbox folders first."

# The "Delete As Spam" and "Recover Spam" button
# The event from Outlook's explorer that our folder has changed.
class ButtonDeleteAsEventBase:
    def Init(self, manager, explorer):
        self.manager = manager
        self.explorer = explorer

    def Close(self):
        self.manager = self.explorer = None

class ButtonDeleteAsSpamEvent(ButtonDeleteAsEventBase):
    def Init(self, manager, explorer):
        ButtonDeleteAsEventBase.Init(self, manager, explorer)
        image = "delete_as_spam.bmp"
        self.Caption = "Delete As Spam"
        self.TooltipText = \
                        "Move the selected message to the Spam folder,\n" \
                        "and train the system that this is Spam."
        SetButtonImage(self, image, manager)

    def OnClick(self, button, cancel):
        msgstore = self.manager.message_store
        msgstore_messages = self.explorer.GetSelectedMessages(True)
        if not msgstore_messages:
            return
        win32ui.DoWaitCursor(1)
        # Delete this item as spam.
        spam_folder = None
        spam_folder_id = self.manager.config.filter.spam_folder_id
        if spam_folder_id:
            spam_folder = msgstore.GetFolder(spam_folder_id)
        if not spam_folder:
            self.manager.ReportError("You must configure the Spam folder",
                               "Invalid Configuration")
            return
        import train
        new_msg_state = self.manager.config.general.delete_as_spam_message_state
        for msgstore_message in msgstore_messages:
            # Must train before moving, else we lose the message!
            subject = msgstore_message.GetSubject()
            print "Moving and spam training message '%s' - " % (subject,),
            if train.train_message(msgstore_message, True, self.manager, rescore = True):
                print "trained as spam"
            else:
                print "already was trained as spam"
            # Do the new message state if necessary.
            try:
                if new_msg_state == "Read":
                    msgstore_message.SetReadState(True)
                elif new_msg_state == "Unread":
                    msgstore_message.SetReadState(False)
                else:
                    if new_msg_state not in ["", "None", None]:
                        print "*** Bad new_msg_state value: %r" % (new_msg_state,)
            except pythoncom.com_error:
                print "*** Failed to set the message state to '%s' for message '%s'" % (new_msg_state, subject)
            # Now move it.
            msgstore_message.MoveTo(spam_folder)
            # Note the move will possibly also trigger a re-train
            # but we are smart enough to know we have already done it.
        # And if the DB can save itself incrementally, do it now
        self.manager.SaveBayesPostIncrementalTrain()
        win32ui.DoWaitCursor(0)

class ButtonRecoverFromSpamEvent(ButtonDeleteAsEventBase):
    def Init(self, manager, explorer):
        ButtonDeleteAsEventBase.Init(self, manager, explorer)
        image = "recover_ham.bmp"
        self.Caption = "Recover from Spam"
        self.TooltipText = \
                "Recovers the selected item back to the folder\n" \
                "it was filtered from (or to the Inbox if this\n" \
                "folder is not known), and trains the system that\n" \
                "this is a good message\n"
        SetButtonImage(self, image, manager)

    def OnClick(self, button, cancel):
        msgstore = self.manager.message_store
        msgstore_messages = self.explorer.GetSelectedMessages(True)
        if not msgstore_messages:
            return
        win32ui.DoWaitCursor(1)
        # Get the inbox as the default place to restore to
        # (incase we dont know (early code) or folder removed etc
        app = self.explorer.Application
        inbox_folder = msgstore.GetFolder(
                    app.Session.GetDefaultFolder(constants.olFolderInbox))
        new_msg_state = self.manager.config.general.recover_from_spam_message_state
        import train
        for msgstore_message in msgstore_messages:
            # Recover where they were moved from
            # During experimenting/playing/debugging, it is possible
            # that the source folder == dest folder - restore to
            # the inbox in this case.
            restore_folder = msgstore_message.GetRememberedFolder()
            if restore_folder is None or \
               msgstore_message.GetFolder() == restore_folder:
                restore_folder = inbox_folder

            # Must train before moving, else we lose the message!
            subject = msgstore_message.GetSubject()
            print "Recovering to folder '%s' and ham training message '%s' - " % (restore_folder.name, subject),
            if train.train_message(msgstore_message, False, self.manager, rescore = True):
                print "trained as ham"
            else:
                print "already was trained as ham"
            # Do the new message state if necessary.
            try:
                if new_msg_state == "Read":
                    msgstore_message.SetReadState(True)
                elif new_msg_state == "Unread":
                    msgstore_message.SetReadState(False)
                else:
                    if new_msg_state not in ["", "None", None]:
                        print "*** Bad new_msg_state value: %r" % (new_msg_state,)
            except pythoncom.com_error:
                print "*** Failed to set the message state to '%s' for message '%s'" % (new_msg_state, subject)
            # Now move it.
            msgstore_message.MoveTo(restore_folder)
            # Note the move will possibly also trigger a re-train
            # but we are smart enough to know we have already done it.
        # And if the DB can save itself incrementally, do it now
        self.manager.SaveBayesPostIncrementalTrain()
        win32ui.DoWaitCursor(0)

# Helpers to work with images on buttons/toolbars.
def SetButtonImage(button, fname, manager):
    # whew - http://support.microsoft.com/default.aspx?scid=KB;EN-US;q288771
    # shows how to make a transparent bmp.
    # Also note that the clipboard takes ownership of the handle -
    # this, we can not simply perform this load once and reuse the image.
    if not os.path.isabs(fname):
        # images relative to the application path
        fname = os.path.join(manager.application_directory,
                                 "images", fname)
    if not os.path.isfile(fname):
        print "WARNING - Trying to use image '%s', but it doesn't exist" % (fname,)
        return None
    handle = win32gui.LoadImage(0, fname, win32con.IMAGE_BITMAP, 0, 0, win32con.LR_DEFAULTSIZE | win32con.LR_LOADFROMFILE)
    win32clipboard.OpenClipboard()
    win32clipboard.SetClipboardData(win32con.CF_BITMAP, handle)
    win32clipboard.CloseClipboard()
    button.Style = constants.msoButtonIconAndCaption
    button.PasteFace()

# A class that manages an "Outlook Explorer" - that is, a top-level window
# All UI elements are managed here, and there is one instance per explorer.
class ExplorerWithEvents:
    def Init(self, manager, explorers_collection):
        self.manager = manager
        self.have_setup_ui = False
        self.explorers_collection = explorers_collection
        self.toolbar = None

    def SetupUI(self):
        manager = self.manager
        activeExplorer = self
        assert self.toolbar is None, "Should not yet have a toolbar"
        # Add our "Delete as ..." and "Recover as" buttons
        self.but_delete_as = self._AddControl(
                        None,
                        constants.msoControlButton,
                        ButtonDeleteAsSpamEvent, (self.manager, self),
                        BeginGroup = False,
                        Tag = "SpamBayesCommand.DeleteAsSpam")
        # And again for "Recover as"
        self.but_recover_as = self._AddControl(
                        None,
                        constants.msoControlButton,
                        ButtonRecoverFromSpamEvent, (self.manager, self),
                        Tag = "SpamBayesCommand.RecoverFromSpam")

        # The main tool-bar dropdown with all our entries.
        # Add a pop-up menu to the toolbar
        popup = self._AddControl(
                        None,
                        constants.msoControlPopup,
                        None, None,
                        Caption="SpamBayes",
                        TooltipText = "SpamBayes anti-spam filters and functions",
                        Enabled = True,
                        Tag = "SpamBayesCommand.Popup")
        if popup is not None: # We may not be able to find/create our button
            # Convert from "CommandBarItem" to derived
            # "CommandBarPopup" Not sure if we should be able to work
            # this out ourselves, but no introspection I tried seemed
            # to indicate we can.  VB does it via strongly-typed
            # declarations.
            popup = CastTo(popup, "CommandBarPopup")
            # And add our children.
            self._AddControl(popup,
                           constants.msoControlButton,
                           ButtonEvent, (manager.ShowManager,),
                           Caption="SpamBayes Manager...",
                           TooltipText = "Show the SpamBayes manager dialog.",
                           Enabled = True,
                           Visible=True,
                           Tag = "SpamBayesCommand.Manager")
            self._AddControl(popup,
                           constants.msoControlButton,
                           ButtonEvent, (ShowClues, self.manager, self),
                           Caption="Show spam clues for current message",
                           Enabled=True,
                           Visible=True,
                           Tag = "SpamBayesCommand.Clues")
        # If we are running from Python sources, enable a few extra items
        if not hasattr(sys, "frozen"):
            self._AddControl(popup,
                           constants.msoControlButton,
                           ButtonEvent, (Tester, self.manager),
                           Caption="Execute test suite",
                           Enabled=True,
                           Visible=True,
                           Tag = "SpamBayesCommand.TestSuite")
        self.have_setup_ui = True

    def _AddControl(self,
                    parent, # who the control is added to
                    control_type, # type of control to add.
                    events_class, events_init_args, # class/Init() args
                    **item_attrs): # extra control attributes.
        # Outlook Toolbars suck :)
        # We have tried a number of options: temp/perm in the standard toolbar,
        # Always creating our own toolbar, etc.
        # This seems to be fairly common:
        # http://groups.google.com/groups?threadm=eKKmbvQvAHA.1808%40tkmsftngp02
        # Now the strategy is just to use our own, permanent toolbar, with
        # permanent items, and ignore uninstall issues.
        # We search all commandbars for a control with our Tag.  If found, we
        # use it (the user may have customized the bar and moved our buttons
        # elsewhere).  If we can not find the child control, we then try and
        # locate our toolbar, creating if necessary.  Our items get added to
        # that.
        assert item_attrs.has_key('Tag'), "Need a 'Tag' attribute!"
        tag = item_attrs["Tag"]
        item = self.CommandBars.FindControl(
                        Type = control_type,
                        Tag = tag)
        if item is None:
            if parent is None:
                # No parent specified - that means top-level - locate the
                # toolbar to use as the parent.
                if self.toolbar is None:
                    # See if we can find our "SpamBayes" toolbar
                    # Indexing via the name appears unreliable, so just loop
                    # Pity we have no "Tag" on a toolbar - then we could even
                    # handle being renamed by the user.
                    bars = self.CommandBars
                    for i in range(bars.Count):
                        toolbar = bars.Item(i+1)
                        if toolbar.Name == "SpamBayes":
                            self.toolbar = toolbar
                            print "Found SB toolbar - visible state is", toolbar.Visible
                            break
                    else:
                        # for not broken - can't find toolbar.  Create a new one.
                        # Create it as a permanent one (which is default)
                        if self.explorers_collection.have_created_toolbar:
                            # Eeek - we have already created a toolbar, but
                            # now we can't find it.  It is likely this is the
                            # first time we are being run, and outlook is
                            # being started with multiple Windows open.
                            # Hopefully things will get back to normal once
                            # Outlook is restarted (which testing shows it does)
                            return

                        print "Creating new SpamBayes toolbar to host our buttons"
                        self.toolbar = bars.Add(toolbar_name, constants.msoBarTop, Temporary=False)
                        self.explorers_collection.have_created_toolbar = True
                    self.toolbar.Visible = True
                parent = self.toolbar
            # Now add the item itself to the parent.
            item = parent.Controls.Add(Type=control_type, Temporary=False)
        # Hook events for the item, but only if we haven't already in some
        # other explorer instance.
        if events_class is not None and tag not in self.explorers_collection.button_event_map:
            item = DispatchWithEvents(item, events_class)
            item.Init(*events_init_args)
            # We must remember the item itself, else the events get disconnected
            # as the item destructs.
            self.explorers_collection.button_event_map[tag] = item
        # Set the extra attributes passed in.
        for attr, val in item_attrs.items():
            setattr(item, attr, val)
        return item

    def GetSelectedMessages(self, allow_multi = True, explorer = None):
        if explorer is None:
            explorer = self.Application.ActiveExplorer()
        sel = explorer.Selection
        if sel.Count > 1 and not allow_multi:
            self.manager.ReportError("Please select a single item", "Large selection")
            return None

        ret = []
        for i in range(sel.Count):
            item = sel.Item(i+1)
            if item.Class == constants.olMail:
                msgstore_message = self.manager.message_store.GetMessage(item)
                ret.append(msgstore_message)

        if len(ret) == 0:
            self.manager.ReportError("No mail items are selected", "No selection")
            return None
        if allow_multi:
            return ret
        return ret[0]

    # The Outlook event handlers
    def OnActivate(self):
        self.manager.LogDebug(2, "OnActivate", self)
        # See comments for OnNewExplorer below.
        # *sigh* - OnActivate seems too early too for Outlook 2000,
        # but Outlook 2003 seems to work here, and *not* the folder switch etc
        # Outlook 2000 crashes when a second window is created and we use this
        # event
        # OnViewSwitch however seems useful, so we ignore this.
        pass

    def OnSelectionChange(self):
        self.manager.LogDebug(2, "OnSelectionChange", self)
        # See comments for OnNewExplorer below.
        if not self.have_setup_ui:
            self.SetupUI()
            # Prime the button views.
            self.OnFolderSwitch()

    def OnClose(self):
        self.manager.LogDebug(2, "OnClose", self)
        self.explorers_collection._DoDeadExplorer(self)
        self.explorers_collection = None
        self.toolbar = None
        self.close() # disconnect events.

    def OnBeforeFolderSwitch(self, new_folder, cancel):
        self.manager.LogDebug(2, "OnBeforeFolderSwitch", self)

    def OnFolderSwitch(self):
        self.manager.LogDebug(2, "OnFolderSwitch", self)
        # Yet another worm-around for our event timing woes.  This may
        # be the first event ever seen for this explorer if, eg,
        # "Outlook Today" is the initial Outlook view.
        if not self.have_setup_ui:
            self.SetupUI()
        # Work out what folder we are in.
        outlook_folder = self.CurrentFolder
        if outlook_folder is None or \
           outlook_folder.DefaultItemType != constants.olMailItem:
            show_delete_as = False
            show_recover_as = False
        else:
            show_delete_as = True
            show_recover_as = False
            try:
                mapi_folder = self.manager.message_store.GetFolder(outlook_folder)
                look_id = self.manager.config.filter.spam_folder_id
                if mapi_folder is not None and look_id:
                    look_folder = self.manager.message_store.GetFolder(look_id)
                    if mapi_folder == look_folder:
                        # This is the Spam folder - only show "recover"
                        show_recover_as = True
                        show_delete_as = False
                # Check if uncertain
                look_id = self.manager.config.filter.unsure_folder_id
                if mapi_folder is not None and look_id:
                    look_folder = self.manager.message_store.GetFolder(look_id)
                    if mapi_folder == look_folder:
                        show_recover_as = True
                        show_delete_as = True
            except:
                print "Error finding the MAPI folders for a folder switch event"
                import traceback
                traceback.print_exc()
        if self.but_recover_as is not None:
            self.but_recover_as.Visible = show_recover_as
        if self.but_delete_as is not None:
            self.but_delete_as.Visible = show_delete_as

    def OnBeforeViewSwitch(self, new_view, cancel):
        self.manager.LogDebug(2, "OnBeforeViewSwitch", self)

    def OnViewSwitch(self):
        self.manager.LogDebug(2, "OnViewSwitch", self)
        if not self.have_setup_ui:
            self.SetupUI()

# Events from our "Explorers" collection (not an Explorer instance)
class ExplorersEvent:
    def Init(self, manager):
        assert self.manager
        self.manager = manager
        self.explorers = []
        self.have_created_toolbar = False
        self.button_event_map = {}

    def Close(self):
        self.explorers = None

    def _DoNewExplorer(self, explorer):
        explorer = DispatchWithEvents(explorer, ExplorerWithEvents)
        explorer.Init(self.manager, self)
        self.explorers.append(explorer)

    def _DoDeadExplorer(self, explorer):
        self.explorers.remove(explorer)
        if len(self.explorers)==0:
            # No more explorers - disconnect all events.
            # (not doing this causes shutdown problems)
            for tag, button in self.button_event_map.items():
                closer = getattr(button, "Close", None)
                if closer is not None:
                    closer()
            self.button_event_map = {}

    def OnNewExplorer(self, explorer):
        # NOTE - Outlook has a bug, as confirmed by many on Usenet, in
        # that OnNewExplorer is too early to access the CommandBars
        # etc elements. We hack around this by putting the logic in
        # the first OnActivate call of the explorer itself.
        # Except that doesn't always work either - sometimes
        # OnActivate will cause a crash when selecting "Open in New Window",
        # so we tried OnSelectionChanges, which works OK until there is a
        # view with no items (eg, Outlook Today) - so at the end of the
        # day, we can never assume we have been initialized!
        self._DoNewExplorer(explorer)

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

    def OnConnection(self, application, connectMode, addin, custom):
        # Handle failures during initialization so that we are not
        # automatically disabled by Outlook.
        # Our error reporter is in the "manager" module, so we get that first
        import manager
        try:
            self.application = application
            self.manager = None # if we die while creating it!
            # Create our bayes manager
            self.manager = manager.GetManager(application)
            assert self.manager.addin is None, "Should not already have an addin"
            self.manager.addin = self
    
            # Only now will the import of "spambayes.Version" work, as the
            # manager is what munges sys.path for us.
            from spambayes.Version import get_version_string
            print "%s starting (with engine %s)..." % \
                    (get_version_string("Outlook"), get_version_string())

            self.explorers_events = None # create at OnStartupComplete

            if self.manager.config.filter.enabled:
                # A little "sanity test" to help the user.  If our status is
                # 'enabled', then it means we have previously managed to
                # convince the manager dialog we have enough ham/spam and
                # valid folders.  If for some reason, we have zero ham or spam,
                # or no folder definitions but are 'enabled', then it is likely
                # something got hosed and the user doesn't know.
                if self.manager.bayes.nham==0 or \
                   self.manager.bayes.nspam==0 or \
                   not self.manager.config.filter.spam_folder_id or \
                   not self.manager.config.filter.watch_folder_ids:
                    msg = "It appears there was an error loading your configuration\r\n\r\n" \
                          "Please re-configure SpamBayes via the SpamBayes dropdown"
                    self.manager.ReportError(msg)
                # But continue on regardless.
                self.FiltersChanged()
                try:
                    self.ProcessMissedMessages()
                except:
                    print "Error processing missed messages!"
                    traceback.print_exc()
        except:
            print "Error connecting to Outlook!"
            traceback.print_exc()
            manager.ReportError(
                "There was an error initializing the SpamBayes addin\r\n\r\n"
                "Please re-start Outlook and try again.")

    def ProcessMissedMessages(self):
        # This could possibly spawn threads if it was too slow!
        from time import clock
        config = self.manager.config.filter
        manager = self.manager
        field_name = manager.config.general.field_score_name
        for folder in manager.message_store.GetFolderGenerator(
                                    config.watch_folder_ids,
                                    config.watch_include_sub):
            num = 0
            start = clock()
            for message in folder.GetNewUnscoredMessageGenerator(field_name):
                ProcessMessage(message, manager)
                num += 1
            # See if perf hurts anyone too much.
            print "Processing %d missed spam in folder '%s' took %gms" \
                  % (num, folder.name, (clock()-start)*1000)

    def FiltersChanged(self):
        try:
            # Create a notification hook for all folders we filter.
            self.UpdateFolderHooks()
        except:
            self.manager.ReportFatalStartupError(
                "Could not watch the specified folders")

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
                    print "SpamBayes: Watching for new messages in folder ", name
            else:
                new_hooks[msgstore_folder.id] = existing
        return new_hooks

    def OnDisconnection(self, mode, custom):
        print "SpamBayes - Disconnecting from Outlook"
        self.folder_hooks = None
        self.application = None
        self.explorers_events = None
        if self.manager is not None:
            # Save database - bsddb databases will generally do nothing here
            # as it will not be dirty, but pickles will.
            # config never needs saving as it is always done by whoever changes
            # it (ie, the dialog)
            self.manager.Save()
            stats = self.manager.stats
            print "SpamBayes processed %d messages, finding %d spam and %d unsure" % \
                (stats.num_seen, stats.num_spam, stats.num_unsure)
            self.manager.Close()
            self.manager = None

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
        # Toolbar and other UI stuff must be setup once startup is complete.
        explorers = self.application.Explorers
        if self.manager is not None: # If we successfully started up.
            # and Explorers events so we know when new explorers spring into life.
            self.explorers_events = WithEvents(explorers, ExplorersEvent)
            self.explorers_events.Init(self.manager)
            # And hook our UI elements to all existing explorers
            for i in range(explorers.Count):
                explorer = explorers.Item(i+1)
                self.explorers_events._DoNewExplorer(explorer)

    def OnBeginShutdown(self, custom):
        pass

def RegisterAddin(klass):
    # prints to help debug binary install issues.
    print "Starting register"
    import _winreg
    key = _winreg.CreateKey(_winreg.HKEY_CURRENT_USER,
                            "Software\\Microsoft\\Office\\Outlook\\Addins")
    subkey = _winreg.CreateKey(key, klass._reg_progid_)
    print "Setting values"
    _winreg.SetValueEx(subkey, "CommandLineSafe", 0, _winreg.REG_DWORD, 0)
    _winreg.SetValueEx(subkey, "LoadBehavior", 0, _winreg.REG_DWORD, 3)
    _winreg.SetValueEx(subkey, "Description", 0, _winreg.REG_SZ, "SpamBayes anti-spam tool")
    _winreg.SetValueEx(subkey, "FriendlyName", 0, _winreg.REG_SZ, "SpamBayes")
    print "Registration complete."

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
