# Options.options is a globally shared options object.

# XXX As this code is, option names must be unique across ini sections,
# XXX and must not conflict with OptionsClass method names.

import sys, os
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import ConfigParser
try:
    from sets import Set
except ImportError:
    from spambayes.compatsets import Set


try:
    True, False, bool
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0
    def bool(val):
        return not not val

import re

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

# If true, the first few characters of application/octet-stream sections
# are used, undecoded.  What 'few' means is decided by octet_prefix_size.
check_octets: False
octet_prefix_size: 5

# Generate tokens just counting the number of instances of each kind of
# header line, in a case-sensitive way.
#
# Depending on data collection, some headers are not safe to count.
# For example, if ham is collected from a mailing list but spam from your
# regular inbox traffic, the presence of a header like List-Info will be a
# very strong ham clue, but a bogus one.  In that case, set
# count_all_header_lines to False, and adjust safe_headers instead.
count_all_header_lines: False

# When True, generate a "noheader:HEADERNAME" token for each header in
# safe_headers (below) that *doesn't* appear in the headers.  This helped
# in various of Tim's python.org tests, but appeared to hurt a little in
# Anthony Baxter's tests.
record_header_absence: False

# Like count_all_header_lines, but restricted to headers in this list.
# safe_headers is ignored when count_all_header_lines is true, unless
# record_header_absence is also true.
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

# Mine the following address headers. If you have mixed source corpuses
# (as opposed to a mixed sauce walrus, which is delicious!) then you
# probably don't want to use 'to' or 'cc')
# Address headers will be decoded, and will generate charset tokens as
# well as the real address.
# others to consider: to, cc, reply-to, errors-to, sender, ...
address_headers: from

# If legitimate mail contains things that look like text to the tokenizer
# and turning turning off this option helps (perhaps binary attachments get
# 'defanged' by something upstream from this operation and thus look like
# text), this may help, and should be an alert that perhaps the tokenizer is
# broken.
generate_long_skips: True

# Try to capitalize on mail sent to multiple similar addresses.
summarize_email_prefixes: False
summarize_email_suffixes: False

#
# Length of words that triggers 'long skips'. Longer than this
# triggers a skip.
#
skip_max_word_size: 12

# Generate tokens which resemble the posting time in 10-minute buckets:
#     'time:'  hour  ':'  minute//10
generate_time_buckets: False

# Extract day of the week tokens from the Date: header.
extract_dow: False

# If true, replace high-bit characters (ord(c) >= 128) and control characters
# with question marks.  This allows non-ASCII character strings to be
# identified with little training and small database burden.  It's appropriate
# only if your ham is plain 7-bit ASCII, or nearly so, so that the mere
# presence of non-ASCII character strings is known in advance to be a strong
# spam indicator.
replace_nonascii_chars: False

[Categorization]
# These options control how a message is categorized

# spam_cutoff and ham_cutoff are used in Python slice sense:
#    A msg is considered    ham if its score is in 0:ham_cutoff
#    A msg is considered unsure if its score is in ham_cutoff:spam_cutoff
#    A msg is considered   spam if its score is in spam_cutoff:
#
# So it's unsure iff  ham_cutoff <= score < spam_cutoff.
# For a binary classifier, make ham_cutoff == spam_cutoff.
# ham_cutoff > spam_cutoff doesn't make sense.
#
# The defaults here (.2 and .9) may be appropriate for the default chi-
# combining scheme.  Cutoffs for chi-combining typically aren't touchy,
# provided you're willing to settle for "really good" instead of "optimal".
# Tim found that .3 and .8 worked very well for well-trained systems on
# his personal email, and his large comp.lang.python test.  If just beginning
# training, or extremely fearful of mistakes, 0.05 and 0.95 may be more
# appropriate for you.
#
# Picking good values for gary-combining is much harder, and appears to be
# corpus-dependent, and within a single corpus dependent on how much
# training has been done.  Values from 0.50 thru the low 0.60's have been
# reported to work best by various testers on their data.
ham_cutoff:  0.20
spam_cutoff: 0.90

[TestDriver]
# These control various displays in class TestDriver.Driver, and Tester.Test.


# Number of buckets in histograms.
nbuckets: 200
show_histograms: True

