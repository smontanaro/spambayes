#!/usr/bin/env python

"""
Proxy class used to insert Spambayes training between two Postfix servers.

For details, see <http://www.postfix.org/SMTPD_PROXY_README.html>.
"""

import os
# This module is generally going to be imported from smtpd which will be run
# as the main program and thus be named __main__.  Importing smtpd directly
# will override any global object definitions.  In particular, the
# DEBUGSTREAM setting might get hosed.
import __main__ as smtpd
if not hasattr(smtpd, "PureProxy"):
    import smtpd

import time
import email.Parser
from spambayes import Options, hammie, storage

__all__ = ['SpambayesProxy']

# stolen from sb_filter.py
# XXX should probably be enhanced to select training database based upon
# message recipients, but let's see how far a single database gets us.
class HammieFilter(object):
    def __init__(self):
        options = Options.options
        # This is a bit of a hack to counter the default for
        # persistent_storage_file changing from ~/.hammiedb to hammie.db
        # This will work unless a user:
        #   * had hammie.db as their value for persistent_storage_file, and
        #   * their config file was loaded by Options.py.
        if options["Storage", "persistent_storage_file"] == \
           options.default("Storage", "persistent_storage_file"):
            options["Storage", "persistent_storage_file"] = \
                                    "~/.hammiedb"
        options.merge_files(['/etc/hammierc',
                            os.path.expanduser('~/.hammierc')])
        self.dbname, self.usedb = storage.database_type([])
        self.modtime = os.path.getmtime(self.dbname)
        self.h = None

    def open(self):
        mtime = os.path.getmtime(self.dbname)
        if self.h is None or self.modtime < mtime:
            self.h = hammie.open(self.dbname, self.usedb, 'r')
            self.modtime = mtime

    def __del__(self):
        self.h = None

    def score_and_filter(self, msg):
        self.open()
        return self.h.score_and_filter(msg)

class SpambayesProxy(smtpd.PureProxy):
    def __init__(self, *args, **kwds):
        smtpd.PureProxy.__init__(self, *args, **kwds)
        self.h = HammieFilter()
        self.spam_cutoff = Options.options["Categorization", "spam_cutoff"]

    def log_message(self, data):
        """log message to unix mbox for later review"""
        # XXX where should we log it?
        pass

    def process_message(self, peer, mailfrom, rcpttos, data):
        t1 = time.time()
        try:
            msg = email.Parser.Parser().parsestr(data)
        except:
            pass
        else:
            t2 = time.time()
            msg.add_header("X-Peer", peer[0])
            prob, data = self.h.score_and_filter(msg)
            t3 = time.time()
            try:
                if prob >= self.spam_cutoff:
                    self.log_message(data)
                    print >> smtpd.DEBUGSTREAM, 'probable spam: %.2f' % prob
                    return '503 Error: probable spam'

                refused = self._deliver(mailfrom, rcpttos, data)
                t4 = time.time()
                # TBD: what to do with refused addresses?
                print >> smtpd.DEBUGSTREAM, 'we got some refusals:', refused
                print >> smtpd.DEBUGSTREAM, 'deliver time:', t4-t3
            finally:
                print >> smtpd.DEBUGSTREAM, 'parse time:', t2-t1
                print >> smtpd.DEBUGSTREAM, 'score time:', t3-t2
