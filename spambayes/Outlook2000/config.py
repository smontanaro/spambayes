# configuration classes for the plugin.
# We used to use a little pickle, but have since moved to a "spambayes.Options"
# class.

# Hack for testing - setup sys.path
if __name__=='__main__':
    try:
        import spambayes.Options
    except ImportError:
        import sys, os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), "..")))

import sys, types

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 0==0, 1==0


FOLDER_ID = r"\(\'[a-fA-F0-9]+\', \'[a-fA-F0-9]+\'\)"
FIELD_NAME = r"[a-zA-Z0-9 ]+"
FILTER_ACTION = "Untouched", "Moved", "Copied"
MSG_READ_STATE = "None", "Read", "Unread"

from spambayes.OptionsClass import OptionsClass, Option
from spambayes.OptionsClass import RESTORE, DO_NOT_RESTORE
from spambayes.OptionsClass import BOOLEAN, INTEGER, REAL, PATH

class FolderIDOption(Option):
    def convert(self, value):
        #print "Convert called on", repr(value)
        error = None
        is_multi = self.multiple_values_allowed()
        # empty string means nothing to single value.
        if not is_multi and not value:
            return None
        # Now sure why we get non-strings here for multis
        if type(value) == types.ListType:
            return value
        # If we really care here, it would be fairly easy to use a regex
        # etc to pull these IDs apart.  eval is easier for now :)
        try:
            items = eval(value)
        except:
            error = "Invalid value (%s:%s)" % (sys.exc_type, sys.exc_value)
        check_items = []
        if error is None:
            if is_multi:
                if type(items) != types.ListType:
                    error = "Multi-valued ID must yield a list"
                check_items = items
            else:
                check_items = [items]
        if error is None:
            for item in check_items:
                if item is None:
                    error = "None isn't valid here (how did it get here anyway?"
                    break
                if not self.is_valid_single(item):
                    error = "Each ID must be a tuple of 2 strings"
                    break
        if error is not None:
            print "Failed to convert FolderID value '%r', is_multi=%d" % \
                  (value, is_multi)
            print error
            if is_multi:
                return []
            else:
                return None
        return items

    def unconvert(self):
        #print "unconvert called with", repr(self.value)
        if self.value is None:
            return ""
        return str(self.value)
    
    def multiple_values_allowed(self):
        return type(self.value)==types.ListType

    def is_valid_single(self, value):
        return value is None or \
               (type(value)==types.TupleType and \
               len(value)==2 and \
               type(value[0])==type(value[1])==types.StringType)