# After the display of a ham+spam histogram pair, you can get a listing of
# all the cutoff values (coinciding with histogram bucket boundaries) that
# minimize
#
#      best_cutoff_fp_weight * (# false positives) +
#      best_cutoff_fn_weight * (# false negatives) +
#      best_cutoff_unsure_weight * (# unsure msgs)
#
# This displays two cutoffs:  hamc and spamc, where
#
#     0.0 <= hamc <= spamc <= 1.0
#
# The idea is that if something scores < hamc, it's called ham; if
# something scores >= spamc, it's called spam; and everything else is
# called 'I am not sure' -- the middle ground.
#
# Note:  You may wish to increase nbuckets, to give this scheme more cutoff
# values to analyze.
compute_best_cutoffs_from_histograms: True
best_cutoff_fp_weight:     10.00
best_cutoff_fn_weight:      1.00
best_cutoff_unsure_weight:  0.20

# Histogram analysis also displays percentiles.  For each percentile p
# in the list, the score S such that p% of all scores are <= S is given.
# Note that percentile 50 is the median, and is displayed (along with the
# min score and max score) independent of this option.
percentiles: 5 25 75 95

# Display spam when
#     show_spam_lo <= spamprob <= show_spam_hi
# and likewise for ham.  The defaults here do not show anything.
show_spam_lo: 1.0
show_spam_hi: 0.0
show_ham_lo: 1.0
show_ham_hi: 0.0

show_false_positives: True
show_false_negatives: False
show_unsure: False

# The maximum # of characters to display for a msg displayed due to the
# show_xyz options above.
show_charlimit: 3000

# If save_trained_pickles is true, Driver.train() saves a binary pickle
# of the classifier after training.  The file basename is given by
# pickle_basename, the extension is .pik, and increasing integers are
# appended to pickle_basename.  By default (if save_trained_pickles is
# true), the filenames are class1.pik, class2.pik, ...  If a file of that
# name already exists, it is overwritten.  pickle_basename is ignored when
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

[CV Driver]
# A cross-validation driver takes N ham+spam sets, and builds N classifiers,
# training each on N-1 sets, and the predicting against the set not trained
# on.  By default, it does this in a clever way, learning *and* unlearning
# sets as it goes along, so that it never needs to train on N-1 sets in one
# gulp after the first time.  Setting this option true forces ''one gulp
# from-scratch'' training every time.  There used to be a set of combining
# schemes that needed this, but now it is just in case you are paranoid <wink>.
build_each_classifier_from_scratch: False

[Classifier]
# The maximum number of extreme words to look at in a msg, where "extreme"
# means with spamprob farthest away from 0.5.  150 appears to work well
# across all corpora tested.
max_discriminators: 150

# These two control the prior assumption about word probabilities.
# unknown_word_prob is essentially the probability given to a word that
# has never been seen before.  Nobody has reported an improvement via moving
# it away from 1/2, although Tim has measured a mean spamprob of a bit over
# 0.5 (0.51-0.55) in 3 well-trained classifiers.
#
# unknown_word_strength adjusts how much weight to give the prior assumption
# relative to the probabilities estimated by counting.  At 0, the counting
# estimates are believed 100%, even to the extent of assigning certainty
# (0 or 1) to a word that has appeared in only ham or only spam.  This
# is a disaster.
#
# As unknown_word_strength tends toward infintity, all probabilities tend
# toward unknown_word_prob.  All reports were that a value near 0.4 worked
# best, so this does not seem to be corpus-dependent.
unknown_word_prob: 0.5
unknown_word_strength: 0.45

# When scoring a message, ignore all words with
# abs(word.spamprob - 0.5) < minimum_prob_strength.
# This may be a hack, but it has proved to reduce error rates in many
# tests.  0.1 appeared to work well across all corpora.
minimum_prob_strength: 0.1

# The combining scheme currently detailed on the Robinon web page.
# The middle ground here is touchy, varying across corpus, and within
# a corpus across amounts of training data.  It almost never gives extreme
# scores (near 0.0 or 1.0), but the tail ends of the ham and spam
# distributions overlap.
use_gary_combining: False

