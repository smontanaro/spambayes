# Options.options is a globally shared options object.

# XXX As this code is, option names must be unique across ini sections,
# XXX and must not conflict with OptionsClass method names.

import sys, os
import StringIO
import ConfigParser
from sets import Set

__all__ = ['options']

defaults = """
[Tokenizer]
# If true, tokenizer.Tokenizer.tokenize_headers() will tokenize the
# contents of each header field just like the text of the message
# body, using the name of the header as a tag.  Tokens look like
# "header:word".  The basic approach is simple and effective, but also
# very sensitive to biases in the ham and spam collections.  For
# example, if the ham and spam were collected at different times,
# several headers with date/time information will become the best
# discriminators.  (Not just Date, but Received and X-From_.)
basic_header_tokenize: False

# If true and basic_header_tokenize is also true, then
# basic_header_tokenize is the only action performed.
basic_header_tokenize_only: False

# If basic_header_tokenize is true, then basic_header_skip is a set of
# headers that should be skipped.
basic_header_skip: received
    date
    x-.*

# If false, tokenizer.Tokenizer.tokenize_body() strips HTML tags
# from pure text/html messages.  Set true to retain HTML tags in this
# case.  On the c.l.py corpus, it helps to set this true because any
# sign of HTML is so despised on tech lists; however, the advantage
# of setting it true eventually vanishes even there given enough
# training data.  If you set this true, you should almost certainly set
# ignore_redundant_html true too.
retain_pure_html_tags: False

# If true, when a multipart/alternative has both text/plain and text/html
# sections, the text/html section is ignored.  That's likely a dubious
# idea in general, so false is likely a better idea here.  In the c.l.py
# tests, it helped a lot when retain_pure_html_tags was true (in that case,
# keeping the HTML tags in the "redundant" HTML was almost certain to score
# the multipart/alternative as spam, regardless of content).
ignore_redundant_html: False

# If true, the first few characters of application/octet-stream sections
# are used, undecoded.  What 'few' means is decided by octet_prefix_size.
check_octets: False
octet_prefix_size: 5

# Generate tokens just counting the number of instances of each kind of
# header line, in a case-sensitive way.
#
# Depending on data collection, some headers aren't safe to count.
# For example, if ham is collected from a mailing list but spam from your
# regular inbox traffic, the presence of a header like List-Info will be a
# very strong ham clue, but a bogus one.  In that case, set
# count_all_header_lines to False, and adjust safe_headers instead.

count_all_header_lines: False

# Like count_all_header_lines, but restricted to headers in this list.
# safe_headers is ignored when count_all_header_lines is true.

safe_headers: abuse-reports-to
    date
    errors-to
    from
    importance
    in-reply-to
    message-id
    mime-version
    organization
    received
    reply-to
    return-path
    subject
    to
    user-agent
    x-abuse-info
    x-complaints-to
    x-face

# A lot of clues can be gotten from IP addresses and names in Received:
# headers.  Again this can give spectacular results for bogus reasons
# if your test corpora are from different sources.  Else set this to true.
mine_received_headers: False

[TestDriver]
# These control various displays in class TestDriver.Driver, and Tester.Test.

# A message is considered spam iff it scores greater than spam_cutoff.
# This is corpus-dependent, and values into the .600's have been known
# to work best on some data.
spam_cutoff: 0.570

# Number of buckets in histograms.
nbuckets: 40
show_histograms: True

# After the display of a ham+spam histogram pair, you can get a listing of
# all the cutoff values (coinciding histogram bucket boundaries) that
# minimize
#
#      best_cutoff_fp_weight * (# false positives) + (# false negatives)
#
# By default, best_cutoff_fp_weight is 1, and so the cutoffs that miminize
# the total number of misclassified messages (fp+fn) are shown.  If you hate
# fp more than fn, set the weight to something larger than 1.  For example,
# if you're willing to endure 100 false negatives to save 1 false positive,
# set it to 100.
# Note:  You may wish to increase nbuckets, to give this scheme more cutoff
# values to analyze.
compute_best_cutoffs_from_histograms: True
best_cutoff_fp_weight: 1

# Display spam when
#     show_spam_lo <= spamprob <= show_spam_hi
# and likewise for ham.  The defaults here don't show anything.
show_spam_lo: 1.0
show_spam_hi: 0.0
show_ham_lo: 1.0
show_ham_hi: 0.0

show_false_positives: True
show_false_negatives: False

# Near the end of Driver.test(), you can get a listing of the 'best
# discriminators' in the words from the training sets.  These are the
# words whose WordInfo.killcount values are highest, meaning they most
# often were among the most extreme clues spamprob() found.  The number
# of best discriminators to show is given by show_best_discriminators;
# set this <= 0 to suppress showing any of the best discriminators.
show_best_discriminators: 30

# The maximum # of characters to display for a msg displayed due to the
# show_xyz options above.
show_charlimit: 3000

# If save_trained_pickles is true, Driver.train() saves a binary pickle
# of the classifier after training.  The file basename is given by
# pickle_basename, the extension is .pik, and increasing integers are
# appended to pickle_basename.  By default (if save_trained_pickles is
# true), the filenames are class1.pik, class2.pik, ...  If a file of that
# name already exists, it's overwritten.  pickle_basename is ignored when
# save_trained_pickles is false.

# if save_histogram_pickles is true, Driver.train() saves a binary
# pickle of the spam and ham histogram for "all test runs". The file
# basename is given by pickle_basename, the suffix _spamhist.pik
# or _hamhist.pik is appended  to the basename.

save_trained_pickles: False
pickle_basename: class
save_histogram_pickles: False

# default locations for timcv and timtest - these get the set number
# interpolated.
spam_directories: Data/Spam/Set%d
ham_directories: Data/Ham/Set%d

[Classifier]
# The maximum number of extreme words to look at in a msg, where "extreme"
# means with spamprob farthest away from 0.5.  150 appears to work well
# across all corpora tested.
max_discriminators: 150

# These two control the prior assumption about word probabilities.
# "x" is essentially the probability given to a word that's never been
# seen before.  Nobody has reported an improvement via moving it away
# from 1/2.
# "s" adjusts how much weight to give the prior assumption relative to
# the probabilities estimated by counting.  At s=0, the counting estimates
# are believed 100%, even to the extent of assigning certainty (0 or 1)
# to a word that's appeared in only ham or only spam.  This is a disaster.
# As s tends toward infintity, all probabilities tend toward x.  All
# reports were that a value near 0.4 worked best, so this doesn't seem to
# be corpus-dependent.
# NOTE:  Gary Robinson previously used a different formula involving 'a'
# and 'x'.  The 'x' here is the same as before.  The 's' here is the old
# 'a' divided by 'x'.
robinson_probability_x: 0.5
robinson_probability_s: 0.45

# When scoring a message, ignore all words with
# abs(word.spamprob - 0.5) < robinson_minimum_prob_strength.
# This may be a hack, but it has proved to reduce error rates in many
# tests over Robinson's base scheme.  0.1 appeared to work well across
# all corpora.
robinson_minimum_prob_strength: 0.1

# There's a strange asymmetry in the scheme, where multiple occurrences of
# a word in a msg are ignored during scoring, but all add to the spamcount
# (or hamcount) during training.  This imbalance couldn't be altered without
# hurting results under the Graham scheme, but it may well be better to
# treat things the same way during training under the Robinson schems.  Set
# this to true to try that.
# NOTE:  In Tim's tests this decreased both the ham and spam mean scores,
# the former more than the latter.  Therefore you'll probably want a smaller
# spam_cutoff value when this is enabled.
count_duplicates_only_once_in_training: False

###########################################################################
# Speculative options for Gary Robinson's central-limit ideas.  These may go
# away, or a bunch of incompatible stuff above may go away.

# Use a central-limit approach for scoring.
# The number of extremes to use is given by max_discriminators (above).
# spam_cutoff should almost certainly be exactly 0.5 when using this approach.
# DO NOT run cross-validation tests when this is enabled!  They'll deliver
# nonense, or, if you're lucky, will blow up with division by 0 or negative
# square roots.  An NxN test grid should work fine.
use_central_limit: False

# Same as use_central_limit, except takes logarithms of probabilities and
# probability complements (p and 1-p) instead.
use_central_limit2: False
"""