defaults = {
    "General" : (
    ("field_score_name", "The name of the field used to store the spam score", "Spam",
        """SpamBayes stores the spam score for each message in a custom field.
        This option specifies the name of the field""",
        FIELD_NAME, RESTORE),
    ("data_directory", "The directory to store the data files.", "",
        """""",
        PATH, DO_NOT_RESTORE),
    ("delete_as_spam_message_state", "How the 'read' flag on a message is modified", "None",
        """When the 'Delete as Spam' function is used, the message 'read' flag can
           also be set.""",
           MSG_READ_STATE, RESTORE),
    ("recover_from_spam_message_state", "How the 'read' flag on a message is modified", "None",
        """When the 'Recover from Spam' function is used, the message 'read' flag can
           also be set.""",
           MSG_READ_STATE, RESTORE),
    ("verbose", "Changes the verbosity of the debug output from the program", 0,
        """""",
        INTEGER, RESTORE),
    ),
    # Experimental options may change, may get removed, and *will* get moved
    # should they be kept.
    # Experimental options will *never* be exposed via the GUI, meaning that
    # migrating any such options should be considered a favour :)
    "Experimental" : (
        # These are migrated, so must remain while migration code remains in place.
        # This isn't critical, so should be deleted after just a few version.
        ("timer_start_delay", "obsolete", 0, "", INTEGER, RESTORE),
        ("timer_interval", "obsolete", 1000, "", INTEGER, RESTORE),
        ("timer_only_receive_folders", "obsolete", True, "", BOOLEAN, RESTORE),
    ),
    "Training" : (
    (FolderIDOption,
        "ham_folder_ids", "Folders containing known good messages", [],
        """A list of folders known to contain good (ham) messages.  When SpamBayes
        is trained, these messages will be used as examples of good messages.""",
        FOLDER_ID, DO_NOT_RESTORE),
    ("ham_include_sub", "Does the nominated ham folders include sub-folders?", False,
        """""",
        BOOLEAN, DO_NOT_RESTORE),
    (FolderIDOption,
        "spam_folder_ids", "Folders containing known bad or spam messages", [],
        """A list of folders known to contain bad (spam) messages.  When SpamBayes
        is trained, these messages will be used as examples of messages to filter.""",
        FOLDER_ID, DO_NOT_RESTORE),
    ("spam_include_sub", "Does the nominated spam folders include sub-folders?", False,
        """""",
        BOOLEAN, DO_NOT_RESTORE),
    ("train_recovered_spam", "Train as good as items are recovered?", True,
        """SpamBayes can detect when a message previously classified as spam
        (or unsure) is moved back to the folder from which it was filtered.
        If this option is enabled, SpamBayes will automatically train on
        such messages""",
        BOOLEAN, RESTORE),
    ("train_manual_spam", "Train as spam items are manually moved?", True,
        """SpamBayes can detect when a message previously classified as good
        (or unsure) is manually moved to the Spam folder.  If this option is
        enabled, SpamBayes will automatically train on such messages""",
        BOOLEAN, RESTORE),
    ("rescore", "Rescore message after training?", True,
        """After the training has completed, should all the messages be
        scored for their Spam value.  This is particularly useful after
        your initial training runs, so you can see how effective your
        sorting of spam and ham was.""",
        BOOLEAN, RESTORE),
    ("rebuild", "Rescore message after training?", True,
        """Should the entire database be rebuilt?  If enabled, then all
        training information is reset, and a complete new database built
        from the existing messages in your folders.  If disabled, then only
        new messages in the folders that have not previously been trained
        on will be processed""",
        BOOLEAN, RESTORE),
    ),

    # These options control how a message is categorized
    "Filter" : (
    ("filter_now", "State of 'Filter Now' checkbox", False,
        """Something useful.""",
        BOOLEAN, RESTORE),
    ("save_spam_info", "Save spam score", True,
        """Should the spam score and other information be saved in each message
        as it is filtered or scored?""",
        BOOLEAN, RESTORE),
    (FolderIDOption,
       "watch_folder_ids", "Folders to watch for new messages", [],
        """The list of folders SpamBayes will watch for new messages,
        processing messages as defined by the filters.""",
        FOLDER_ID, DO_NOT_RESTORE),
    ("watch_include_sub", "Does the nominated watch folders include sub-folders?", False,
        """""",
        BOOLEAN, DO_NOT_RESTORE),
    (FolderIDOption,
        "spam_folder_id", "The folder used to track spam", None,
        """The folder SpamBayes moves or copies spam to.""",
        FOLDER_ID, DO_NOT_RESTORE),
    ("spam_threshold", "The score necessary to be considered 'certain' spam", 90.0,
        """Any message with a Spam score greater than or equal to this value
        will be considered spam, and processed accordingly.""",
        REAL, RESTORE),
    ("spam_action", "The action to take for new spam", "Moved",
        """The action that should be taken as Spam messages arrive.""",
        FILTER_ACTION, RESTORE),
    ("spam_mark_as_read", "Should filtered spam also be marked as 'read'", False,
        """Determines if spam messages are marked as 'Read' as they are
        filtered.  This can be set to 'True' if the new-mail folder counts bother
        you when the only new items are spam.  It can be set to 'False'
        if you use the 'read' state of these messages to determine which
        items you are yet to review. This option does not affect the
        new-mail icon in the system tray.""",
        BOOLEAN, RESTORE),
    (FolderIDOption,
        "unsure_folder_id", "The folder used to track uncertain messages", None,
        """The folder SpamBayes moves or copies uncertain messages to.""",
        FOLDER_ID, DO_NOT_RESTORE),
    ("unsure_threshold", "The score necessary to be considered 'unsure'", 15.0,
        """Any message with a Spam score greater than or equal to this value
        (but less than the spam threshold) will be considered spam, and
        processed accordingly.""",
        REAL, RESTORE),
    ("unsure_action", "The action to take for new uncertain messages", "Moved",
        """The action that should be taken as unsure messages arrive.""",
        FILTER_ACTION, RESTORE),
    ("unsure_mark_as_read", "Should filtered uncertain message also be marked as 'read'", False,
        """Determines if unsure messages are marked as 'Read' as they are
        filtered.  See 'spam_mark_as_read' for more details.""",
        BOOLEAN, RESTORE),
    ("enabled", "Is filtering enabled?", False,
        """""",
        BOOLEAN, RESTORE),
    # Options that allow the filtering to be done by a timer.
    ("timer_enabled", "Should items be filtered by a timer?", False,
        """Depending on a number of factors, SpamBayes may occasionally miss
        messages or conflict with builtin Outlook rules.  If this option
        is set, SpamBayes will filter all messages in the background.  This
        generally solves both of these problem, at the cost of having Spam stay
        in your inbox for a few extra seconds.""",
        BOOLEAN, RESTORE),
    ("timer_start_delay", "The interval (in seconds) before the timer starts.", 2.0,
        """Once a new item is received in the inbox, SpamBayes will begin
        processing messages after the given delay.  If a new message arrives
        during this period, the timer will be reset and the delay will start again.""",
        REAL, RESTORE),
    ("timer_interval", "The interval between subsequent timer checks (in seconds)", 1.0,
        """Once the new message timer finds a new message, how long should
        SpamBayes wait before checking for another new message, assuming no
        other new messages arrive.  Should a new message arrive during this
        process, the timer will reset, meaning that timer_start_delay will
        elapse before the process begins again.""",
        REAL, RESTORE),
    ("timer_only_receive_folders",
        "Should the timer only be used for 'Inbox' type folders?", True,
        """The point of using a timer is to prevent the SpamBayes filter
        getting in the way the builtin Outlook rules.  Therefore, is it 
        generally only necessary to use a timer for folders that have new
        items being delivered directly to them.  Folders that are not inbox
        style folders generally are not subject to builtin filtering, so
        generally have no problems filtering messages in 'real time'.""",
        BOOLEAN, RESTORE),
    ),
    "Filter_Now": (
    (FolderIDOption, "folder_ids", "Folders to filter in a 'Filter Now' operation", [],
        """The list of folders that will be filtered by this process.""",
        FOLDER_ID, DO_NOT_RESTORE),
    ("include_sub", "Does the nominated folders include sub-folders?", False,
        """""",
        BOOLEAN, DO_NOT_RESTORE),
    ("only_unread", "Only filter unread messages?", False,
        """When scoring messages, should only messages that are unread be
        considered?""",
        BOOLEAN, RESTORE),
    ("only_unseen", "Only filter previously unseen ?", False,
        """When scoring messages, should only messages that have never
        previously Spam scored be considered?""",
        BOOLEAN, RESTORE),
    ("action_all", "Perform all filter actions?", True,
        """When scoring the messages, should all items be performed (such as
        moving the items based on the score) or should the items only be scored,
        but otherwise untouched.""",
        BOOLEAN, RESTORE),
    ),
}