# For vectors of random, uniformly distributed probabilities, -2*sum(ln(p_i))
# follows the chi-squared distribution with 2*n degrees of freedom.  This is
# the "provably most-sensitive" test the original scheme was monotonic
# with.  Getting closer to the theoretical basis appears to give an excellent
# combining method, usually very extreme in its judgment, yet finding a tiny
# (in # of msgs, spread across a huge range of scores) middle ground where
# lots of the mistakes live.  This is the best method so far.
# One systematic benefit is is immunity to "cancellation disease".  One
# systematic drawback is sensitivity to *any* deviation from a
# uniform distribution, regardless of whether actually evidence of
# ham or spam.  Rob Hooft alleviated that by combining the final S and H
# measures via (S-H+1)/2 instead of via S/(S+H)).
# In practice, it appears that setting ham_cutoff=0.05, and spam_cutoff=0.95,
# does well across test sets; while these cutoffs are rarely optimal, they
# get close to optimal.  With more training data, Tim has had good luck
# with ham_cutoff=0.30 and spam_cutoff=0.80 across three test data sets
# (original c.l.p data, his own email, and newer general python.org traffic).
use_chi_squared_combining: True

# If the # of ham and spam in training data are out of balance, the
# spamprob guesses can get stronger in the direction of the category with
# more training msgs.  In one sense this must be so, since the more data
# we have of one flavor, the more we know about that flavor.  But that
# allows the accidental appearance of a strong word of that flavor in a msg
# of the other flavor much more power than an accident in the other
# direction.  Enable experimental_ham_spam_imbalance_adjustment if you have
# more ham than spam training data (or more spam than ham), and the
# Bayesian probability adjustment won't 'believe' raw counts more than
# min(# ham trained on, # spam trained on) justifies.  I *expect* this
# option will go away (and become the default), but people *with* strong
# imbalance need to test it first.
experimental_ham_spam_imbalance_adjustment: False

[Hammie]
# The name of the header that hammie adds to an E-mail in filter mode
# It contains the "classification" of the mail, plus the score.
hammie_header_name: X-Spambayes-Classification

# The three disposition names are added to the header as the following
# Three words:
header_spam_string: spam
header_ham_string: ham
header_unsure_string: unsure

# Accuracy of the score in the header in decimal digits
header_score_digits: 2

# Set this to "True", to augment scores of 1.00 or 0.00 by a logarithmic
# "one-ness" or "zero-ness" score (basically it shows the "number of zeros"
# or "number of nines" next to the score value).
header_score_logarithm: False

# Enable debugging information in the header.
hammie_debug_header: False

# Name of a debugging header for spambayes hackers, showing the strongest
# clues that have resulted in the classification in the standard header.
hammie_debug_header_name: X-Spambayes-Debug

# Train when filtering?  After filtering a message, hammie can then
# train itself on the judgement (ham or spam).  This can speed things up
# with a procmail-based solution.  If you do enable this, please make
# sure to retrain any mistakes.  Otherwise, your word database will
# slowly become useless.
hammie_train_on_filter: False

# When training on a message, the name of the header to add with how it
# was trained
hammie_trained_header: X-Spambayes-Trained

# The range of clues that are added to the "debug" header in the E-mail
# All clues that have their probability smaller than this number, or larger
# than one minus this number are added to the header such that you can see
# why spambayes thinks this is ham/spam or why it is unsure. The default is
# to show all clues, but you can reduce that by setting showclue to a lower
# value, such as 0.1
clue_mailheader_cutoff: 0.5

[hammiefilter]
# hammiefilter can use either a database (quick to score one message) or
# a pickle (quick to train on huge amounts of messages). Set this to
# True to use a database by default.
hammiefilter_persistent_use_database: True
hammiefilter_persistent_storage_file: ~/.hammiedb