int_cracker = ('getint', None)
float_cracker = ('getfloat', None)
boolean_cracker = ('getboolean', bool)
string_cracker = ('get', None)

all_options = {
    'Tokenizer': {'retain_pure_html_tags': boolean_cracker,
                  'ignore_redundant_html': boolean_cracker,
                  'safe_headers': ('get', lambda s: Set(s.split())),
                  'count_all_header_lines': boolean_cracker,
                  'mine_received_headers': boolean_cracker,
                  'check_octets': boolean_cracker,
                  'octet_prefix_size': int_cracker,
                  'basic_header_tokenize': boolean_cracker,
                  'basic_header_tokenize_only': boolean_cracker,
                  'basic_header_skip': ('get', lambda s: Set(s.split())),
                 },
    'TestDriver': {'nbuckets': int_cracker,
                   'show_ham_lo': float_cracker,
                   'show_ham_hi': float_cracker,
                   'show_spam_lo': float_cracker,
                   'show_spam_hi': float_cracker,
                   'show_false_positives': boolean_cracker,
                   'show_false_negatives': boolean_cracker,
                   'show_histograms': boolean_cracker,
                   'show_best_discriminators': int_cracker,
                   'save_trained_pickles': boolean_cracker,
                   'save_histogram_pickles': boolean_cracker,
                   'pickle_basename': string_cracker,
                   'show_charlimit': int_cracker,
                   'spam_cutoff': float_cracker,
                   'spam_directories': string_cracker,
                   'ham_directories': string_cracker,
                   'compute_best_cutoffs_from_histograms': boolean_cracker,
                   'best_cutoff_fp_weight': float_cracker,
                  },
    'Classifier': {'max_discriminators': int_cracker,
                   'robinson_probability_x': float_cracker,
                   'robinson_probability_s': float_cracker,
                   'robinson_minimum_prob_strength': float_cracker,
                   'count_duplicates_only_once_in_training': boolean_cracker,

                   'use_central_limit': boolean_cracker,
                   'use_central_limit2': boolean_cracker,
                   },
}

