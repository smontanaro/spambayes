from __future__ import generators

import cPickle
import os
import sys
import thread

import win32com.client
import win32com.client.gencache
import pythoncom

import config

try:
    this_filename = os.path.abspath(__file__)
except NameError:
    this_filename = os.path.abspath(sys.argv[0])

# This is a little of a hack <wink>.  We are generally in a child directory of the
# bayes code.  To help installation, we handle the fact that this may not be
# on sys.path.
try:
    import classifier
except ImportError:
    parent = os.path.abspath(os.path.join(os.path.dirname(this_filename), ".."))
    sys.path.insert(0, parent)
    del parent
    import classifier

import hammie

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
        self._tls = {thread.get_ident(): {"outlook": outlook} }
        self.outlook = outlook
        os.chdir(cwd)

        self.LoadBayes()

    # Outlook gives us thread grief :(
    def WorkerThreadStarting(self):
        pythoncom.CoInitialize()
        self._tls[thread.get_ident()] = {}

    def WorkerThreadEnding(self):
        assert self._tls.has_key(thread.get_ident()), \
               "WorkerThreadStarting hasn't been called for this thread"
        del self._tls[thread.get_ident()]
        pythoncom.CoUninitialize()

    def GetOutlookForCurrentThread(self):
        assert self._tls.has_key(thread.get_ident()), \
               "WorkerThreadStarting hasn't been called for this thread"
        existing = self._tls[thread.get_ident()].get("outlook")
        if not existing:
            existing = win32com.client.Dispatch("Outlook.Application")
            self._tls[thread.get_ident()]["outlook"] = existing
        return existing

    def GetBayesStreamForMessage(self, message):
        # Note - caller must catch COM error
        import email

        headers = message.Fields[0x7D001E].Value
        headers = headers.encode('ascii', 'replace')
        try:
            body = message.Fields[0x1013001E].Value # HTMLBody field
            body = body.encode("ascii", "replace") + "\n"
        except pythoncom.error:
            body = ""
        body += message.Text.encode("ascii", "replace")

        # XXX If this was originally a MIME msg, we're hosed at this point --
        # the boundary tag in the headers doesn't exist in the body, and
        # the msg is simply ill-formed.  The miserable hack here simply
        # squashes the text part (if any) and the HTML part (if any) together,
        # and strips MIME info from the original headers.
        msg = email.message_from_string(headers + '\n' + body)
        if msg.has_key('content-type'):
            del msg['content-type']
        if msg.has_key('content-transfer-encoding'):
            del msg['content-transfer-encoding']
        return msg

    def LoadBayes(self):
        if not os.path.exists(self.ini_filename):
            raise ManagerError("The file '%s' must exist before the "
                               "database '%s' can be opened or created" % (
                               self.ini_filename, self.bayes_filename))
        bayes = None
        try:
            os.environ["BAYESCUSTOMIZE"]=self.ini_filename
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
            print ("Bayes database initialized with "
                   "%d spam and %d good messages" % (bayes.nspam, bayes.nham))
        self.bayes = bayes
        self.bayes_dirty = False

    def MakeHammie(self):
        return hammie.Hammie(self.bayes)

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
        os.environ["BAYESCUSTOMIZE"]=self.ini_filename
        self.bayes = classifier.Bayes()
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

_mgr = None

def GetManager(verbose=1):
    global _mgr
    if _mgr is None:
        _mgr = BayesManager(verbose=verbose)
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