[pop3proxy]
# pop3proxy settings - pop3proxy also respects the options in the Hammie
# section, with the exception of the extra header details at the moment.
# The only mandatory option is pop3proxy_servers, eg. "pop3.my-isp.com:110",
# or a comma-separated list of those.  The ":110" is optional.  If you
# specify more than one server in pop3proxy_servers, you must specify the
# same number of ports in pop3proxy_ports.
pop3proxy_servers:
pop3proxy_ports:
pop3proxy_cache_use_gzip: False
pop3proxy_cache_expiry_days: 7
pop3proxy_spam_cache: pop3proxy-spam-cache
pop3proxy_ham_cache: pop3proxy-ham-cache
pop3proxy_unknown_cache: pop3proxy-unknown-cache
pop3proxy_persistent_use_database: True
pop3proxy_persistent_storage_file: hammie.db
pop3proxy_notate_to: False
pop3proxy_notate_subject: False
pop3proxy_include_prob: False
pop3proxy_prob_header_name: X-Spambayes-Spam-Probability
pop3proxy_include_thermostat: False
pop3proxy_thermostat_header_name: X-Spambayes-Level
pop3proxy_include_evidence: False
pop3proxy_evidence_header_name: X-Spambayes-Evidence
pop3proxy_cache_messages: True
# valid options for pop3proxy_add_mailid_to include
# "", "header", "body", and "header body"
pop3proxy_add_mailid_to:
pop3proxy_mailid_header_name: X-Spambayes-MailId
pop3proxy_strip_incoming_mailids: False

# Deprecated - use pop3proxy_servers and pop3proxy_ports instead.
pop3proxy_server_name:
pop3proxy_server_port: 110
pop3proxy_port: 110

[smtpproxy]
smtpproxy_servers:
smtpproxy_ports:
smtpproxy_ham_address = spambayes_ham@localhost
smtpproxy_spam_address = spambayes_spam@localhost
smtpproxy_shutdown_address = spambayes_shutdown@localhost

[html_ui]
html_ui_port: 8880
html_ui_launch_browser: False
html_ui_allow_remote_connections: True