def _warn(msg):
    print >> sys.stderr, msg

class OptionsClass(object):
    def __init__(self):
        self._config = ConfigParser.ConfigParser()

    def mergefiles(self, fnamelist):
        self._config.read(fnamelist)
        self._update()

    def mergefilelike(self, filelike):
        self._config.readfp(filelike)
        self._update()

    def _update(self):
        nerrors = 0
        c = self._config
        for section in c.sections():
            if section not in all_options:
                _warn("config file has unknown section %r" % section)
                nerrors += 1
                continue
            goodopts = all_options[section]
            for option in c.options(section):
                if option not in goodopts:
                    _warn("config file has unknown option %r in "
                         "section %r" % (option, section))
                    nerrors += 1
                    continue
                fetcher, converter = goodopts[option]
                value = getattr(c, fetcher)(section, option)
                if converter is not None:
                    value = converter(value)
                setattr(options, option, value)
        if nerrors:
            raise ValueError("errors while parsing .ini file")

    def display(self):
        output = StringIO.StringIO()
        self._config.write(output)
        return output.getvalue()

options = OptionsClass()

d = StringIO.StringIO(defaults)
options.mergefilelike(d)
del d

alternate = os.getenv('BAYESCUSTOMIZE')
if alternate:
    options.mergefiles(alternate.split())
else:
    options.mergefiles(['bayescustomize.ini'])
