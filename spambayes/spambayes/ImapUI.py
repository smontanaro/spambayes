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
 o There is a function to get a list of all the folders available on
   the server, but nothing is done with this.  Obviously what we would
   like is to present a page where the user selects (checkboxes) the
   folders that s/he wishes to filter, the folders s/he wishes to use
   as train-as-ham and train-as-spam, and (radio buttons) the folders
   to move suspected spam and unsures into.  I think this should be
   a separate page from the standard config as it's already going to
   be really big if there are lots of folders to choose from.
   An alternative design would be to have a single list of the folders
   and five columns - three of checkboxes (filter, train-as-spam and
   train-as-ham) and two of radio buttons (spam folder and ham folder).
   I think this might be more confusing, though.
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
from Options import options, optionsPathname

global classifier

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
    ('Header Options',        None),
    ('pop3proxy',             'notate_to'),
    ('pop3proxy',             'notate_subject'),
    ('pop3proxy',             'include_prob'),
    ('pop3proxy',             'include_thermostat'),
    ('pop3proxy',             'include_evidence'),
    ('pop3proxy',             'add_mailid_to'),
    ('pop3proxy',             'strip_incoming_mailids'),
    ('Statistics Options',    None),
    ('pop3proxy',             'persistent_storage_file'),
    ('Categorization',        'ham_cutoff'),
    ('Categorization',        'spam_cutoff'),
)

class IMAPUserInterface(UserInterface.UserInterface):
    """Serves the HTML user interface for the proxies."""

    def __init__(self, cls, imap):
        global classifier
        UserInterface.UserInterface.__init__(self, cls, parm_map)
        classifier = cls
        self.imap = imap

    def onHome(self):
        """Serve up the homepage."""
        stateDict = classifier.__dict__.copy()
        stateDict.update(classifier.__dict__)
        statusTable = self.html.statusTable.clone()
        del statusTable.proxyDetails
        # This could be a bit more modular
        statusTable.configurationLink += """You can also <a href=
        'filterfolders'>configure folders to filter</a> and <a href=
        'trainingfolders'>Configure folders to train</a>"""
        content = (self._buildBox('Status and Configuration',
                                  'status.gif', statusTable % stateDict)+
                   self._buildTrainBox() +
                   self._buildClassifyBox() +
                   self._buildBox('Word query', 'query.gif',
                                  self.html.wordQuery)
                   )
        self._writePreamble("Home")
        self.write(content)
        self._writePostamble()

    def reReadOptions(self):
        """Called by the config page when the user saves some new options, or
        restores the defaults."""
        # Reload the options.
        global classifier
        classifier.store()
        import Options
        reload(Options)
        global options
        from Options import options

    def onSave(self, how):
        self.imap.logout(False) # never expunge from the web ui
        UserInterface.UserInterface.onSave(self, how)

    def onFilterfolders(self):
        available_folders = self._folder_list()
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

        self._writePreamble("Select Filter Folders")
        self.write(content)
        self._writePostamble()

    def onTrainingfolders(self):
        available_folders = self._folder_list()
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

        self._writePreamble("Select Training Folders")
        self.write(content)
        self._writePostamble()

    def onChangeopts(self, **parms):
        backup = self.parm_ini_map
        print parms
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
        print self.parm_ini_map
        print parms
        UserInterface.UserInterface.onChangeopts(self, **parms)
        self.parm_ini_map = backup
        
    def _buildFolderBox(self, section, option, available_folders):
        folderTable = self.html.configTable.clone()
        del folderTable.configTextRow1
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
                folderRow.folderBox.name += folder
            else:
                folderRow.folderBox.type = "radio"
            current_options = ',' + options[section, option] + ','
            if current_options.find(',' + folder + ',') != -1:
                folderRow.folderBox.checked = "checked"
            folderTable += folderRow
        return self._buildBox(options.display_name(section, option),
                              None, folderTable)

    def _folder_list(self):
        '''Return a alphabetical list of all folders available
        on the server'''
        response = self.imap.list()
        if response[0] != "OK":
            return []
        all_folders = response[1]
        folders = []
        for fol in all_folders:
            r = re.compile(r"\(([\w\\ ]*)\) ")
            m = r.search(fol)
            name_attributes = fol[:m.end()-1]
            self.folder_delimiter = fol[m.end()+1:m.end()+2]
            # a bit of a hack, but we really need to know if this is
            # the case
            if self.folder_delimiter == ',':
                print """WARNING: Your imap server uses commas as the folder
                delimiter.  This may cause unpredictable errors."""
            folders.append(fol[m.end()+5:-1])
        folders.sort()
        return folders