[globals]
verbose: False
# What DBM storage type should we use?  Must be best, db3hash, dbhash,
# gdbm, dumbdbm.  Windows folk should steer clear of dbhash.  Default is
# "best", which will pick the best DBM type available on your platform.
dbm_type: best
"""

int_cracker = ('getint', None)
float_cracker = ('getfloat', None)
boolean_cracker = ('getboolean', bool)
string_cracker = ('get', None)

all_options = {
    'Tokenizer': {'safe_headers': ('get', lambda s: Set(s.split())),
                  'address_headers': ('get', lambda s: Set(s.split())),
                  'count_all_header_lines': boolean_cracker,
                  'record_header_absence': boolean_cracker,
                  'generate_long_skips': boolean_cracker,
                  'summarize_email_prefixes': boolean_cracker,
                  'summarize_email_suffixes': boolean_cracker,
                  'skip_max_word_size': int_cracker,
                  'extract_dow': boolean_cracker,
                  'generate_time_buckets': boolean_cracker,
                  'mine_received_headers': boolean_cracker,
                  'check_octets': boolean_cracker,
                  'octet_prefix_size': int_cracker,
                  'basic_header_tokenize': boolean_cracker,
                  'basic_header_tokenize_only': boolean_cracker,
                  'basic_header_skip': ('get', lambda s: Set(s.split())),
                  'replace_nonascii_chars': boolean_cracker,
                 },
    'Categorization': { 'ham_cutoff': float_cracker,
                        'spam_cutoff': float_cracker,
                      },
    'TestDriver': {'nbuckets': int_cracker,
                   'show_ham_lo': float_cracker,
                   'show_ham_hi': float_cracker,
                   'show_spam_lo': float_cracker,
                   'show_spam_hi': float_cracker,
                   'show_false_positives': boolean_cracker,
                   'show_false_negatives': boolean_cracker,
                   'show_unsure': boolean_cracker,
                   'show_histograms': boolean_cracker,
                   'percentiles': ('get', lambda s: map(float, s.split())),
                   'save_trained_pickles': boolean_cracker,
                   'save_histogram_pickles': boolean_cracker,
                   'pickle_basename': string_cracker,
                   'show_charlimit': int_cracker,
                   'spam_directories': string_cracker,
                   'ham_directories': string_cracker,
                   'compute_best_cutoffs_from_histograms': boolean_cracker,
                   'best_cutoff_fp_weight': float_cracker,
                   'best_cutoff_fn_weight': float_cracker,
                   'best_cutoff_unsure_weight': float_cracker,
                  },
    'CV Driver': {'build_each_classifier_from_scratch': boolean_cracker,
                 },
    'Classifier': {'max_discriminators': int_cracker,
                   'unknown_word_prob': float_cracker,
                   'unknown_word_strength': float_cracker,
                   'minimum_prob_strength': float_cracker,
                   'use_gary_combining': boolean_cracker,
                   'use_chi_squared_combining': boolean_cracker,
                   'experimental_ham_spam_imbalance_adjustment': boolean_cracker,
                  },
    'Hammie': {'hammie_header_name': string_cracker,
               'clue_mailheader_cutoff': float_cracker,
               'persistent_use_database': boolean_cracker,
               'header_spam_string': string_cracker,
               'header_unsure_string': string_cracker,
               'header_ham_string': string_cracker,
               'header_score_digits': int_cracker,
               'header_score_logarithm': boolean_cracker,
               'hammie_debug_header': boolean_cracker,
               'hammie_debug_header_name': string_cracker,
               'hammie_train_on_filter': boolean_cracker,
               'hammie_trained_header': string_cracker,
               },
    'hammiefilter' : {'hammiefilter_persistent_use_database': boolean_cracker,
                      'hammiefilter_persistent_storage_file': string_cracker,
                      },
    'pop3proxy': {'pop3proxy_servers': string_cracker,
                  'pop3proxy_ports': string_cracker,
                  'pop3proxy_server_name': string_cracker,
                  'pop3proxy_server_port': int_cracker,
                  'pop3proxy_port': int_cracker,
                  'pop3proxy_cache_use_gzip': boolean_cracker,
                  'pop3proxy_cache_expiry_days': int_cracker,
                  'pop3proxy_spam_cache': string_cracker,
                  'pop3proxy_ham_cache': string_cracker,
                  'pop3proxy_unknown_cache': string_cracker,
                  'pop3proxy_persistent_use_database': boolean_cracker,
                  'pop3proxy_persistent_storage_file': string_cracker,
                  'pop3proxy_notate_to' : boolean_cracker,
                  'pop3proxy_notate_subject' : boolean_cracker,
                  'pop3proxy_include_prob' : boolean_cracker,
                  'pop3proxy_prob_header_name' : string_cracker,
                  'pop3proxy_include_thermostat' : boolean_cracker,
                  'pop3proxy_thermostat_header_name' : string_cracker,
                  'pop3proxy_include_evidence' : boolean_cracker,
                  'pop3proxy_evidence_header_name' : string_cracker,
                  'pop3proxy_cache_messages' : boolean_cracker,
                  'pop3proxy_add_mailid_to' : string_cracker,
                  'pop3proxy_mailid_header_name' : string_cracker,
                  'pop3proxy_strip_incoming_mailids' : boolean_cracker,
                  },
    'smtpproxy': {'smtpproxy_ham_address' : string_cracker,
                  'smtpproxy_spam_address' : string_cracker,
                  'smtpproxy_shutdown_address' : string_cracker,
                  'smtpproxy_servers' : string_cracker,
                  'smtpproxy_ports' : string_cracker, 
                  },
    'html_ui': {'html_ui_port': int_cracker,
                'html_ui_launch_browser': boolean_cracker,
                'html_ui_allow_remote_connections': boolean_cracker,
                },
    'globals': {'verbose': boolean_cracker,
                'dbm_type': string_cracker,
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


# `optionsPathname` is the pathname of the last ini file in the list.
# This is where the web-based configuration page will write its changes.
# If no ini files are found, it defaults to bayescustomize.ini in the
# current working directory.
optionsPathname = None

options = OptionsClass()

d = StringIO.StringIO(defaults)
options.mergefilelike(d)
del d

alternate = None
if hasattr(os, 'getenv'):
    alternate = os.getenv('BAYESCUSTOMIZE')
if alternate:
    filenames = alternate.split(os.pathsep)
    options.mergefiles(filenames)
    optionsPathname = os.path.abspath(filenames[-1])
else:
    alts = []
    for path in ['bayescustomize.ini', '~/.spambayesrc']:
        epath = os.path.expanduser(path)
        if os.path.exists(epath):
            alts.append(epath)
    if alts:
        options.mergefiles(alts)
        optionsPathname = os.path.abspath(alts[-1])

if not optionsPathname:
    optionsPathname = os.path.abspath('bayescustomize.ini')
