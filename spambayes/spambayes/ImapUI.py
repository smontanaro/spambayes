"""IMAPFilter Web Interface

Classes:
    IMAPUserInterface - Interface class for the IMAP filter

Abstract:

This module implements a browser based Spambayes user interface for the
IMAP filter.  Users may use it to interface with the filter - it is
expected that this will primarily be for configuration, although users
may also wish to look up words in the database, or classify a message.

The following functions are currently included:
[From the base class UserInterface]
  onClassify - classify a given message
  onWordquery - query a word from the database
  onTrain - train a message or mbox
  onSave - save the database and possibly shutdown
[Here]
  onHome - a home page with various options

To do:
 o This could have a neat review page, like pop3proxy, built up by
   asking the IMAP server appropriate questions.  I don't know whether
   this is needed, however.  This would then allow viewing a message,
   showing the clues for it, and so on.  Finding a message (via the
   spambayes id) could also be done.
 o Suggestions?
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>, Tim Stone"
__credits__ = "All the Spambayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

import re

import UserInterface
from spambayes.Options import options, optionsPathname

# These are the options that will be offered on the configuration page.
# If the option is None, then the entry is a header and the following
# options will appear in a new box on the configuration page.
# These are also used to generate http request parameters and template
# fields/variables.
parm_map = (
    ('IMAP Options',          None),
    ('imap',                  'server'),
    ('imap',                  'username'),
    # to display, or not to display; that is the question!
    # if we show this here, it's in plain text for everyone to
    # see (and worse - if we don't restrict connections to
    # localhost, it's available for the world to see)
    # on the other hand, we have to be able to enter it somehow...
    ('imap',                  'password'),
    ('imap',                  'use_ssl'),
    ('Interface Options',     None),
    ('html_ui',               'allow_remote_connections'),
    ('Header Options',        None),
    ('Headers',               'notate_to'),
    ('Headers',               'notate_subject'),
    ('Storage Options',       None),
    ('Storage',               'persistent_storage_file'),
    ('Storage',               'messageinfo_storage_file'),
    ('Statistics Options',    None),
    ('Categorization',        'ham_cutoff'),
    ('Categorization',        'spam_cutoff'),
)

# Like the above, but hese are the options that will be offered on the
# advanced configuration page.
adv_map = (
    ('Statistics Options',  None),
    ('Classifier',          'max_discriminators'),
    ('Classifier',          'minimum_prob_strength'),
    ('Classifier',          'unknown_word_prob'),
    ('Classifier',          'unknown_word_strength'),
    ('Header Options',      None),
    ('Headers',             'include_score'),
    ('Headers',             'header_score_digits'),
    ('Headers',             'header_score_logarithm'),
    ('Headers',             'include_thermostat'),
    ('Headers',             'include_evidence'),
    ('Headers',             'clue_mailheader_cutoff'),
    ('Storage Options',     None),
    ('Storage',             'persistent_use_database'),
    ('Tokenising Options',  None),
    ('Tokenizer',           'mine_received_headers'),
    ('Tokenizer',           'replace_nonascii_chars'),
    ('Tokenizer',           'summarize_email_prefixes'),
    ('Tokenizer',           'summarize_email_suffixes'),
    ('Interface Options',   None),
    ('html_ui',             'display_adv_find'),
)

class IMAPUserInterface(UserInterface.UserInterface):
    """Serves the HTML user interface for the proxies."""
    def __init__(self, cls, imap, pwd, imap_session_class):
        global parm_map
        # Only offer SSL if it is available
        try:
            from imaplib import IMAP4_SSL
        except ImportError:
            parm_list = list(parm_map)
            parm_list.remove(("imap", "use_ssl"))
            parm_map = tuple(parm_list)
        else:
            del IMAP4_SSL
        UserInterface.UserInterface.__init__(self, cls, parm_map, adv_map)
        self.classifier = cls
        self.imap = imap
        self.imap_pwd = pwd
        self.imap_logged_in = False
        self.app_for_version = "IMAP Filter"
        self.imap_session_class = imap_session_class

    def onHome(self):
        """Serve up the homepage."""
        stateDict = self.classifier.__dict__.copy()
        stateDict["warning"] = ""
        stateDict.update(self.classifier.__dict__)
        statusTable = self.html.statusTable.clone()
        del statusTable.proxyDetails
        # This could be a bit more modular
        statusTable.configurationLink += """<br />&nbsp;&nbsp;&nbsp;&nbsp;
        &nbsp;You can also <a href='filterfolders'>configure folders to
        filter</a><br />and <a
        href='trainingfolders'>Configure folders to train</a>"""
        findBox = self._buildBox('Word query', 'query.gif',
                                 self.html.wordQuery)
        if not options["html_ui", "display_adv_find"]:
            del findBox.advanced
        content = (self._buildBox('Status and Configuration',
                                  'status.gif', statusTable % stateDict)+
                   self._buildTrainBox() +
                   self._buildClassifyBox() +
                   findBox
                   )
        self._writePreamble("Home")
        self.write(content)
        self._writePostamble()

    def reReadOptions(self):
        """Called by the config page when the user saves some new options, or
        restores the defaults."""
        # Re-read the options.
        self.classifier.store()
        import Options
        Options.load_options()
        global options
        from Options import options

    def onSave(self, how):
        if self.imap is not None:
            self.imap.logout()
        UserInterface.UserInterface.onSave(self, how)

    def onFilterfolders(self):
        self._writePreamble("Select Filter Folders")
        self._login_to_imap()
        if self.imap_logged_in:
            available_folders = self.imap.folder_list()
            content = self.html.configForm.clone()
            content.configFormContent = ""
            content.introduction = """This page allows you to change which
            folders are filtered, and where filtered mail ends up."""
            content.config_submit.value = "Save Filter Folders"
            content.optionsPathname = optionsPathname

            for opt in ("unsure_folder", "spam_folder",
                        "filter_folders"):
                folderBox = self._buildFolderBox("imap", opt, available_folders)
                content.configFormContent += folderBox

            self.write(content)
            self._writePostamble()

    def _login_to_imap(self):
        if self.imap_logged_in:
            return
        if self.imap is None and len(options["imap", "server"]) > 0:
            server = options["imap", "server"][0]
            if server.find(':') > -1:
                server, port = server.split(':', 1)
                port = int(port)
            else:
                if options["imap", "use_ssl"]:
                    port = 993
                else:
                    port = 143
            self.imap = self.imap_session_class(server, port)
        if self.imap is None:
            content = self._buildBox("Error", None,
                                     """Must specify server details first.""")
            self.write(content)
            self._writePostamble()
            return
        username = options["imap", "username"][0]
        if username == "":
            content = self._buildBox("Error", None,
                                     """Must specify username first.""")
            self.write(content)
            self._writePostamble()
            return
        self.imap.login(username, self.imap_pwd)
        self.imap_logged_in = True

    def onTrainingfolders(self):
        self._writePreamble("Select Training Folders")
        self._login_to_imap()
        if self.imap_logged_in:
            available_folders = self.imap.folder_list()
            content = self.html.configForm.clone()
            content.configFormContent = ""
            content.introduction = """This page allows you to change which
            folders contain mail to train Spambayes."""
            content.config_submit.value = "Save Training Folders"
            content.optionsPathname = optionsPathname

            for opt in ("ham_train_folders",
                        "spam_train_folders"):
                folderBox = self._buildFolderBox("imap", opt, available_folders)
                content.configFormContent += folderBox

            self.write(content)
            self._writePostamble()

    def onChangeopts(self, **parms):
        backup = self.parm_ini_map
        if parms["how"] == "Save Training Folders" or \
           parms["how"] == "Save Filter Folders":
            del parms["how"]
            self.parm_ini_map = ()
            for opt, value in parms.items():
                del parms[opt]
                # Under strange circumstances this could break,
                # so if we can think of a better way to do this,
                # that would be nice.
                if opt[-len(value):] == value:
                    opt = opt[:-len(value)]
                self.parm_ini_map += ("imap", opt),
                key = "imap_" + opt
                if parms.has_key(key):
                    parms[key] += ',' + value
                else:
                    parms[key] = value
        UserInterface.UserInterface.onChangeopts(self, **parms)
        self.parm_ini_map = backup

    def _buildFolderBox(self, section, option, available_folders):
        folderTable = self.html.configTable.clone()
        del folderTable.configTextRow1
        del folderTable.configTextRow2
        del folderTable.configCbRow1
        del folderTable.configRow2
        del folderTable.blankRow
        del folderTable.folderRow
        firstRow = True
        for folder in available_folders:
            folderRow = self.html.configTable.folderRow.clone()
            if firstRow:
                folderRow.helpCell = options.doc(section, option)
                firstRow = False
            else:
                del folderRow.helpCell
            folderRow.folderBox.name = option
            folderRow.folderBox.value = folder
            folderRow.folderName = folder
            if options.multiple_values_allowed(section, option):
                if folder in options[section, option]:
                    folderRow.folderBox.checked = "checked"
                folderRow.folderBox.name += folder
            else:
                if folder == options[section, option]:
                    folderRow.folderBox.checked = "checked"
                folderRow.folderBox.type = "radio"
            folderTable += folderRow
        return self._buildBox(options.display_name(section, option),
                              None, folderTable)
