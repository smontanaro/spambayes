#!/usr/bin/env python

"""Concept based on Richard Jowsey's URLSlurper.java

SlurpingClassifier is a class that extends Classifier to (in some cases)
also retrieve text from (http) urls contained in messages and use that
to augment the probability calculation.

*** At the moment, this script is designed as a special instance of timtest.
(Command line arguments (like -n) are passed through to timtest).
Executing the script has the same effect as executing timtest, except that
the SlurpingClassifier class is used instead of Classifier.  This should
make testing this concept reasonably easy, without modifying the tokeniser,
classifier, or anything else.  To actually integrate this code, you would
need to replace use of the Classifier class with the SlurpingClassifier
class, and also call urlslurper.setup() if you need to set up caching or
a proxy.  If this was to be permanently added as an option, then this
information could be stored in Options.py, and this step would be
unnecessary.***

We retrieve as many urls from the message as we can find, subject to a
user-defined time limit.  Note that this time limit doesn't get checked
in the middle of retrieving a URL, so if one take a long time to get
(perhaps it times out), we might go well over the time limit.

We only slurp if:
  o The original probability is in our unsure range.
  o There were less than 'max_discriminators' clues in the original.
  o We can get some text back from the link (it hasn't timed out, for
    example).
  o The score of the retrieved text is outside our unsure range.

If the global only_slurp_base is True, then each url gets converted to its
'base' form - i.e. as simple a version as possible.  All directory
information is removed, and the domain is reduced to the two (three for
those with a country TLD) top-most elements.  This should have two
beneficial effects:
  o It's unlikely that any information could be contained in this 'base'
    url that could identify the user (unless they have a *lot* of domains).
  o Many urls (both spam and ham) will strip down into the same 'base' url.
    Since we have a limited form of caching, this means that a lot fewer
    urls will have to be retrieved.
However, this does mean that if the 'base' url is hammy and the full is
spammy, or vice-versa, that the slurp will give back the wrong information.
Whether or not this is the case would have to be determined by testing.
This defaults to False; you can set it to true with via the command line:
        -b                      Reduce URLs to simple ('base') form.

If you need to connect via an [authenicating] proxy, you can pass values
via the command line:
        -u username             Proxy username
        -p password             Proxy password
        -a host                 Address for proxy (e.g. proxy.example.com)
        -o proxy port           Port for proxy (probably 8080 or 80)

To speed things up, the result from slurping a url is cached in a pickle,
and referred to where possible.  This defaults to the file "url.pck" in
the local directory, but you can specify your own file via the command line:
        -f filename             URL cache filename

Notes:
 o There are lots of ways to get around this working.  If the site has a
   robots.txt file that excludes all robots, or all urllib robots, then
   this will fail.  If the page is just an html frame with no content,
   then this will fail.  And so on...
 o Training is only carried out on the message itself - no slurping is
   done.  This is probably as it should be.
 o At the moment, the score from classifying the webpage is averaged
   with the score from classifying the message.  It would be interesting
   to see if:
     (a) Replacing the message score with the webpage score, or
     (b) Rescoring with the message tokens and the webpage tokens
   would give better results.  (Note that with (b), the caching would not
   work, unless we cached all the tokens, not just the probs).
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
__credits__ = "Richard Jowsey, all the Spambayes folk."

from __future__ import generators

import urllib2
import sys
import re
import pickle
import os
import time

sys.path.insert(-1, os.getcwd())
sys.path.insert(-1, os.path.dirname(os.getcwd()))

from email import message_from_string
from spambayes.tokenizer import Tokenizer
from spambayes import storage
from spambayes.Options import options
from spambayes.classifier import Classifier, Bayes
from testtools import timtest
import spambayes

global cache_filename
cache_filename = "url.pck"

global proxy_info
proxy_info = {}
# Fill in the details here (and uncomment these lines) if you connect via
# a proxy and don't want to enter the details via the command line.
#proxy_info = {
#    'user' : 'username',
#    'pass' : 'password',
#    'host' : "domain name",
#    'port' : 8080  # 8080 or 80, probably
#}

global only_slurp_base
only_slurp_base = False
global url_dict
url_dict = {}

def body_tokens(msg):
    tokens = Tokenizer().tokenize_body(msg)
    for tok in tokens:
        yield tok

HTTP_RE = re.compile(r"http\://[\@\w.:~\\/\-\?\+\=]+[\w]")

class SlurpingClassifier(Classifier):
    def __init__(self):
        Classifier.__init__(self)

    def spamprob(self, wordstream, evidence=False, time_limit=None):
        global url_dict
        start_time = time.time()
        prob, clues = Classifier.spamprob(self, wordstream, True)
        if len(clues) < options["Classifier", "max_discriminators"] and \
           prob > options["Categorization", "ham_cutoff"] and \
           prob < options["Categorization", "spam_cutoff"] and \
           (time_limit is None or time.time() - start_time < time_limit):
            urls = HTTP_RE.findall(wordstream.guts)
            urlprob = 0.0
            urlclues = []
            number_urls = 0
            for url in urls:
                if only_slurp_base:
                    # to try and speed things up, and to avoid following
                    # unique URLS, we convert the url to as basic a form
                    # as we can - so http://www.massey.ac.nz/~tameyer/index.html
                    # would become http://massey.ac.nz and http://id.example.com
                    # would become http://example.com
                    url = url + '/'
                    scheme, empty, domain, garbage = url.split('/', 3)
                    parts = domain.split('.')
                    if len(parts) > 2:
                        base_domain = parts[-2] + '.' + parts[-1]
                        if len(parts[-1]) < 3:
                            base_domain = parts[-3] + '.' + base_domain
                    else:
                        base_domain = domain
                    url = scheme + "//" + base_domain
                tokens = None
                if url_dict.has_key(url):
                    urlprob += url_dict[url]
                    number_urls += 1
                else:
                    if options["globals", "verbose"]:
                        print "Slurping:", url, "..."
                    try:
                        f = urllib2.urlopen(url)
                        page = f.read()
                        f.close()
                        headers = str(f.headers)
                        page = headers + "\r\n" + page
                        if options["globals", "verbose"]:
                            print "Slurped."
                    except IOError:
                        url_dict[url] = 0.5
                        print "Couldn't get", url
                    if not url_dict.has_key(url) or url_dict[url] != 0.5:
                        # Create a fake Message object since Tokenizer is
                        # designed to deal with them.
                        msg = message_from_string(page)
                        # Although we have a message object with headers
                        # (kindly provided by urllib2), the headers won't
                        # match those that we have trained against (unless
                        # we start training with slurping as well), so
                        # we only tokenise the *body*.
                        uprob = Classifier.spamprob(self, body_tokens(msg))
                        urlprob += uprob
                        number_urls += 1
                        url_dict[url] = uprob
            if number_urls > 0 and \
               (urlprob < options["Categorization", "ham_cutoff"] or \
                urlprob > options["Categorization", "spam_cutoff"]):
                prob = (prob + (urlprob / number_urls)) / 2
        # Save the url dict so we don't continually slurp the same urls
        # The problem here, of course, is that we save the probability that
        # the current database gives us.  If we do more/different training
        # later, this probability might not still be accurate.  We should
        # either:
        #   (a) Not do any caching,
        #   (b) Cache the tokens (needs lots of space!) not the prob, or
        #   (c) Tag the probability with a date, and after x time has
        #       passed, expire old probabilities.
        f = file(cache_filename, "w")
        pickle.dump(url_dict, f)
        f.close()
        if evidence:
            return prob, clues
        return prob

def setup(proxy={}, filename=None):
    if len(proxy) > 0:
        # build a new opener that uses a proxy requiring authorization
        proxy_support = urllib2.ProxyHandler({"http" :
                        "http://%(user)s:%(pass)s@%(host)s:%(port)d" % proxy})
        opener = urllib2.build_opener(proxy_support, urllib2.HTTPHandler)
    else:
        # Build a new opener without any proxy information.
        opener = urllib2.build_opener(urllib2.HTTPHandler)
     
    # install it
    urllib2.install_opener(opener)

    # read any url cache    
    if os.path.exists(filename):
        f = file(filename, "r")
        url_dict = pickle.load(f)
        f.close()

 
if __name__ == "__main__":
    import getopt
    from spambayes import msgs

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hbu:p:a:o:f:n:s:',
                                   ['ham-keep=', 'spam-keep='])
    except getopt.error, msg:
        print >>sys.stderr, __doc__
        sys.exit()

    nsets = seed = hamkeep = spamkeep = None
    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-u':
            global proxy_info
            proxy_info["user"] = arg
        elif opt == '-p':
            global proxy_info
            proxy_info["pass"] = arg
        elif opt == '-a':
            global proxy_info
            proxy_info["host"] = arg
        elif opt == '-o':
            global proxy_info
            proxy_info["port"] = int(arg)
        elif opt == '-f':
            global cache_filename
            cache_filename = arg
        elif opt == '-b':
            global only_slurp_base
            only_slurp_base = True
        # from timtest.py
        elif opt == '-n':
            nsets = int(arg)
        elif opt == '-s':
            seed = int(arg)
        elif opt == '--ham-keep':
            hamkeep = int(arg)
        elif opt == '--spam-keep':
            spamkeep = int(arg)

    setup(proxy_info, cache_filename)
    spambayes.classifier.Bayes = SlurpingClassifier

    if nsets is None:
        timtest.usage(1, "-n is required")

    msgs.setparms(hamkeep, spamkeep, seed=seed)
    timtest.drive(nsets)
