from __future__ import generators

import cPickle
import os
import sys
import errno
import shutil
import traceback
import operator
import win32api, win32con, win32gui

import win32com.client
import win32com.client.gencache
import pythoncom

import msgstore

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

# Characters valid in a filename.  Used to nuke bad chars from the profile
# name (which we try and use as a filename).
# We assume characters > 127 are OK as they may be unicode
filename_chars = ('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
                '0123456789'
                """$%'-_@~ `!()^#&+,;=[]""")

# Report a message to the user - should only be used for pretty serious errors
# hence we also print a traceback.
# Module level function so we can report errors creating the manager
def _GetParent():
    try:
        return win32gui.GetActiveWindow()
    except win32gui.error:
        pass
    return 0

def _DoMessage(message, title, flags):
    return win32gui.MessageBox(_GetParent(), message, title, flags)

def ReportError(message, title = None):
    import traceback
    print "ERROR:", repr(message)
    if sys.exc_info()[0] is not None:
        traceback.print_exc()
    if title is None: title = "SpamBayes"
    _DoMessage(message, title, win32con.MB_ICONEXCLAMATION)

def ReportInformation(message, title = None):
    if title is None: title = "SpamBayes"
    _DoMessage(message, title, win32con.MB_ICONINFORMATION)

def AskQuestion(message, title = None):
    if title is None: title = "SpamBayes"
    return _DoMessage(message, title, win32con.MB_YESNO | \
                                      win32con.MB_ICONQUESTION) == win32con.IDYES

# Notes on Unicode directory names
# You will have much more success with extended characters in
# directory names using Python 2.3.
try:
    filesystem_encoding = sys.getfilesystemencoding()
except AttributeError:
    filesystem_encoding = "mbcs"

# Work out our "application directory", which is
# the directory of our main .py/.dll/.exe file we
# are running from.
try:
    if hasattr(sys, "frozen"):
        if sys.frozen == "dll":
            this_filename = win32api.GetModuleFileName(sys.frozendllhandle)
        else:
            # Don't think we will ever run as a .EXE, but...
            this_filename = os.path.abspath(sys.argv[0])
    else:
        this_filename = os.path.abspath(__file__)
except NameError: # no __file__
    this_filename = os.path.abspath(sys.argv[0])

# See if we can use the new bsddb module. (The old one is unreliable
# on Windows, so we don't use that)
try:
    import bsddb3 as bsddb
    # bsddb3 is definitely not broken
    use_db = True
except ImportError:
    # Not using the 3rd party bsddb3, so try the one in the std library
    try:
        import bsddb
        use_db = hasattr(bsddb, "db") # This name is not in the old one.
    except ImportError:
        # No DB library at all!
        use_db = False

# This is a little bit of a hack <wink>.  We are generally in a child
# directory of the bayes code.  To help installation, we handle the
# fact that this may not be on sys.path.  Note that doing these
# imports is delayed, so that we can set the BAYESCUSTOMIZE envar
# first (if we import anything from the core spambayes code before
# setting that envar, our .ini file may have no effect).
# However, we want *some* Spambayes code before the options are processed
# so this is now 2 steps - get the "early" spambayes core stuff (which
# must not import spambayes.Options) and sets up sys.path, and "later" core
# stuff, which can include spambayes.Options, and assume sys.path in place.
def import_early_core_spambayes_stuff():
    try:
        from spambayes import OptionsClass
    except ImportError:
        parent = os.path.abspath(os.path.join(os.path.dirname(this_filename),
                                              ".."))
        sys.path.insert(0, parent)

def import_core_spambayes_stuff(ini_filename):
    assert "spambayes.Options" not in sys.modules, \
        "'spambayes.Options' was imported too early"
    global bayes_classifier, bayes_tokenize, bayes_storage
    # ini_filename is Unicode, but environ not unicode aware
    os.environ["BAYESCUSTOMIZE"] = ini_filename.encode(filesystem_encoding)
    from spambayes import classifier
    from spambayes.tokenizer import tokenize
    from spambayes import storage
    bayes_classifier = classifier
    bayes_tokenize = tokenize
    bayes_storage = storage
    assert "spambayes.Options" in sys.modules, \
        "Expected 'spambayes.Options' to be loaded here"

class ManagerError(Exception):
    pass

