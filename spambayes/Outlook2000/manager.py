from __future__ import generators

import cPickle
import os
import sys

import win32com.client
import win32com.client.gencache
import pythoncom

import config
import msgstore

try:
    this_filename = os.path.abspath(__file__)
except NameError:
    this_filename = os.path.abspath(sys.argv[0])

# This is a little bit of a hack <wink>.  We are generally in a child directory
# of the bayes code.  To help installation, we handle the fact that this may
# not be on sys.path.  Note that doing these imports is delayed, so that we
# can set the BAYESCUSTOMIZE envar first (if we import anything from the core
# spambayes code before setting that envar, our .ini file may have no effect).
def import_core_spambayes_stuff(ini_filename):
    global bayes_classifier, bayes_tokenize

    os.environ["BAYESCUSTOMIZE"] = ini_filename
    try:
        import classifier
    except ImportError:
        parent = os.path.abspath(os.path.join(os.path.dirname(this_filename),
                                              ".."))
        sys.path.insert(0, parent)

    import classifier
    from tokenizer import tokenize
    bayes_classifier = classifier
    bayes_tokenize = tokenize

class ManagerError(Exception):
    pass

class BayesManager:
    def __init__(self, config_base="default", outlook=None, verbose=1):
        self.addin = None
        self.verbose = verbose
        if not os.path.isabs(config_base):
            config_base = os.path.join(os.path.dirname(this_filename),
                                       config_base)
        config_base = os.path.abspath(config_base)
        self.ini_filename = config_base + "_bayes_customize.ini"
        self.bayes_filename = config_base + "_bayes_database.pck"
        self.message_db_filename = config_base + "_message_database.pck"
        self.config_filename = config_base + "_configuration.pck"

        # First read the configuration file.
        self.config = self.LoadConfig()

        self.outlook = outlook

        import_core_spambayes_stuff(self.ini_filename)
        self.LoadBayes()
        self.message_store = msgstore.MAPIMsgStore(outlook)

    # Outlook gives us thread grief :(
    def WorkerThreadStarting(self):
        pythoncom.CoInitialize()

    def WorkerThreadEnding(self):
        pythoncom.CoUninitialize()

    def FormatFolderNames(self, folder_ids, include_sub):
        names = []
        for eid in folder_ids:
            try:
                name = self.message_store.GetFolder(eid).name
            except pythoncom.com_error:
                name = "<unknown folder>"
            names.append(name)
        ret = '; '.join(names)
        if include_sub:
            ret += " (incl. Sub-folders)"
        return ret

    def EnsureOutlookFieldsForFolder(self, folder_id, include_sub = False):
        # Ensure that our fields exist on the Outlook *folder*
        # Setting properties via our msgstore (via Ext Mapi) gets the props
        # on the message OK, but Outlook doesn't see it as a "UserProperty".
        # Using MAPI to set them directly on the folder also has no effect.
        # So until we know better, use Outlook to hack this in.
        # Should be called once per folder you are watching/filtering etc
        assert self.outlook is not None, "I need outlook :("
        ol = self.outlook
        folder = ol.Session.GetFolderFromID(*folder_id)
        if self.verbose > 1:
            print "Checking folder '%s' for our field '%s'" \
                  % (self.config.field_score_name,folder.Name.encode("mbcs", "replace"))
        items = folder.Items
        item = items.GetFirst()
        if item is not None:
            ups = item.UserProperties
            # Display format is documented as being the 1-based index in
            # the combo box in the outlook UI for the given data type.
            # 1 is the first - "all digits", which seems fine.
            # *sigh* - need to search by int index
            for i in range(ups.Count):
                up = ups[i+1]
                if up.Name == self.config.field_score_name:
                    break
            else: # for not broken
                try:
                    ups.Add(self.config.field_score_name,
                           # "Integer" from the UI doesn't exist!
                           # 'olNumber' doesn't seem to work with PT_INT*
                           win32com.client.constants.olCombination,
                           True) # Add to folder
                    item.Save()
                    if self.verbose > 1:
                        print "Created the UserProperty!"
                except pythoncom.com_error:
                    import traceback
                    print "Failed to create the field"
                    traceback.print_exc()
        # else no items in this folder - not much worth doing!
        if include_sub:
            # Recurse down the folder list.
            folders = item.Folders
            folder = folders.GetFirst()
            while folder is not None:
                self.EnsureOutlookFieldsForFolder(folder.EntryID, True)
                folder = folders.GetNext()

    def LoadBayes(self):
        if not os.path.exists(self.ini_filename):
            raise ManagerError("The file '%s' must exist before the "
                               "database '%s' can be opened or created" % (
                               self.ini_filename, self.bayes_filename))
        bayes = message_db = None
        try:
            bayes = cPickle.load(open(self.bayes_filename, 'rb'))
            print "Loaded bayes database from '%s'" % (self.bayes_filename,)
        except IOError:
            pass # ignore file-not-found
        except:
            print "Failed to load bayes database"
            import traceback
            traceback.print_exc()
        try:
            message_db = cPickle.load(open(self.message_db_filename, 'rb'))
            print "Loaded message database from '%s'" % (self.message_db_filename,)
        except IOError:
            pass
        except:
            print "Failed to load bayes message database"
            import traceback
            traceback.print_exc()
        if bayes is None or message_db is None:
            print "Either bayes database or message database is missing - creating new"
            self.InitNewBayes()
            bayes = self.bayes
            message_db = self.message_db
        if self.verbose:
            print ("Bayes database initialized with "
                   "%d spam and %d good messages" % (bayes.nspam, bayes.nham))
        if len(message_db) != bayes.nham + bayes.nspam:
            print "*** - message database only has %d messages - bayes has %d - something is screwey" % \
                    (len(message_db), bayes.nham + bayes.nspam)
        self.bayes = bayes
        self.message_db = message_db
        self.bayes_dirty = False

    def LoadConfig(self):
        try:
            f = open(self.config_filename, 'rb')
        except IOError:
            if self.verbose:
                print ("Created new configuration file '%s'" %
                       self.config_filename)
            return config.ConfigurationRoot()

        try:
            ret = cPickle.load(f)
            f.close()
            if self.verbose > 1:
                print "Loaded configuration from '%s':" % self.config_filename
                ret._dump()
        except (AttributeError, ImportError):
            ret = config.ConfigurationRoot()
            print "FAILED to load configuration from '%s' - using default:" % (self.config_filename,)
            import traceback
            traceback.print_exc()
        except IOError, details:
            # File-not-found - less serious.
            ret = config.ConfigurationRoot()
            if self.verbose > 1:
                # filename included in exception!
                print "IOError loading configuration (%s) - using default:" % (details)
        return ret

    def InitNewBayes(self):
        self.bayes = bayes_classifier.Bayes()
        self.message_db = {} # OK, so its not quite a DB yet <wink>
        self.bayes_dirty = True

    def SaveBayes(self):
        bayes = self.bayes
        if self.verbose:
            print ("Saving bayes database with %d spam and %d good messages" %
                   (bayes.nspam, bayes.nham))
            print " ->", self.bayes_filename
        cPickle.dump(bayes, open(self.bayes_filename,"wb"), 1)
        if self.verbose:
            print " ->", self.message_db_filename
        cPickle.dump(self.message_db, open(self.message_db_filename,"wb"), 1)
        self.bayes_dirty = False

    def SaveConfig(self):
        if self.verbose > 1:
            print "Saving configuration:"
            self.config._dump()
            print " ->", self.config_filename
        cPickle.dump(self.config, open(self.config_filename,"wb"), 1)

    def Save(self):
        self.SaveConfig()
        if self.bayes_dirty:
            self.SaveBayes()
        else:
            print "Bayes database is not dirty - not writing"

    def Close(self):
        if self.bayes_dirty and self.bayes:
            print "Warning: BayesManager closed while Bayes database dirty"
        self.bayes = None
        self.config = None
        if self.message_store is not None:
            self.message_store.Close()
            self.message_store = None

    def score(self, msg, evidence=False, scale=True):
        """Score a msg.

        If optional arg evidence is specified and true, the result is a
        two-tuple

            score, clues

        where clues is a list of the (word, spamprob(word)) pairs that
        went into determining the score.  Else just the score is returned.

        If optional arg scale is specified and false, the score is a float
        in 0.0 (ham) thru 1.0 (spam).  Else (the default), the score is
        scaled into an integer from 0 (ham) thru 100 (spam).
        """

        email = msg.GetEmailPackageObject()
        result = self.bayes.spamprob(bayes_tokenize(email), evidence)
        if not scale:
            return result
        # For sister-friendliness, multiply score by 100 and round to an int.
        if evidence:
            score, the_evidence = result
        else:
            score = result
        score = int(round(score * 100.0))
        if evidence:
            return score, the_evidence
        else:
            return score

