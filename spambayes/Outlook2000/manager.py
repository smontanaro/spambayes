from __future__ import generators

import cPickle
import os
import sys
import thread

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

# Suck in CDO type lib
win32com.client.gencache.EnsureModule('{3FA7DEA7-6438-101B-ACC1-00AA00423326}',
                                      0, 1, 21, bForDemand=True)

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
        self.config_filename = config_base + "_configuration.pck"

        # First read the configuration file.
        path = os.path.split(this_filename)[0]
        self.config = self.LoadConfig()

        cwd = os.getcwd()
        self.mapi = win32com.client.Dispatch("MAPI.Session")
        self.mapi.Logon(None, None, False, False)
        self.outlook = outlook
        os.chdir(cwd)

        import_core_spambayes_stuff(self.ini_filename)
        self.LoadBayes()
        self.message_store = msgstore.MAPIMsgStore(outlook)

    # Outlook gives us thread grief :(
    def WorkerThreadStarting(self):
        pythoncom.CoInitialize()

    def WorkerThreadEnding(self):
        pythoncom.CoUninitialize()

    def LoadBayes(self):
        if not os.path.exists(self.ini_filename):
            raise ManagerError("The file '%s' must exist before the "
                               "database '%s' can be opened or created" % (
                               self.ini_filename, self.bayes_filename))
        bayes = None
        try:
            # Ooops - Tim did it another way - checking this in before I get more conficts!
##            from Options import options
##            options.mergefiles([self.ini_filename])
            bayes = cPickle.load(open(self.bayes_filename, 'rb'))
            print "Loaded bayes database from '%s'" % (self.bayes_filename,)
        except IOError:
            pass # ignore file-not-found
        except:
            print "Failed to load bayes database"
            import traceback
            traceback.print_exc()
        if bayes is None:
            self.InitNewBayes()
            bayes = self.bayes
        if self.verbose:
            print ("Bayes database initialized with "
                   "%d spam and %d good messages" % (bayes.nspam, bayes.nham))
        self.bayes = bayes
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
            # Ooops - Tim did it another way - checking this in before I get more conficts!
##        from Options import options
##        options.mergefiles([self.ini_filename])
        self.bayes = bayes_classifier.Bayes()
        self.bayes_dirty = True

    def SaveBayes(self):
        bayes = self.bayes
        if self.verbose:
            print ("Saving bayes database with %d spam and %d good messages" %
                   (bayes.nspam, bayes.nham))
            print " ->", self.bayes_filename
        cPickle.dump(bayes, open(self.bayes_filename,"wb"), 1)

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
            self.bayes_dirty = False
        else:
            print "Bayes database is not dirty - not writing"

    def Close(self):
        if self.mapi is not None:
            self.mapi.Logoff()
            self.mapi = None
        if self.bayes_dirty and self.bayes:
            print "Warning: BayesManager closed while Bayes database dirty"
        self.bayes = None
        self.config = None
        if self.message_store is not None:
            self.message_store.Close()
            self.message_store = None

    def score(self, msg, evidence=False):
        email = msg.GetEmailPackageObject()
        # As Tim suggested in email, score should move to range(100)
        # This is probably a good place to do it - anyone who wants the real
        # float value can look at the "clues"
        return self.bayes.spamprob(bayes_tokenize(msg), evidence)

_mgr = None

def GetManager(outlook = None, verbose=1):
    global _mgr
    if _mgr is None:
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

    def do_classify(dlg):
        import classify
        import dialogs.ClassifyDialog
        d = dialogs.ClassifyDialog.ClassifyDialog(dlg.mgr, classify.classifier)
        d.DoModal()

    def do_filter(dlg):
        import filter, rule
        import dialogs.FilterDialog
        d = dialogs.FilterDialog.FilterArrivalsDialog(dlg.mgr, rule.Rule, filter.filterer)
        d.DoModal()
        if dlg.mgr.addin is not None:
            dlg.mgr.addin.FiltersChanged()

    import dialogs.ManagerDialog
    d = dialogs.ManagerDialog.ManagerDialog(mgr, do_train, do_filter, do_classify)
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
    main(verbose)