class Stats:
    def __init__(self):
        self.num_seen = self.num_spam = self.num_unsure = 0

# Function to "safely" save a pickle, only overwriting
# the existing file after a successful write.
def SavePickle(what, filename):
    temp_filename = filename + ".tmp"
    file = open(temp_filename,"wb")
    try:
        cPickle.dump(what, file, 1)
    finally:
        file.close()
    # now rename to the correct file.
    try:
        os.unlink(filename)
    except os.error:
        pass
    os.rename(temp_filename, filename)

# Base class for our "storage manager" - we choose between the pickle
# and DB versions at runtime.  As our bayes uses spambayes.storage,
# our base class can share common bayes loading code.
class BasicStorageManager:
    db_extension = None # for pychecker - overwritten by subclass
    def __init__(self, bayes_base_name, mdb_base_name):
        self.bayes_filename = bayes_base_name + self.db_extension
        self.mdb_filename = mdb_base_name + self.db_extension
    def new_bayes(self):
        # Just delete the file and do an "open"
        try:
            os.unlink(self.bayes_filename)
        except EnvironmentError, e:
            if e.errno != errno.ENOENT: raise
        return self.open_bayes()
    def store_bayes(self, bayes):
        bayes.store()
    def open_bayes(self):
        raise NotImplementedError

class PickleStorageManager(BasicStorageManager):
    db_extension = ".pck"
    def open_bayes(self):
        return bayes_storage.PickledClassifier(self.bayes_filename)
    def close_bayes(self, bayes):
        pass
    def open_mdb(self):
        return cPickle.load(open(self.mdb_filename, 'rb'))
    def new_mdb(self):
        return {}
    def store_mdb(self, mdb):
        SavePickle(mdb, self.mdb_filename)
    def close_mdb(self, mdb):
        pass
    def is_incremental(self):
        return False # False means we always save the entire DB

class DBStorageManager(BasicStorageManager):
    db_extension = ".db"
    def open_bayes(self):
        # bsddb doesn't handle unicode filenames yet :(
        fname = self.bayes_filename.encode(filesystem_encoding)
        return bayes_storage.DBDictClassifier(fname)
    def close_bayes(self, bayes):
        bayes.db.close()
        bayes.dbm.close()
    def open_mdb(self):
        fname = self.mdb_filename.encode(filesystem_encoding)
        return bsddb.hashopen(fname)
    def new_mdb(self):
        try:
            os.unlink(self.mdb_filename)
        except EnvironmentError, e:
            if e.errno != errno.ENOENT: raise
        return self.open_mdb()
    def store_mdb(self, mdb):
        mdb.sync()
    def close_mdb(self, mdb):
        mdb.close()
    def is_incremental(self):
        return True # True means only changed records get actually written