_mgr = None

def GetManager(outlook = None, verbose=1):
    global _mgr
    if _mgr is None:
        if outlook is None:
            outlook = win32com.client.Dispatch("Outlook.Application")
        _mgr = BayesManager(outlook=outlook, verbose=verbose)
    # If requesting greater verbosity, honour it
    if verbose > _mgr.verbose:
        _mgr.verbose = verbose
    return _mgr

def ShowManager(mgr):
    def do_train(dlg):
        import train
        import dialogs.TrainingDialog
        d = dialogs.TrainingDialog.TrainingDialog(dlg.mgr, train.trainer)
        d.DoModal()

    def do_filter(dlg):
        import filter
        import dialogs.FilterDialog
        d = dialogs.FilterDialog.FilterNowDialog(dlg.mgr, filter.filterer)
        d.DoModal()

    def define_filter(dlg):
        import filter
        import dialogs.FilterDialog
        d = dialogs.FilterDialog.FilterArrivalsDialog(dlg.mgr, filter.filterer)
        d.DoModal()
        if dlg.mgr.addin is not None:
            dlg.mgr.addin.FiltersChanged()


    import dialogs.ManagerDialog
    d = dialogs.ManagerDialog.ManagerDialog(mgr, do_train, do_filter, define_filter)
    d.DoModal()

def main(verbose_level = 1):
    try:
        mgr = GetManager(verbose=verbose_level)
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