# A simple container that provides "." access to items
class SectionContainer:
    def __init__(self, options, section):
        self.__dict__['_options'] = options
        self.__dict__['_section'] = section
    def __getattr__(self, attr):
        return self._options.get(self._section, attr)
    def __setattr__(self, attr, val):
        return self._options.set(self._section, attr, val)

class OptionsContainer:
    def __init__(self, options):
        self.__dict__['_options'] = options
    def __getattr__(self, attr):
        attr = attr.lower()
        for key in self._options.sections():
            if attr == key.lower():
                container = SectionContainer(self._options, key)
                self.__dict__[attr] = container
                return container
        raise AttributeError, "Options has no section '%s'" % attr
    def __setattr__(self, attr, val):
        raise AttributeError, "No section [%s]" % attr
    # and delegate a few methods so this object can be used in place of
    # a real options object. maybe should add this to getattr. do we want all?
    def get_option(self, section, name):
        return self._options.get_option(section, name)

def CreateConfig(defaults=defaults):
    options = OptionsClass()
    options.load_defaults(defaults)
    return options

def MigrateOptions(options):
    # Migrate some "old" options to "new" options.  Can be deleted in
    # a few versions :)
    # Binary007 last with experimental timer values.
    delay = options.get("Experimental", "timer_start_delay")
    interval = options.get("Experimental", "timer_interval")
    if delay and interval:
        options.set("Filter", "timer_enabled", True)
        options.set("Filter", "timer_start_delay", float(delay / 1000))
        options.set("Filter", "timer_interval", float(interval / 1000))
        # and reset the old options so they are not written to the new file
        # (actually, resetting isn't enough - must hack and clobber)
        del options._options["Experimental", "timer_start_delay"]
        del options._options["Experimental", "timer_interval"]

    torf = options.get("Experimental", "timer_only_receive_folders")
    if not torf:
        options.set("Filter", "timer_only_receive_folders", False)
        # and reset old
        del options._options["Experimental", "timer_only_receive_folders"]

