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
from spambayes.OptionsClass import BOOLEAN, REAL, PATH

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
        PATH, RESTORE),
    ("delete_as_spam_message_state", "How the 'read' flag on a message is modified", "None",
        """When the 'Delete as Spam' function is used, the message 'read' flag can
           also be set.""",
           MSG_READ_STATE, RESTORE),
    ("recover_from_spam_message_state", "How the 'read' flag on a message is modified", "None",
        """When the 'Recover from Spam' function is used, the message 'read' flag can
           also be set.""",
           MSG_READ_STATE, RESTORE),
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
        """State of the 'rescore' button""",
        BOOLEAN, RESTORE),
    ),

    # These options control how a message is categorized
    "Filter" : (
    ("filter_now", "State of 'Filter Now' checkbox", False,
        """Something useful.""",
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
        """""",
        REAL, RESTORE),
    ("spam_action", "The action to take for new spam", "Untouched",
        """""",
        FILTER_ACTION, RESTORE),
    (FolderIDOption,
        "unsure_folder_id", "The folder used to track uncertain messages", None,
        """The folder SpamBayes moves or copies uncertain messages to.""",
        FOLDER_ID, DO_NOT_RESTORE),
    ("unsure_threshold", "The score necessary to be considered 'unsure'", 15.0,
        """""",
        REAL, RESTORE),
    ("unsure_action", "The action to take for new uncertain messages", "Untouched",
        """""",
        FILTER_ACTION, RESTORE),
    ("enabled", "Is filtering enabled?", False,
        """""",
        BOOLEAN, RESTORE),
    ),
    "Filter_Now": (
    (FolderIDOption, "folder_ids", "Folders to filter in a 'Filter Now' operation", [],
        """""",
        FOLDER_ID, DO_NOT_RESTORE),
    ("include_sub", "Does the nominated folders include sub-folders?", False,
        """""",
        BOOLEAN, DO_NOT_RESTORE),
    ("only_unread", "Only filter unread messages?", False,
        """""",
        BOOLEAN, RESTORE),
    ("only_unseen", "Only filter previously unseen ?", False,
        """""",
        BOOLEAN, RESTORE),
    ("action_all", "Perform all filter actions?", True,
        """""",
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

def CreateConfig():
    options = OptionsClass()
    options.load_defaults(defaults)
    return options

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
    options.update_file("delme.cfg")
    print "Created 'delme.cfg'"

