from __future__ import generators

import cPickle
import os
import sys
import thread

import classifier
from tokenizer import tokenize
import win32com.client
import win32com.client.gencache
import pythoncom

# Suck in CDO type lib
win32com.client.gencache.EnsureModule('{3FA7DEA7-6438-101B-ACC1-00AA00423326}', 0, 1, 21, bForDemand = True)

try:
    this_filename = __file__
except NameError:
    this_filename = sys.argv[0]

class ManagerError(Exception):
    pass

class BayesManager:
    def __init__(self, config_base="default", outlook=None, verbose=True):
        self.verbose = verbose
        if not os.path.isabs(config_base):
            config_base = os.path.join( os.path.dirname(this_filename), config_base)
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
        self._tls = {thread.get_ident(): {"outlook": outlook} }
        self.outlook = outlook
        os.chdir(cwd)

        self.LoadBayes()

    # Outlook gives us thread grief :(
    def WorkerThreadStarting(self):
        pythoncom.CoInitialize()
        self._tls[thread.get_ident()] = {}

    def WorkerThreadEnding(self):
        assert self._tls.has_key(thread.get_ident()), "WorkerThreadStarting hasn't been called for this thread"
        del self._tls[thread.get_ident()]
        pythoncom.CoUninitialize()

    def GetOutlookForCurrentThread(self):
        assert self._tls.has_key(thread.get_ident()), "WorkerThreadStarting hasn't been called for this thread"
        existing = self._tls[thread.get_ident()].get("outlook")
        if not existing:
            existing = win32com.client.Dispatch("Outlook.Application")
            self._tls[thread.get_ident()]["outlook"] = existing
        return existing

    def LoadBayes(self):
        if not os.path.exists(self.ini_filename):
            raise ManagerError("The file '%s' must exist before the database '%s' can be opened or created" % (self.ini_filename, self.bayes_filename))
        bayes = None
        try:
            bayes = cPickle.load(open(self.bayes_filename,'rb'))
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
            print "Bayes database initialized with %d spam and %d good messages" % (bayes.nspam, bayes.nham)
        self.bayes = bayes
        self.bayes_dirty = False

    def LoadConfig(self):
        try:
            ret = cPickle.load(open(self.config_filename,'rb'))
            if self.verbose > 1:
                print "Loaded configuration from '%s':" % (self.config_filename,)
                ret._dump()
        except (AttributeError, ImportError):
            ret = _ConfigurationRoot()
            if self.verbose > 1:
                print "FAILED to load configuration from '%s - using default:" % (self.config_filename,)
                import traceback
                traceback.print_exc()
        return ret

    def InitNewBayes(self):
        os.environ["BAYESCUSTOMIZE"]=self.ini_filename
        self.bayes = classifier.Bayes()
        self.bayes_dirty = True

    def SaveBayes(self):
        bayes = self.bayes
        if self.verbose:
            print "Saving bayes database with %d spam and %d good messages" % (bayes.nspam, bayes.nham)
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
        self._tls = None

    def BuildFolderList(self, folder_ids, include_sub):
        ret = {}
        for id in folder_ids:
            subs = []
            try:
                f = self.mapi.GetFolder(id)
                if include_sub:
                    sub_ids = []
                    subs = f.Folders
                    for i in range(1, subs.Count):
                        sub_ids.append(subs.Item(i).ID)
                    subs = self.BuildFolderList(sub_ids, True)
            except pythoncom.error:
                continue
            ret[id] = f
            for sub in subs:
                ret[sub.ID] = sub
        return ret.values()

    def YieldMessageList(self, folder):
        messages = folder.Messages
        if not messages:
            print "Can't find messages in folder '%s'" % (folder.Name,)
            return
        message = messages.GetFirst()
        while message is not None:
            yield message
            message = messages.GetNext()

# configuration stuff we persist.
class _ConfigurationContainer:
    def __init__(self, **kw):
        self.__dict__.update(kw)
    def __setstate__(self, state):
        self.__init__() # ensure any new/default values setup
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

class _ConfigurationRoot(_ConfigurationContainer):
    def __init__(self):
        self.training = _ConfigurationContainer(
            ham_folder_ids = [],
            ham_include_sub = False,
            spam_folder_ids = [],
            spam_include_sub = False,
            )
        self.classify = _ConfigurationContainer(
            folder_ids = [],
            include_sub = False,
            field_name = "SpamProb",
            )
        self.filter = _ConfigurationContainer(
            folder_ids = [],
            include_sub = False,
            )
        self.filter_now = _ConfigurationContainer(
            folder_ids = [],
            include_sub = False,
            only_unread = False,
            )
        self.rules = []


_mgr = None

def GetManager():
    global _mgr
    if _mgr is None:
        _mgr = BayesManager()
    return _mgr

if __name__=='__main__':
    try:
        mgr = BayesManager()
    except ManagerError, d:
        print "Error initializing Bayes manager"
        print d