# Old code when we used a pickle.  Still needed so old pickles can be
# loaded, and moved to the new options file format.
class _ConfigurationContainer:
    def __init__(self, **kw):
        self.__dict__.update(kw)
    def __setstate__(self, state):
        self.__dict__.update(state)
    def _dump(self, thisname="<root>", level=0):
        import pprint
        prefix = "  " * level
        print "%s%s:" % (prefix, thisname)
        for name, ob in self.__dict__.items():
            d = getattr(ob, "_dump", None)
            if d is None:
                print "%s %s: %s" % (prefix, name, pprint.pformat(ob))
            else:
                d(name, level+1)

class ConfigurationRoot(_ConfigurationContainer):
    def __init__(self):
        pass
# End of old pickle code.

if __name__=='__main__':
    options = CreateConfig()
    options.merge_files(['delme.cfg'])
    c = OptionsContainer(options)
    f = options.get("Training", "ham_folder_ids")
    print "Folders before set are", f
    for i in f:
        print i, type(i)
    new_folder_ids = [('000123','456789'), ('ABCDEF', 'FEDCBA')]
    options.set("Training", "ham_folder_ids", new_folder_ids)
    f = options.get("Training", "ham_folder_ids")
    print "Folders after set are", f
    for i in f:
        print i, type(i)

    try:
        c.filter.oops = "Foo"
    except (AttributeError,KeyError): # whatever :)
        pass
    else:
        print "ERROR: I was able to set an invalid sub-property!"

    try:
        c.oops = "Foo"
    except (AttributeError,KeyError): # whatever :)
        pass
    else:
        print "ERROR: I was able to set an invalid top-level property!"

    # Test single ID folders.
    if c.filter.unsure_folder_id is not None:
        print "It appears we loaded a folder ID - resetting"
        c.filter.unsure_folder_id = None
    unsure_id = c.filter.unsure_folder_id
    if unsure_id is not None: raise ValueError, "unsure_id wrong (%r)" % (c.filter.unsure_folder_id,)
    unsure_id = c.filter.unsure_folder_id = ('12345', 'abcdef')
    if unsure_id != c.filter.unsure_folder_id: raise ValueError, "unsure_id wrong (%r)" % (c.filter.unsure_folder_id,)
    c.filter.unsure_folder_id = None
    if c.filter.unsure_folder_id is not None: raise ValueError, "unsure_id wrong (%r)" % (c.filter.unsure_folder_id,)
    
    options.set("Filter", "filter_now", True)
    print "Filter_now from container is", c.filter.filter_now
    options.set("Filter", "filter_now", False)
    print "Filter_now from container is now", c.filter.filter_now
    c.filter.filter_now = True
    print "Filter_now from container is finally", c.filter.filter_now
    print "Only unread is", c.filter_now.only_unread
    v = r"/foo/bar"
    c.general.data_directory=v
    if c.general.data_directory!=v: print "Bad directory!", c.general.data_directory
    v = r"c:\test directory\some sub directory"
    c.general.data_directory=v
    if c.general.data_directory!=v: print "Bad directory!", c.general.data_directory
    v = r"\\server\c$"
    c.general.data_directory=v
    if c.general.data_directory!=v: print "Bad directory!", c.general.data_directory
    options.update_file("delme.cfg")
    print "Created 'delme.cfg'"

