##
## This is a simple Spambayes plugin for Amit Patel's proxy3 web proxy:
##    http://theory.stanford.edu/~amitp/proxy.html
##
## Author: Skip Montanaro <skip@pobox.com>
##

import os

from proxy3_filter import *
import proxy3_options

from spambayes import hammie, Options, mboxutils
dbf = os.path.expanduser(Options.options.hammiefilter_persistent_storage_file)

class SpambayesFilter(BufferAllFilter):
    hammie = hammie.open(dbf, 1, 'r')

    def filter(self, s):
        if self.reply.split()[1] == '200':
            prob = self.hammie.score("%s\r\n%s" % (self.serverheaders, s))
            print "|  prob: %.5f" % prob
            if prob >= Options.options.spam_cutoff:
                print self.serverheaders
                print "text:", s[0:40], "...", s[-40:]
                return "not authorized"
       return s

from proxy3_util import *

register_filter('*/*', 'text/html', SpambayesFilter)