# Encapsulates our entire classification database
# This allows a couple of different "databases" to be open at once
# eg, a "temporary" one for training, etc.
# The manager should contain no database state - it should all be here.
class ClassifierData:
    def __init__(self, db_manager, logger):
        self.db_manager = db_manager
        self.bayes = None
        self.message_db = None
        self.dirty = False
        self.logger = logger # currently the manager, but needed only for logging

    def Load(self):
        import time
        start = time.clock()
        bayes = message_db = None
        # Exceptions must be caught by caller.
        # file-not-found handled gracefully by storage.
        bayes = self.db_manager.open_bayes()
        fname = self.db_manager.bayes_filename.encode("mbcs", "replace")
        print "Loaded bayes database from '%s'" % (fname,)

        message_db = self.db_manager.open_mdb()
        fname = self.db_manager.mdb_filename.encode("mbcs", "replace")
        print "Loaded message database from '%s'" % (fname,)

        self.logger.LogDebug(0, "Bayes database initialized with "
                   "%d spam and %d good messages" % (bayes.nspam, bayes.nham))
        if len(message_db) != bayes.nham + bayes.nspam:
            print "*** - message database has %d messages - bayes has %d - something is screwey" % \
                    (len(message_db), bayes.nham + bayes.nspam)
        self.bayes = bayes
        self.message_db = message_db
        self.dirty = False
        self.logger.LogDebug(1, "Loaded databases in %gms" % ((time.clock()-start)*1000))

    def InitNew(self):
        if self.bayes is not None:
            self.db_manager.close_bayes(self.bayes)
        if self.message_db is not None:
            self.db_manager.close_mdb(self.message_db)
        self.bayes = self.db_manager.new_bayes()
        self.message_db = self.db_manager.new_mdb()
        self.dirty = True

    def SavePostIncrementalTrain(self):
        # Save the database after a training operation - only actually
        # saves if we aren't using pickles.
        if self.db_manager.is_incremental():
            if self.dirty:
                self.Save()
            else:
                self.logger.LogDebug(1, "Bayes database is not dirty - not writing")
        else:
            print "Using a slow database - not saving after incremental train"

    def Save(self):
        import time
        start = time.clock()
        bayes = self.bayes
        # Try and work out where this count sometimes goes wrong.
        if bayes.nspam + bayes.nham != len(self.message_db):
            print "WARNING: Bayes database has %d messages, " \
                  "but training database has %d" % \
                  (bayes.nspam + bayes.nham, len(self.message_db))

        if self.logger.verbose:
            print "Saving bayes database with %d spam and %d good messages" %\
                   (bayes.nspam, bayes.nham)
            print " ->", self.db_manager.bayes_filename
        self.db_manager.store_bayes(self.bayes)
        if self.logger.verbose:
            print " ->", self.db_manager.mdb_filename
        self.db_manager.store_mdb(self.message_db)
        self.dirty = False
        self.logger.LogDebug(1, "Saved databases in %gms" % ((time.clock()-start)*1000))

    def Close(self):
        if self.dirty and self.bayes:
            print "Warning: ClassifierData closed while Bayes database dirty"
        if self.db_manager:
            self.db_manager.close_bayes(self.bayes)
            self.db_manager.close_mdb(self.message_db)
            self.db_manager = None
        self.bayes = None
        self.logger = None

    def Adopt(self, other):
        assert not other.dirty, "Adopting dirty classifier data!"
        other.db_manager.close_bayes(other.bayes)
        other.db_manager.close_mdb(other.message_db)
        self.db_manager.close_bayes(self.bayes)
        self.db_manager.close_mdb(self.message_db)
        # Move the files
        shutil.move(other.db_manager.bayes_filename, self.db_manager.bayes_filename)
        shutil.move(other.db_manager.mdb_filename, self.db_manager.mdb_filename)
        # and re-open.
        self.Load()

def GetStorageManagerClass():
    return [PickleStorageManager, DBStorageManager][use_db]

# Our main "bayes manager"
class BayesManager:
    def __init__(self, config_base="default", outlook=None, verbose=0):
        self.never_configured = True
        self.reported_error_map = {}
        self.reported_startup_error = False
        self.config = self.options = None
        self.addin = None
        self.verbose = verbose
        self.stats = Stats()
        self.outlook = outlook
        self.dialog_parser = None

        import_early_core_spambayes_stuff()

        self.application_directory = os.path.dirname(this_filename)
        # where windows would like our data stored (and where
        # we do, unless overwritten via a config file)
        self.windows_data_directory = self.LocateDataDirectory()
        # Read the primary configuration files
        self.PrepareConfig()

        # See if the initial config files specify a
        # "data directory".  If so, use it, otherwise
        # use the default Windows data directory for our app.
        value = self.config.general.data_directory
        if value:
            # until I know otherwise, config files are ASCII - but our
            # file system is unicode to some degree.
            # (do config files support encodings at all?)
            # Assume the file system encoding for file names!
            try:
                value = value.decode(filesystem_encoding)
            except AttributeError: # May already be Unicode
                pass
            assert type(value) == type(u''), "%r should be a unicode" % value
            try:
                if not os.path.isdir(value):
                    os.makedirs(value)
                if not os.path.isdir(value):
                    raise os.error
                value = os.path.abspath(value)
            except os.error:
                print "The configuration files have specified a data directory of"
                print repr(value)
                print "but it is not valid.  Using default"
                value = None
        if value:
            self.data_directory = value
        else:
            self.data_directory = self.windows_data_directory

        # Now we have the data directory, migrate anything needed, and load
        # any config from it.
        self.MigrateDataDirectory()

        # Get the message store before loading config, as we use the profile
        # name.
        self.message_store = msgstore.MAPIMsgStore(outlook)
        self.LoadConfig()

        bayes_options_filename = os.path.join(self.data_directory, "default_bayes_customize.ini")
        import_core_spambayes_stuff(bayes_options_filename)

        bayes_base = os.path.join(self.data_directory, "default_bayes_database")
        mdb_base = os.path.join(self.data_directory, "default_message_database")
        # determine which db manager to use, and create it.
        ManagerClass = GetStorageManagerClass()
        db_manager = ManagerClass(bayes_base, mdb_base)
        self.classifier_data = ClassifierData(db_manager, self)
        self.LoadBayes()

    # "old" bayes functions - new code should use "classifier_data" directly
    def LoadBayes(self):
        try:
            self.classifier_data.Load()
        except:
            self.ReportFatalStartupError("Failed to load bayes database")
            self.classifier_data.InitNew()

    def InitNewBayes(self):
        self.classifier_data.InitNew()
    def SaveBayes(self):
        self.classifier_data.Save()
    def SaveBayesPostIncrementalTrain(self):
        self.classifier_data.SavePostIncrementalTrain()
    # Logging - this too should be somewhere else.
    def LogDebug(self, level, *args):
        if self.verbose >= level:
            for arg in args[:-1]:
                print arg,
            print args[-1]

    def ReportError(self, message, title = None):
        ReportError(message, title)
    def ReportInformation(self, message, title=None):
        ReportInformation(message, title)
    def AskQuestion(self, message, title=None):
        return AskQuestion(message, title)

    # Report a super-serious startup error to the user.
    # This should only be used when SpamBayes was previously working, but a
    # critical error means we are probably not working now.
    # We just report the first such error - subsequent ones are likely a result of
    # the first - hence, this must only be used for startup errors.
    def ReportFatalStartupError(self, message):
        if not self.reported_startup_error:
            self.reported_startup_error = True
            full_message = \
                "There was an error initializing the Spam plugin.\r\n\r\n" \
                "Spam filtering has been disabled.  Please re-configure\r\n" \
                "and re-enable this plugin\r\n\r\n" \
                "Error details:\r\n" + message
            # Disable the plugin
            if self.config is not None:
                self.config.filter.enabled = False
            self.ReportError(full_message)
        else:
            # We have reported the error, but for the sake of the log, we
            # still want it logged there.
            print "ERROR:", repr(message)
            traceback.print_exc()

    def ReportErrorOnce(self, msg, title = None, key = None):
        if key is None: key = msg
        # Always print the message and traceback.
        print "ERROR:", repr(msg)
        traceback.print_exc()
        if key in self.reported_error_map:
            print "(this error has already been reported - not displaying it again)"
        else:
            self.reported_error_map[key] = True
            ReportError(msg, title)

    # Outlook used to give us thread grief - now we avoid Outlook
    # from threads, but this remains a worthwhile abstraction.
    def WorkerThreadStarting(self):
        pythoncom.CoInitialize()

    def WorkerThreadEnding(self):
        pythoncom.CoUninitialize()

    def LocateDataDirectory(self):
        # Locate the best directory for our data files.
        from win32com.shell import shell, shellcon
        try:
            appdata = shell.SHGetFolderPath(0,shellcon.CSIDL_APPDATA,0,0)
            path = os.path.join(appdata, "SpamBayes")
            if not os.path.isdir(path):
                os.makedirs(path)
            return path
        except pythoncom.com_error:
            # Function doesn't exist on early win95,
            # and it may just fail anyway!
            return self.application_directory
        except EnvironmentError:
            # Can't make the directory.
            return self.application_directory
            
    def MigrateDataDirectory(self):
        # A bit of a nod to save people doing a full retrain.
        # Try and locate our files in the old location, and move
        # then to the new one.
        # Also used first time SpamBayes is run - this will cause
        # the ini file to be *copied* to the correct directory
        self._MigrateFile("default_bayes_customize.ini", False)
        self._MigrateFile("default_bayes_database.pck")
        self._MigrateFile("default_bayes_database.db")
        self._MigrateFile("default_message_database.pck")
        self._MigrateFile("default_message_database.db")
        self._MigrateFile("default_configuration.pck")

    # Copy a file from the application_directory to the data_directory.
    # By default (do_move not specified), the source file is deleted.
    # Pass do_move=False to leave the original file.
    def _MigrateFile(self, filename, do_move = True):
        src = os.path.join(self.application_directory, filename)
        dest = os.path.join(self.data_directory, filename)
        if os.path.isfile(src) and not os.path.isfile(dest):
            # shutil in 2.2 and earlier don't contain 'move'.
            # Win95 and Win98 don't support MoveFileEx.
            shutil.copyfile(src, dest)
            if do_move:
                os.remove(src)

    def FormatFolderNames(self, folder_ids, include_sub):
        names = []
        for eid in folder_ids:
            folder = self.message_store.GetFolder(eid)
            if folder is None:
                name = "<unknown folder>"
            else:
                name = folder.name
            names.append(name)
        ret = '; '.join(names)
        if include_sub:
            ret += " (incl. Sub-folders)"
        return ret

    def EnsureOutlookFieldsForFolder(self, folder_id, include_sub=False):
        # Ensure that our fields exist on the Outlook *folder*
        # Setting properties via our msgstore (via Ext Mapi) gets the props
        # on the message OK, but Outlook doesn't see it as a "UserProperty".
        # Using MAPI to set them directly on the folder also has no effect.
        # So until we know better, use Outlook to hack this in.
        # Should be called once per folder you are watching/filtering etc
        #
        # Oh the tribulations of our property grail
        # We originally wanted to use the "Integer" Outlook field,
        # but it seems this property type alone is not expose via the Object
        # model.  So we resort to olPercent, and live with the % sign
        # (which really is OK!)
        assert self.outlook is not None, "I need outlook :("
        msgstore_folder = self.message_store.GetFolder(folder_id)
        if msgstore_folder is None:
            print "Checking a folder for our field failed - "\
                  "there is no such folder."
            return
            
        folder = msgstore_folder.GetOutlookItem()
        self.LogDebug(2, "Checking folder '%s' for field '%s'" \
                  % (folder.Name.encode("mbcs", "replace"), self.config.general.field_score_name))
        items = folder.Items
        item = items.GetFirst()
        while item is not None:
            if item.Class != win32com.client.constants.olMail:
                item = items.GetNext()
                continue
            break
        # OK - item is either a mail item, or None
        if item is not None:
            ups = item.UserProperties
            # *sigh* - need to search by int index
            for i in range(ups.Count):
                up = ups[i+1]
                if up.Name == self.config.general.field_score_name:
                    break
            else: # for not broken
                try:
                    # Display format is documented as being the 1-based index in
                    # the combo box in the outlook UI for the given data type.
                    # 1 is the first - "Rounded", which seems fine.
                    format = 1
                    ups.Add(self.config.general.field_score_name,
                           win32com.client.constants.olPercent,
                           True, # Add to folder
                           format)
                    item.Save()
                    self.LogDebug(2, "Created the UserProperty!")
                except pythoncom.com_error, details:
                    print "Warning: failed to create the Outlook " \
                          "user-property in folder '%s'" \
                          % (folder.Name.encode("mbcs", "replace"),)
                    print "", details
            if include_sub:
                # Recurse down the folder list.
                folders = item.Parent.Folders
                folder = folders.GetFirst()
                while folder is not None:
                    this_id = folder.StoreID, folder.EntryID
                    self.EnsureOutlookFieldsForFolder(this_id, True)
                    folder = folders.GetNext()
        # else no items in this folder - not much worth doing!

    def PrepareConfig(self):
        # Load our Outlook specific configuration.  This is done before
        # SpamBayes is imported, and thus we are able to change the INI
        # file used for the engine.  It is also done before the primary
        # options are loaded - this means we can change the directory
        # from which these options are loaded.
        import config
        self.options = config.CreateConfig()
        # Note that self.options really *is* self.config - but self.config
        # allows a "." notation to access the values.  Changing one is reflected
        # immediately in the other.
        self.config = config.OptionsContainer(self.options)

        filename = os.path.join(self.application_directory, "default_configuration.ini")
        self._MergeConfigFile(filename)

        filename = os.path.join(self.windows_data_directory, "default_configuration.ini")
        self._MergeConfigFile(filename)

    def _MergeConfigFile(self, filename):
        try:
            self.options.merge_file(filename)
        except:
            msg = "The configuration file named below is invalid.\r\n" \
                    "Please either correct or remove this file\r\n\r\n" \
                    "Filename: " + filename
            self.ReportError(msg)

    def LoadConfig(self):
        # Insist on english numeric conventions in config file.
        # See addin.py, and [725466] Include a proper locale fix in Options.py
        import locale; locale.setlocale(locale.LC_NUMERIC, "C")

        profile_name = self.message_store.GetProfileName()
        # The profile name may include characters invalid in file names.
        if profile_name is not None:
            profile_name = "".join([c for c in profile_name
                                    if ord(c)>127 or c in filename_chars])
        if profile_name is None:
            # should only happen in source-code versions - older win32alls can't
            # determine this.
            profile_name = "unknown_profile"
            print "*** NOTE: It appears you are running the source-code version of"
            print "* SpamBayes, and running a win32all version pre 154."
            print "* If you work with multiple Outlook profiles, it is recommended"
            print "* you upgrade - see http://starship.python.net/crew/mhammond"""
        else:
            # xxx - remove me sometime - win32all grew this post 154(ish)
            # binary never released with this, so we can be a little more brutal
            # Try and rename to current profile, silent failure
            try:
                os.rename(os.path.join(self.data_directory, "unknown_profile.ini"),
                          os.path.join(self.data_directory, profile_name + ".ini"))
            except os.error:
                pass

        self.config_filename = os.path.join(self.data_directory, profile_name + ".ini")
        self.never_configured = not os.path.exists(self.config_filename)
        # Now load it up
        self._MergeConfigFile(self.config_filename)
        # Set global verbosity from the options file.
        self.verbose = self.config.general.verbose
        if self.verbose:
            self.LogDebug(self.verbose, "System verbosity set to", self.verbose)

        # Do any migrations - first the old pickle into the new format.
        self.MigrateOldPickle()
        # Then any options we change (particularly any 'experimental' ones we
        # consider important)
        import config
        config.MigrateOptions(self.options)

        if self.verbose > 1:
            print "Dumping loaded configuration:"
            print self.options.display()
            print "-- end of configuration --"

    def MigrateOldPickle(self):
        assert self.config is not None, "Must have a config"
        pickle_filename = os.path.join(self.data_directory,
                                       "default_configuration.pck")
        try:
            f = open(pickle_filename, 'rb')
        except IOError:
            self.LogDebug(1, "No old pickle file to migrate")
            return
        print "Migrating old pickle '%s'" % pickle_filename
        try:
            try:
                old_config = cPickle.load(f)
            except:
                print "FAILED to load old pickle"
                traceback.print_exc()
                msg = "There was an error loading your old\r\n" \
                      "SpamBayes configuration file.\r\n\r\n" \
                      "It is likely that you will need to re-configure\r\n" \
                      "SpamBayes before it will function correctly."
                self.ReportError(msg)
                # But we can't abort yet - we really should still try and
                # delete it, as we aren't gunna work next time in this case!
                old_config = None
        finally:
            f.close()
        if old_config is not None:
            for section, items in old_config.__dict__.items():
                print " migrating section '%s'" % (section,)
                # exactly one value wasn't in a section - now in "general"
                dict = getattr(items, "__dict__", None)
                if dict is None:
                    dict = {section: items}
                    section = "general"
                for name, value in dict.items():
                    sect = getattr(self.config, section)
                    setattr(sect, name, value)
        # Save the config, then delete the pickle so future attempts to
        # migrate will fail.  We save first, so failure here means next
        # attempt should still find the pickle.
        self.LogDebug(1, "pickle migration doing initial configuration save")
        try:
            self.LogDebug(1, "pickle migration removing '%s'" % pickle_filename)
            os.remove(pickle_filename)
        except os.error:
            msg = "There was an error migrating and removing your old\r\n" \
                  "SpamBayes configuration file.  Configuration changes\r\n" \
                  "you make are unlikely to be reflected next\r\n" \
                  "time you start Outlook.  Please try rebooting."
            self.ReportError(msg)


    def GetClassifier(self):
        """Return the classifier we're using."""
        return self.classifier_data.bayes

    def SaveConfig(self):
        # Insist on english numeric conventions in config file.
        # See addin.py, and [725466] Include a proper locale fix in Options.py
        import locale; locale.setlocale(locale.LC_NUMERIC, "C")

        # Update our runtime verbosity from the options.
        self.verbose = self.config.general.verbose
        print "Saving configuration ->", self.config_filename.encode("mbcs", "replace")
        assert self.config and self.options, "Have no config to save!"
        if self.verbose > 1:
            print "Dumping configuration to save:"
            print self.options.display()
            print "-- end of configuration --"
        self.options.update_file(self.config_filename)

    def Save(self):
        # No longer save the config here - do it explicitly when changing it
        # (prevents lots of extra pickle writes, for no good reason.  Other
        # alternative is a dirty flag for config - this is simpler)
        if self.classifier_data.dirty:
            self.classifier_data.Save()
        else:
            self.LogDebug(1, "Bayes database is not dirty - not writing")

    def Close(self):
        self.classifier_data.Close()
        self.config = None
        if self.message_store is not None:
            self.message_store.Close()
            self.message_store = None
        self.outlook = None

    def score(self, msg, evidence=False):
        """Score a msg.

        If optional arg evidence is specified and true, the result is a
        two-tuple

            score, clues

        where clues is a list of the (word, spamprob(word)) pairs that
        went into determining the score.  Else just the score is returned.
        """
        email = msg.GetEmailPackageObject()
        try:
            return self.classifier_data.bayes.spamprob(bayes_tokenize(email), evidence)
        except AssertionError:
            # See bug 706520 assert fails in classifier
            # For now, just tell the user.
            msg = "It appears your SpamBayes training database is corrupt.\r\n\r\n" \
                  "We are working on solving this, but unfortunately you\r\n" \
                  "must re-train the system via the SpamBayes manager."
            self.ReportErrorOnce(msg)
            raise

    def GetDisabledReason(self):
        # Gets the reason why the plugin can not be enabled.
        # If return is None, then it can be enabled (and indeed may be!)
        # Otherwise return is the string reason
        config = self.config.filter
        ok_to_enable = operator.truth(config.watch_folder_ids)
        if not ok_to_enable:
            return "You must define folders to watch for new messages.  " \
                   "Select the 'Filtering' tab to define these folders."

        ok_to_enable = operator.truth(config.spam_folder_id)
        if not ok_to_enable:
            return "You must define the folder to receive your certain spam.  " \
                   "Select the 'Filtering' tab to define this folders."

        return None

    def ShowManager(self):
        import dialogs
        dialogs.ShowDialog(0, self, self.config, "IDD_MANAGER")
        # And re-save now, just incase Outlook dies on the way down.
        self.SaveConfig()
    def ShowFilterNow(self):
        import dialogs
        dialogs.ShowDialog(0, self, self.config, "IDD_FILTER_NOW")
        # And re-save now, just incase Outlook dies on the way down.
        self.SaveConfig()

    def ShowHtml(self,url):
        """Displays the main SpamBayes documentation in your Web browser"""
        import sys, os, urllib
        if urllib.splittype(url)[0] is None: # just a file spec
            if hasattr(sys, "frozen"):
                # Same directory as to the executable.
                fname = os.path.join(os.path.dirname(sys.argv[0]),
                                        url)
            else:
                # (ie, main Outlook2000) dir
                fname = os.path.join(os.path.dirname(__file__),
                                        url)
            fname = os.path.abspath(fname)
            if not os.path.isfile(fname):
                self.ReportError("Can't find "+url)
                return
            url = fname
        # else assume it is valid!
        from dialogs import SetWaitCursor
        SetWaitCursor(1)
        os.startfile(url)
        SetWaitCursor(0)

_mgr = None

def GetManager(outlook = None):
    global _mgr
    if _mgr is None:
        if outlook is None:
            outlook = win32com.client.Dispatch("Outlook.Application")
        _mgr = BayesManager(outlook=outlook)
    return _mgr

def ShowManager(mgr):
    mgr.ShowManager()

def main(verbose_level = 1):
    try:
        mgr = GetManager()
        mgr.verbose = max(mgr.verbose, verbose_level)
    except ManagerError, d:
        print "Error initializing Bayes manager"
        print d
        return 1
    ShowManager(mgr)
    mgr.Save()
    mgr.Close()
    return 0

def usage():
    print "Usage: manager [-v ...]"
    sys.exit(1)

if __name__=='__main__':
    verbose = 1
    import getopt
    opts, args = getopt.getopt(sys.argv[1:], "v")
    if args:
        usage()
    for opt, val in opts:
        if opt=="-v":
            verbose += 1
        else:
            usage()
    sys.exit(main(verbose))
