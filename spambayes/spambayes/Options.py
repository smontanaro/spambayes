"""Options

Classes:
    Option - Holds information about an option
    OptionsClass - A collection of options

Abstract:

Options.options is a globally shared options object.
This object is initialised when the module is loaded: the envar
BAYESCUSTOMIZE is checked for a list of names, if nothing is found
then the local directory and the home directory are checked for a
file caleld bayescustomize.ini and the initial values are loaded from
this.

The Option class holds information about an option - the name of the
option, a nice name (to display), documentation, default value,
possible values (a tuple or a regex pattern), whether multiple values
are allowed, and whether the option should be reset when restoring to
defaults (options like server names should *not* be).

The OptionsClass class provides facility for a collection of Options.
It is expected that manipulation of the options will be carried out
via an instance of this class.

To Do:
 o The all_options list is a hangover, really.  This should be
   absorbed into the new style
 o Get rid of the really ugly backwards compatability code (that adds
   many, many attributes to the options object) as soon as all the
   modules are changed over.
 o Write a script to convert configuration files to the new format
   (this will be easy)
 o Once the above is done, and we have waited a suitable time, stop
   allowing invalid options in configuration files
 o Find a regex expert to come up with *good* patterns for domains,
   email addresses, and so forth.
 o [See also the __issues__ string.]
 o Suggestions?

"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__credits__ = "All the Spambayes folk."
# blame for the new format: Tony Meyer <ta-meyer@ihug.co.nz>

__issues__ = """Things that should be considered further and by
other people:

set(sect, opt, "val") and set(sect, opt, val) when val is a number
both will work ok in terms of the regex at the moment.  When you
get the value, a string or a number will be returned, depending
on which you set.  I'm not sure this is a good thing.

An option that can have multiple values will accept None as a valid
value.  I'm not sure this is a good thing.

We are very generous in checking validity when multiple values are
allowed and the check is a regex (rather than a tuple).  Any sequence
that does not match the regex may be used to delimit the values.
For example, if the regex was simply r"[\d]*" then these would all
be considered valid:
"123a234" -> 123, 234
"123abced234" -> 123, 234
"123XST234xas" -> 123, 234
"123 234" -> 123, 234
"123~!@$%^&@234!" -> 123, 234

If this is a problem, my recommendation would be to change the
multiple_values_allowed attribute from a boolean to a regex/None
i.e. if multiple is None, then only one value is allowed.  Otherwise
multiple is used in a re.split() to separate the input.

When we write() or update() we should convert NoneType into empty strings,
as this is what a configuration file would expect.
"""

import sys, os
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import UpdatableConfigParser
try:
    from sets import Set
except ImportError:
    from compatsets import Set


try:
    True, False, bool
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0
    def bool(val):
        return not not val

import re

# These are handy references to commonly used regex/tuples defining
# permitted values. Although the majority of options use one of these,
# you may use any regex or tuple you wish.
HEADER_NAME = r"[\w\.-\*]+"
HEADER_VALUE = r"[\w\.-\*]+"
INTEGER = r"[\d]+"              # actually, a *positive* integer
REAL = r"[\d]+[\.]?[\d]*"       # likewise, a *positive* real
BOOLEAN = (False, True)
SERVER = r"[\w\.\-]+(:[\d]+)?"  # in the form server:port
PORT = r"[\d]+"
EMAIL_ADDRESS = r"[\w\-\.]+@[\w\-\.]+"
PATH = r"[\w\.-~:\\/\*]+"
VARIABLE_PATH = PATH + r"%"
FILE = r"[\S]+"
FILE_WITH_PATH = PATH
# IMAP seems to allow any character at all in a folder name,
# but we want to use the comma as a delimiter for lists, so
# we don't allow this.  If anyone has folders with commas in the
# names, please let us know and we'll figure out something else.
# ImapUI.py prints out a warning if this is the case.
IMAP_FOLDER = r"[^,]+"

# Each option must include a specification of whether multiple values
# are allowed or not.  This is a True/False value, but to make things
# easier to read, we define these here:
MULTIPLE_ALLOWED = True
SINGLE_VALUE = False

# Similarly, each option must specify whether it should be reset to
# this value on a "reset to defaults" command.  Most should, but with some
# like a server name that defaults to "", this would be pointless.
# Again, for ease of reading, we define these here:
RESTORE = True
DO_NO_RESTORE = False

__all__ = ['options']

# Format:
# defaults is a dictionary, where the keys are the section names
# each key maps to a tuple consisting of:
#   option name, display name, default,
#   doc string, possible values, multiple values allowed,
#   restore on restore-to-defaults

defaults = {
  "Tokenizer" : (
    ("basic_header_tokenize", "Basic header tokenising", False,
     """If true, tokenizer.Tokenizer.tokenize_headers() will tokenize the
     contents of each header field just like the text of the message
     body, using the name of the header as a tag.  Tokens look like
     "header:word".  The basic approach is simple and effective, but also
     very sensitive to biases in the ham and spam collections.  For
     example, if the ham and spam were collected at different times,
     several headers with date/time information will become the best
     discriminators.  (Not just Date, but Received and X-From_.)""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("basic_header_tokenize_only", "Only basic header tokenising", False,
     """If true and basic_header_tokenize is also true, then
     basic_header_tokenize is the only action performed.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("basic_header_skip", "Basic headers to skip", "received date x-.*",
     """If basic_header_tokenize is true, then basic_header_skip is a set
     of headers that should be skipped.""",
     HEADER_NAME, MULTIPLE_ALLOWED, RESTORE),

    ("check_octets", "Check application/octet-stream sections", False,
     """If true, the first few characters of application/octet-stream
     sections are used, undecoded.  What 'few' means is decided by
     octet_prefix_size.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("octet_prefix_size", "Number of characters of octet stream to process", 5,
     """The number of characters of the application/octet-stream sections
     to use, if check_octets is set to true.""",
     INTEGER, SINGLE_VALUE, RESTORE),

    ("count_all_header_lines", "Count all header lines", False,
     """Generate tokens just counting the number of instances of each kind
     of header line, in a case-sensitive way.

     Depending on data collection, some headers are not safe to count.
     For example, if ham is collected from a mailing list but spam from
     your regular inbox traffic, the presence of a header like List-Info
     will be a very strong ham clue, but a bogus one.  In that case, set
     count_all_header_lines to False, and adjust safe_headers instead.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("record_header_absence", "Record header absence", False,
     """When True, generate a "noheader:HEADERNAME" token for each header
     in safe_headers (below) that *doesn't* appear in the headers.  This
     helped in various of Tim's python.org tests, but appeared to hurt a
     little in Anthony Baxter's tests.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("safe_headers", "Safe headers", """abuse-reports-to date errors-to
    from importance in-reply-to message-id mime-version organization
    received reply-to return-path subject to user-agent x-abuse-info
    x-complaints-to x-face""",
     """Like count_all_header_lines, but restricted to headers in this list.
     safe_headers is ignored when count_all_header_lines is true, unless
     record_header_absence is also true.""",
     HEADER_NAME, MULTIPLE_ALLOWED, RESTORE),

    ("mine_received_headers", "Mine the received headers", False,
     """A lot of clues can be gotten from IP addresses and names in
     Received: headers.  Again this can give spectacular results for bogus
     reasons if your test corpora are from different sources. Else set this
     to true.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("address_headers", "Address headers to mine", "from",
     """Mine the following address headers. If you have mixed source
     corpuses (as opposed to a mixed sauce walrus, which is delicious!)
     then you probably don't want to use 'to' or 'cc') Address headers will
     be decoded, and will generate charset tokens as well as the real
     address.  Others to consider: to, cc, reply-to, errors-to, sender,
     ...""",
     HEADER_NAME, MULTIPLE_ALLOWED, RESTORE),

    ("generate_long_skips", "Generate long skips", True,
     """If legitimate mail contains things that look like text to the
     tokenizer and turning turning off this option helps (perhaps binary
     attachments get 'defanged' by something upstream from this operation
     and thus look like text), this may help, and should be an alert that
     perhaps the tokenizer is broken.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("summarize_email_prefixes", "Summarise email prefixes", False,
     """Try to capitalize on mail sent to multiple similar addresses.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("summarize_email_suffixes", "Summarise email prefixes", False,
     """Try to capitalize on mail sent to multiple similar addresses.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("skip_max_word_size", "Long skip trigger length", 12,
     """Length of words that triggers 'long skips'. Longer than this
     triggers a skip.""",
     INTEGER, SINGLE_VALUE, RESTORE),

    ("generate_time_buckets", "Generate time buckets", False,
     """Generate tokens which resemble the posting time in 10-minute
     buckets:  'time:'  hour  ':'  minute//10""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("extract_dow", "Extract day-of-week", False,
     """Extract day of the week tokens from the Date: header.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("replace_nonascii_chars", "", False,
     """If true, replace high-bit characters (ord(c) >= 128) and control
     characters with question marks.  This allows non-ASCII character
     strings to be identified with little training and small database
     burden.  It's appropriate only if your ham is plain 7-bit ASCII, or
     nearly so, so that the mere presence of non-ASCII character strings is
     known in advance to be a strong spam indicator.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("search_for_habeas_headers", "", False,
     """If true, search for the habeas headers (see http://www.habeas.com)
     If they are present and correct, this is a strong ham sign, if they
     are present and incorrect, this is a strong spam sign""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("reduce_habeas_headers", "", False,
     """If search_for_habeas_headers is set, nine tokens are generated for
     messages with habeas headers.  This should be fine, since messages
     with the headers should either be ham, or result in FN so that we can
     send them to habeas so they can be sued.  However, to reduce the
     strength of habeas headers, we offer the ability to reduce the nine
     tokens to one. (This option has no effect if search_for_habeas_headers
     is False)""",
     BOOLEAN, SINGLE_VALUE, RESTORE),
  ),
           
  # These options control how a message is categorized
  "Categorization" : (
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
    # his personal email, and his large comp.lang.python test.  If just
    # beginning training, or extremely fearful of mistakes, 0.05 and 0.95 may
    # be more appropriate for you.
    #
    # Picking good values for gary-combining is much harder, and appears to be
    # corpus-dependent, and within a single corpus dependent on how much
    # training has been done.  Values from 0.50 thru the low 0.60's have been
    # reported to work best by various testers on their data.
    ("ham_cutoff", "Ham cutoff", 0.20,
     """Spambayes gives each email message a spam probability between
     0 and 1. Emails below the Ham Cutoff probability are classified
     as Ham. Larger values will result in more messages being
     classified as ham, but with less certainty that all of them
     actually are ham. This value should be between 0 and 1,
     and should be smaller than the Spam Cutoff.""",
     REAL, SINGLE_VALUE, RESTORE),

    ("spam_cutoff", "Spam cutoff", 0.90,
     """Emails with a spam probability above the Spam Cutoff are
     classified as Spam - just like the Ham Cutoff but at the other
     end of the scale.  Messages that fall between the two values
     are classified as Unsure.""",
     REAL, SINGLE_VALUE, RESTORE),
  ),
 
  # These control various displays in class TestDriver.Driver, and
  # Tester.Test.
  "TestDriver" : (
    ("nbuckets", "Number of buckets", 200,
     """Number of buckets in histograms.""",
     INTEGER, SINGLE_VALUE, RESTORE),

    ("show_histograms", "Show histograms", True,
     "",BOOLEAN, SINGLE_VALUE, RESTORE),

    ("compute_best_cutoffs_from_histograms", "Compute best cutoffs from histograms", True,
     """After the display of a ham+spam histogram pair, you can get a
     listing of all the cutoff values (coinciding with histogram bucket
     boundaries) that minimize:
         best_cutoff_fp_weight * (# false positives) +
         best_cutoff_fn_weight * (# false negatives) +
         best_cutoff_unsure_weight * (# unsure msgs)

     This displays two cutoffs:  hamc and spamc, where
        0.0 <= hamc <= spamc <= 1.0

     The idea is that if something scores < hamc, it's called ham; if
     something scores >= spamc, it's called spam; and everything else is
     called 'I am not sure' -- the middle ground.

     Note:  You may wish to increase nbuckets, to give this scheme more cutoff
     values to analyze.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("best_cutoff_fp_weight", "Best cutoff false positive weight", 10.00,
     """""",
     REAL, SINGLE_VALUE, RESTORE),

    ("best_cutoff_fn_weight", "Best cutoff false negative weight", 1.00,
     """""",
     REAL, SINGLE_VALUE, RESTORE),

    ("best_cutoff_unsure_weight", "Best cutoff unsure weight", 0.20,
     """""",
     REAL, SINGLE_VALUE, RESTORE),

    ("percentiles", "Percentiles", "5 25 75 95",
     """Histogram analysis also displays percentiles.  For each percentile
     p in the list, the score S such that p% of all scores are <= S is
     given. Note that percentile 50 is the median, and is displayed (along
     with the min score and max score) independent of this option.""",
     INTEGER, MULTIPLE_ALLOWED, RESTORE),

    ("show_spam_lo", "", 1.0,
     """Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything.""",
     REAL, SINGLE_VALUE, RESTORE),

    ("show_spam_hi", "", 0.0,
     """Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything.""",
     REAL, SINGLE_VALUE, RESTORE),

    ("show_ham_lo", "", 1.0,
     """Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything.""",
     REAL, SINGLE_VALUE, RESTORE),

    ("show_ham_hi", "", 0.0,
     """Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything.""",
     REAL, SINGLE_VALUE, RESTORE),

    ("show_false_positives", "Show false positives", True,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("show_false_negatives", "Show false negatives", False,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("show_unsure", "Show unsure", False,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("show_charlimit", "Show character limit", 3000,
     """The maximum # of characters to display for a msg displayed due to
     the show_xyz options above.""",
     INTEGER, SINGLE_VALUE, RESTORE),

    ("save_trained_pickles", "Save trained pickles", False,
     """If save_trained_pickles is true, Driver.train() saves a binary
     pickle of the classifier after training.  The file basename is given
     by pickle_basename, the extension is .pik, and increasing integers are
     appended to pickle_basename.  By default (if save_trained_pickles is
     true), the filenames are class1.pik, class2.pik, ...  If a file of
     that name already exists, it is overwritten.  pickle_basename is
     ignored when save_trained_pickles is false.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("pickle_basename", "Pickle basename", "class",
     """""",
     r"[\w]+", SINGLE_VALUE, RESTORE),

    ("save_histogram_pickles", "Save histogram pickles", False,
     """If save_histogram_pickles is true, Driver.train() saves a binary
     pickle of the spam and ham histogram for "all test runs". The file
     basename is given by pickle_basename, the suffix _spamhist.pik
     or _hamhist.pik is appended  to the basename.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("spam_directories", "Spam directories", "Data/Spam/Set%d",
     """default locations for timcv and timtest - these get the set number
     interpolated.""",
     VARIABLE_PATH, MULTIPLE_ALLOWED, RESTORE),

    ("ham_directories", "Ham directories", "Data/Ham/Set%d",
     """default locations for timcv and timtest - these get the set number
     interpolated.""",
     VARIABLE_PATH, MULTIPLE_ALLOWED, RESTORE),
  ),

  "CV Driver": (
    ("build_each_classifier_from_scratch", "Build each classifier from scratch", False,
     """A cross-validation driver takes N ham+spam sets, and builds N
     classifiers, training each on N-1 sets, and the predicting against the
     set not trained on.  By default, it does this in a clever way,
     learning *and* unlearning sets as it goes along, so that it never
     needs to train on N-1 sets in one gulp after the first time.  Setting
     this option true forces ''one gulp from-scratch'' training every time.
     There used to be a set of combining schemes that needed this, but now
     it is just in case you are paranoid <wink>.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),
  ),
 
  "Classifier": (
    ("max_discriminators", "Maximum number of extreme words", 150,
     """The maximum number of extreme words to look at in a msg, where
     "extreme" means with spamprob farthest away from 0.5.  150 appears to
     work well across all corpora tested.""",
     INTEGER, SINGLE_VALUE, RESTORE),

    ("unknown_word_prob", "Unknown word probability", 0.5,
     """These two control the prior assumption about word probabilities.
     unknown_word_prob is essentially the probability given to a word that
     has never been seen before.  Nobody has reported an improvement via
     moving it away from 1/2, although Tim has measured a mean spamprob of
     a bit over 0.5 (0.51-0.55) in 3 well-trained classifiers.

     uknown_word_strength adjusts how much weight to give the prior
     assumption relative to the probabilities estimated by counting.  At 0,
     the counting estimates are believed 100%, even to the extent of
     assigning certainty (0 or 1) to a word that has appeared in only ham
     or only spam.  This is a disaster.""",
     REAL, SINGLE_VALUE, RESTORE),

    ("unknown_word_strength", "Unknown word strength", 0.45,
     """As unknown_word_strength tends toward infintity, all probabilities
     tend toward unknown_word_prob.  All reports were that a value near 0.4
     worked best, so this does not seem to be corpus-dependent.""",
     REAL, SINGLE_VALUE, RESTORE),
 
    ("minimum_prob_strength", "Minimum probability strength", 0.1,
     """When scoring a message, ignore all words with
     abs(word.spamprob - 0.5) < minimum_prob_strength.
     This may be a hack, but it has proved to reduce error rates in many
     tests.  0.1 appeared to work well across all corpora.""",
     REAL, SINGLE_VALUE, RESTORE),
 
    ("use_gary_combining", "Use gary-combining", False,
     """The combining scheme currently detailed on the Robinon web page.
     The middle ground here is touchy, varying across corpus, and within
     a corpus across amounts of training data.  It almost never gives
     extreme scores (near 0.0 or 1.0), but the tail ends of the ham and
     spam distributions overlap.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),
 
    ("use_chi_squared_combining", "Use chi-squared combining", True,
     """For vectors of random, uniformly distributed probabilities,
     -2*sum(ln(p_i)) follows the chi-squared distribution with 2*n degrees
     of freedom.  This is the "provably most-sensitive" test the original
     scheme was monotonic with.  Getting closer to the theoretical basis
     appears to give an excellent combining method, usually very extreme in
     its judgment, yet finding a tiny (in # of msgs, spread across a huge
     range of scores) middle ground where lots of the mistakes live.  This
     is the best method so far. One systematic benefit is is immunity to
     "cancellation disease". One systematic drawback is sensitivity to
     *any* deviation from a uniform distribution, regardless of whether
     actually evidence of ham or spam. Rob Hooft alleviated that by
     combining the final S and H measures via (S-H+1)/2 instead of via
     S/(S+H)). In practice, it appears that setting ham_cutoff=0.05, and
     spam_cutoff=0.95, does well across test sets; while these cutoffs are
     rarely optimal, they get close to optimal.  With more training data,
     Tim has had good luck with ham_cutoff=0.30 and spam_cutoff=0.80 across
     three test data sets (original c.l.p data, his own email, and newer
     general python.org traffic).""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("experimental_ham_spam_imbalance_adjustment", "Correct for imbalanced ham/spam ratio", False,
     """If the # of ham and spam in training data are out of balance, the
     spamprob guesses can get stronger in the direction of the category
     with more training msgs.  In one sense this must be so, since the more
     data we have of one flavor, the more we know about that flavor.  But
     that allows the accidental appearance of a strong word of that flavor
     in a msg of the other flavor much more power than an accident in the
     other direction.  Enable experimental_ham_spam_imbalance_adjustment if
     you have more ham than spam training data (or more spam than ham), and
     the Bayesian probability adjustment won't 'believe' raw counts more
     than min(# ham trained on, # spam trained on) justifies.  I *expect*
     this option will go away (and become the default), but people *with*
     strong imbalance need to test it first.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),
  ),
 
  "Hammie": (
    # The name of the header that hammie, pop3proxy, and any other spambayes
    # software, adds to emails in filter mode.  This will definately contain
    # the "classification" of the mail, and may also (i.e. with hammie)
    # contain the score
    ("header_name", "Classification header name", "X-Spambayes-Classification",
     """Spambayes classifies each message by inserting a new header into
     the message.  This header can then be used by your email client
     (provided your client supports filtering) to move spam into a
     separate folder (recommended), delete it (not recommended), etc.
     This option specifies the name of the header that Spambayes inserts.
     The default value should work just fine, but you may change it to
     anything that you wish.""",
     HEADER_NAME, SINGLE_VALUE, RESTORE),

    # The three disposition names are added to the header as the following
    # Three words:
    ("header_spam_string", "Spam disposition name", "spam",
     """The header that Spambayes inserts into each email has a name,
     (Header Name, above), and a value.  If the classifier determines
     that this email is probably spam, it places a header named as
     above with a value as specified by this string.  The default
     value should work just fine, but you may change it to anything
     that you wish.""",
     HEADER_VALUE, SINGLE_VALUE, RESTORE),
 
    ("header_ham_string", "Ham disposition name", "ham",
     """As for Spam Designation, but for emails classified as
     Ham.""",
     HEADER_VALUE, SINGLE_VALUE, RESTORE),

    ("header_unsure_string", "Unsure disposition name", "unsure",
     """As for Spam/Ham Designation, but for emails which the
     classifer wasn't sure about (ie. the spam probability fell between
     the Ham and Spam Cutoffs).  Emails that have this classification
     should always be the subject of training.""",
     HEADER_VALUE, SINGLE_VALUE, RESTORE),
 
    ("header_score_digits", "Accuracy of reported score", 2,
     """Accuracy of the score in the header in decimal digits""",
     INTEGER, SINGLE_VALUE, RESTORE),
    
    ("header_score_logarithm", "Augment score with logarithm", False,
     """Set this to "True", to augment scores of 1.00 or 0.00 by a
     logarithmic "one-ness" or "zero-ness" score (basically it shows the
     "number of zeros" or "number of nines" next to the score value).""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("debug_header", "Add debug header", False,
     """Enable debugging information in the header.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),
 
    ("debug_header_name", "Debug header name", "X-Spambayes-Debug",
     """Name of a debugging header for spambayes hackers, showing the
     strongest clues that have resulted in the classification in the
     standard header.""",
     HEADER_NAME, SINGLE_VALUE, RESTORE),
 
    ("train_on_filter", "Train when filtering", False,
     """Train when filtering?  After filtering a message, hammie can then
     train itself on the judgement (ham or spam).  This can speed things up
     with a procmail-based solution.  If you do enable this, please make
     sure to retrain any mistakes.  Otherwise, your word database will
     slowly become useless.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("trained_header", "Trained header name", "X-Spambayes-Trained",
     """When training on a message, the name of the header to add with how
     it was trained""",
     HEADER_NAME, SINGLE_VALUE, RESTORE),

    ("clue_mailheader_cutoff", "Debug header cutoff", 0.5,
     """The range of clues that are added to the "debug" header in the
     E-mail. All clues that have their probability smaller than this number,
     or larger than one minus this number are added to the header such that
     you can see why spambayes thinks this is ham/spam or why it is unsure.
     The default is to show all clues, but you can reduce that by setting
     showclue to a lower value, such as 0.1""",
     REAL, SINGLE_VALUE, RESTORE),
  ),

  "hammiefilter" : (
    ("persistent_use_database", "", True,
     """hammiefilter can use either a database (quick to score one message)
     or a pickle (quick to train on huge amounts of messages). Set this to
     True to use a database by default.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("persistent_storage_file", "", "~/.hammiedb",
     """""",
     FILE_WITH_PATH, SINGLE_VALUE, DO_NOT_RESTORE),
  ),

  # pop3proxy settings - pop3proxy also respects the options in the Hammie
  # section, with the exception of the extra header details at the moment.
  # The only mandatory option is pop3proxy_servers, eg.
  # "pop3.my-isp.com:110", or a comma-separated list of those.  The ":110"
  # is optional.  If you specify more than one server in pop3proxy_servers,
  # you must specify the same number of ports in pop3proxy_ports.
  "pop3proxy" : (
    ("servers", "Servers", "",
     """The Spambayes POP3 proxy intercepts incoming email and classifies
     it before sending it on to your email client.  You need to specify
     which POP3 server(s) you wish it to intercept - a POP3 server
     address typically looks like "pop3.myisp.net".  If you use more than
     one server, simply separate their names with commas.  You can get
     these server names from your existing email configuration, or from
     your ISP or system administrator.  If you are using Web-based email,
     you can't use the Spambayes POP3 proxy (sorry!).  In your email
     client's configuration, where you would normally put your POP3 server
     address, you should now put the address of the machine running
     Spambayes.""",
     SERVER, MULTIPLE_ALLOWED, DO_NOT_RESTORE),

    ("ports", "Ports", "",
     """Each POP3 server that is being monitored must be assigned to a
     'port' in the Spambayes POP3 proxy.  This port must be different for
     each monitored server, and there must be a port for
     each monitored server.  Again, you need to configure your email
     client to use this port.  If there are multiple servers, you must
     specify the same number of ports as servers, separated by commas.""",
     PORT, MULTIPLE_ALLOWED, DO_NOT_RESTORE),

    ("cache_use_gzip", "Use gzip", False,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),
    
    ("cache_expiry_days", "Days before cached messages expire", 7,
     """""",
     INTEGER, SINGLE_VALUE, RESTORE),

    ("spam_cache", "Spam cache directory", "pop3proxy-spam-cache",
     """""",
     PATH, SINGLE_VALUE, DO_NOT_RESTORE),
    
    ("ham_cache", "Ham cache directory", "pop3proxy-ham-cache",
     """""",
     PATH, SINGLE_VALUE, DO_NOT_RESTORE),
    
    ("unknown_cache", "Unknown cache directory", "pop3proxy-unknown-cache",
     """""",
     PATH, SINGLE_VALUE, DO_NOT_RESTORE),

    ("persistent_use_database", "", True,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("persistent_storage_file", "Storage file name", "hammie.db",
     """Spambayes builds a database of information that it gathers
     from incoming emails and from you, the user, to get better and
     better at classifying your email.  This option specifies the
     name of the database file.  If you don't give a full pathname,
     the name will be taken to be relative to the current working
     directory.""",
     FILE_WITH_PATH, SINGLE_VALUE, DO_NOT_RESTORE),

    ("notate_to", "Notate to", False,
     """Some email clients (Outlook Express, for example) can only
     set up filtering rules on a limited set of headers.  These
     clients cannot test for the existence/value of an arbitrary
     header and filter mail based on that information.  To
     accomodate these kind of mail clients, the Notate To: can be
     checked, which will add "spam", "ham", or "unsure" to the
     recipient list.  A filter rule can then use this to see if
     one of these words (followed by a comma) is in the recipient
     list, and route the mail to an appropriate folder, or take
     whatever other action is supported and appropriate for the
     mail classification.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("notate_subject", "Classify in subject: header", False,
     """This option will add the same information as 'Notate To',
     but to the start of the mail subject line.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("include_prob", "Add probability header", False,
     """You can have spambayes insert a header with the calculated spam
     probability into each mail.  If you can view headers with your
     mailer, then you can see this information, which can be interesting
     and even instructive if you're a serious spambayes junkie.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("prob_header_name", "Probability header name", "X-Spambayes-Spam-Probability",
     """""",
     HEADER_NAME, SINGLE_VALUE, RESTORE),

    ("include_thermostat", "Add level header", False,
     """You can have spambayes insert a header with the calculated spam
     probability, expressed as a number of '*'s, into each mail (the more
     '*'s, the higher the probability it is spam). If your mailer
     supports it, you can use this information to fine tune your
     classification of ham/spam, ignoring the classification given.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("thermostat_header_name", "Level header name", "X-Spambayes-Level",
     """""",
     HEADER_NAME, SINGLE_VALUE, RESTORE),

    ("include_evidence", "Add evidence header", False,
     """You can have spambayes insert a header into mail, with the
     evidence that it used to classify that message (a collection of
     words with ham and spam probabilities).  If you can view headers
     with your mailer, then this may give you some insight as to why
     a particular message was scored in a particular way.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("evidence_header_name", "Evidence header name", "X-Spambayes-Evidence",
     """""",
     HEADER_NAME, SINGLE_VALUE, RESTORE),

    ("cache_messages", "Cache messages", True,
     """You can disable the pop3proxy caching of messages.  This
     will make the proxy a bit faster, and make it use less space
     on your hard drive.  The proxy uses its cache for reviewing
     and training of messages, so if you disable caching you won't
     be able to do further training unless you re-enable it.
     Thus, you should only turn caching off when you are satisfied
     with the filtering that Spambayes is doing for you.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("add_mailid_to", "Add unique spambayes id", "",
     """If you wish to be able to find a specific message (via the 'find'
     box on the home page), or use the SMTP proxy to
     train, you will need to know the unique id of each message.  If your
     mailer allows you to view all message headers, and includes all these
     headers in forwarded/bounced mail, then the best place for this id
     is in the headers of incoming mail.  Unfortunately, some mail clients
     do not offer these capabilities.  For these clients, you will need to
     have the id added to the body of the message.  If you are not sure,
     the safest option is to use both.""",
     ("header", "body"), MULTIPLE_ALLOWED, True),

    ("mailid_header_name", "Spambayes id header name", "X-Spambayes-MailId",
     """""",
     HEADER_NAME, SINGLE_VALUE, RESTORE),

    ("strip_incoming_mailids", "Strip incoming spambayes ids", False,
     """If you receive messages from other spambayes users, you might
     find that incoming mail (generally replies) already has an id,
     particularly if they have set the id to appear in the body (see
     above).  This might confuse the SMTP proxy when it tries to identify
     the message to train, and make it difficult for you to identify
     the correct id to find a message.  This option strips all spambayes
     ids from incoming mail.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),
  ),

  "smtpproxy" : (

    ("servers", "Servers", "",
     """The Spambayes SMTP proxy intercepts outgoing email - if you
     forward mail to one of the addresses below, it is examined for an id
     and the message corresponding to that id is trained as ham/spam.  All
     other mail is sent along to your outgoing mail server.  You need to
     specify which SMTP server(s) you wish it to intercept - a SMTP server
     address typically looks like "smtp.myisp.net".  If you use more than
     one server, simply separate their names with commas.  You can get
     these server names from your existing email configuration, or from
     your ISP or system administrator.  If you are using Web-based email,
     you can't use the Spambayes SMTP proxy (sorry!).  In your email
     client's configuration, where you would normally put your SMTP server
     address, you should now put the address of the machine running
     Spambayes.""",
     SERVER, MULTIPLE_ALLOWED, DO_NOT_RESTORE),

    ("ports", "Ports", "",
     """Each SMTP server that is being monitored must be assigned to a
     'port' in the Spambayes SMTP proxy.  This port must be different for
     each monitored server, and there must be a port for
     each monitored server.  Again, you need to configure your email
     client to use this port.  If there are multiple servers, you must
     specify the same number of ports as servers, separated by commas.""",
     PORT, MULTIPLE_ALLOWED, DO_NOT_RESTORE),

    ("ham_address", "Train as ham address", "spambayes_ham@localhost",
     """When a message is received that you wish to train on (for example,
     one that was incorrectly classified), you need to forward or bounce
     it to one of two special addresses so that the SMTP proxy can identify
     it.  If you wish to train it as ham, forward or bounce it to this
     address.  You will want to use an address that is not
     a valid email address, like ham@nowhere.nothing.""",
     EMAIL_ADDRESS, SINGLE_VALUE, RESTORE),

    ("spam_address", "Train as spam address", "spambayes_spam@localhost",
     """As with Ham Address above, but the address that you need to forward
     or bounce mail that you wish to train as spam.  You will want to use
     an address that is not a valid email address, like
     spam@nowhere.nothing.""",
     EMAIL_ADDRESS, SINGLE_VALUE, RESTORE),
  ),

  "html_ui" : (
    ("port", "Port", 8880,
     """""",
     PORT, SINGLE_VALUE, RESTORE),

    ("launch_browser", "Launch browser", False,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("allow_remote_connections", "Allow remote connections", False,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),
  ),

  "Outlook" : (
    ("train_recovered_spam", "", True,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("train_manual_spam", "", True,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("spam_action", "", "Untouched",
     """""",
     ("Untouched", "Moved", "Copied"), SINGLE_VALUE, RESTORE),

    ("unsure_action", "", "Untouched",
     """""",
     ("Untouched", "Moved", "Copied"), SINGLE_VALUE, RESTORE),

    ("filter_enabled", "", False,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("field_score_name", "", "Spam",
     """""",
     r"[\w]+", SINGLE_VALUE, RESTORE),

    ("delete_as_spam_marks_as_read", "", False,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("rescore", "", True,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),
  ),
 
  "globals" : (
    ("verbose", "Verbose", False,
     """""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("dbm_type", "Database storage type", "best",
     """What DBM storage type should we use?  Must be best, db3hash, dbhash,
     gdbm, or dumbdbm.  Windows folk should steer clear of dbhash.  Default
     is "best", which will pick the best DBM type available on your
     platform.""",
     ("best", "bd3hash", "dbhash", "gdbm", "dumbdbm"), SINGLE_VALUE, RESTORE),
  ),

  "imap" : (
    ("server", "Server", "",
     """This is the name of the imap server that stores your mail, and
     which the imap filter will connect to - for example: mail.example.com
     or imap.example.com.  If you use more than one server, then things are
     a bit more complicated for you at the moment, sorry.  You will need to
     have multiple instances of the imap filter running, each with a
     different server (and possibly username and password) value.  You can
     do this if you have a different configuration file for each instance,
     but you'll have to do it by hand for the moment.  Please let the
     mailing list know if you are in this situation so that we can consider
     coming up with a better solution.""",
     SERVER, SINGLE_VALUE, DO_NOT_RESTORE),

    ("port", "Port", 143,
     """This is the port of the imap server that stores your mail, and
     which the imap filter will connect to.  The default IMAP port is 143,
     or 993 if using SSL; you will probably have one of those values here.
     If you are using multiple imap servers, please see the comments
     regarding the server value.""",
     PORT, SINGLE_VALUE, DO_NOT_RESTORE),

    ("username", "Username", "",
     """This is the id that you use to log into your imap server.  If your
     address is funkyguy@example.com, then your username is probably
     funkyguy. If you are using multiple imap servers, or multiple accounts
     on the same server, please see the comments regarding the server
     value.""",
     PORT, SINGLE_VALUE, DO_NOT_RESTORE),

    ("password", "Password", "",
     """That is that password that you use to log into your imap server.
     This will be stored in plain text in your configuration file, and if
     you have set the web user interface to allow remote connections, then
     it will be available for the whole world to see in plain text.  If
     I've just freaked you out, don't panic <wink>.  You can leave this
     blank and use the -p command line option to imapfilter.py and you will
     be prompted for your password.""",
     r"[\w]+", SINGLE_VALUE, DO_NOT_RESTORE),

    ("expunge", "Purge//Expunge", False,
     """Permanently remove *all* messages flagged with //Deleted on logout.
     If you do not know what this means, then please leave this as
     False.""",
     BOOLEAN, SINGLE_VALUE, RESTORE),

    ("filter_folders", "Folders to filter", "INBOX",
     """Comma delimited list of folders to be filtered""",
     IMAP_FOLDER, MULTIPLE_ALLOWED, DO_NOT_RESTORE),

    ("unsure_folder", "Folder for unsure messages", "",
     """""", IMAP_FOLDER, SINGLE_VALUE, DO_NOT_RESTORE),
    
    ("spam_folder", "Folder for suspected spam", "",
     """""", IMAP_FOLDER, SINGLE_VALUE, DO_NOT_RESTORE),

    ("ham_train_folders", "Folders with mail to be trained as ham", "",
     """Comma delimited list of folders that will be examined for messages
     to train as ham.""", IMAP_FOLDER, MULTIPLE_ALLOWED, DO_NOT_RESTORE),

    ("spam_train_folders", "Folders with mail to be trained as spam", "",
     """Comma delimited list of folders that will be examined for messages
     to train as spam.""", IMAP_FOLDER, MULTIPLE_ALLOWED, DO_NOT_RESTORE),
  ),
}

int_cracker = ('getint', int)
float_cracker = ('getfloat', float)
boolean_cracker = ('getboolean', bool)
string_cracker = ('get', str)

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
                  'search_for_habeas_headers': boolean_cracker,
                  'reduce_habeas_headers': boolean_cracker,
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
                   'experimental_ham_spam_imbalance_adjustment': \
                   boolean_cracker,
                  },
    'Hammie': {'header_name': string_cracker,
               'clue_mailheader_cutoff': float_cracker,
               'persistent_use_database': boolean_cracker,
               'header_spam_string': string_cracker,
               'header_unsure_string': string_cracker,
               'header_ham_string': string_cracker,
               'header_score_digits': int_cracker,
               'header_score_logarithm': boolean_cracker,
               'debug_header': boolean_cracker,
               'debug_header_name': string_cracker,
               'train_on_filter': boolean_cracker,
               'trained_header': string_cracker,
               },
    'hammiefilter' : {'persistent_use_database': boolean_cracker,
                      'persistent_storage_file': string_cracker,
                      },
    'pop3proxy': {'servers': string_cracker,
                  'ports': string_cracker,
                  'cache_use_gzip': boolean_cracker,
                  'cache_expiry_days': int_cracker,
                  'spam_cache': string_cracker,
                  'ham_cache': string_cracker,
                  'unknown_cache': string_cracker,
                  'persistent_use_database': boolean_cracker,
                  'persistent_storage_file': string_cracker,
                  'notate_to' : boolean_cracker,
                  'notate_subject' : boolean_cracker,
                  'include_prob' : boolean_cracker,
                  'prob_header_name' : string_cracker,
                  'include_thermostat' : boolean_cracker,
                  'thermostat_header_name' : string_cracker,
                  'include_evidence' : boolean_cracker,
                  'evidence_header_name' : string_cracker,
                  'cache_messages' : boolean_cracker,
                  'add_mailid_to' : string_cracker,
                  'mailid_header_name' : string_cracker,
                  'strip_incoming_mailids' : boolean_cracker,
                  },
    'smtpproxy': {'ham_address' : string_cracker,
                  'spam_address' : string_cracker,
                  'shutdown_address' : string_cracker,
                  'servers' : string_cracker,
                  'ports' : string_cracker, 
                  },
    'imap': {'server' : string_cracker,
             'port' : int_cracker,
             'username' : string_cracker,
             'password' : string_cracker,
             'filter_folders' : string_cracker,
             'unsure_folder' : string_cracker,
             'spam_folder' : string_cracker,
             'ham_train_folders' : string_cracker,
             'spam_train_folders' : string_cracker,
             'expunge' : boolean_cracker, 
            },
    'html_ui': {'port': int_cracker,
                'launch_browser': boolean_cracker,
                'allow_remote_connections': boolean_cracker,
            },
    'Outlook': {'train_recovered_spam' : boolean_cracker,
                'train_manual_spam' : boolean_cracker,
                'spam_action' : string_cracker,
                'unsure_action' : string_cracker,
                'filter_enabled' : boolean_cracker,
                'field_score_name' : string_cracker,
                'delete_as_spam_marks_as_read' : boolean_cracker,
                'rescore' : boolean_cracker, 
                },
    'globals': {'verbose' : boolean_cracker,
                'dbm_type' : string_cracker,
                },
}

def _warn(msg):
    print >> sys.stderr, msg

class Option(object):
    def __init__(self, name, nice_name="", default=None,
                 help_text="", allowed=None, multiple=False, restore=True):
        self.name = name
        self.nice_name = nice_name
        self.default_value = default
        self.explanation_text = help_text
        self.allowed_values = allowed
        self.restore = restore
        self.value = None
        self.multiple = multiple

    def display_name(self):
        '''A name for the option suitable for display to a user.'''
        return self.nice_name
    def default(self):
        '''The default value for the option.'''
        return self.default_value
    def doc(self):
        '''Documentation for the option.'''
        return self.explanation_text
    def valid_input(self):
        '''Valid values for the option.'''
        return self.allowed_values
    def no_restore(self):
        '''Do not restore this option when restoring to defaults.'''
        return not self.restore
    def set(self, val):
        '''Set option to value.'''
        self.value = val
    def get(self):
        '''Get option value.'''
        return self.value
    def multiple_values_allowed(self):
        '''Multiple values are allowed for this option.'''
        return self.multiple
    
    def is_valid(self, value):
        '''Check if this is a valid value for this option.'''
        if self.allowed_values is None:
            return False
        if type(self.allowed_values) == type((0,1)):
            if self.multiple and value is None:
                return True
            if type(value) == type((0,1)):
                if self.multiple:
                    for v in value:
                        if not v in self.allowed_values:
                            return False
                    return True
                return False
            else:
               if value in self.allowed_values:
                   return True
               return False
        elif type(self.allowed_values) == type(""):
            vals = self._split_values(value)
            if len(vals) == 0:
                return False
            return True

    def _split_values(self, value):
        # do the regex mojo here
        r = re.compile(self.allowed_values)
        s = str(value)
        i = 0
        vals = ()
        while True:
            m = r.search(s[i:])
            if m is None:
                break
            vals += (m.group(),)
            i += m.end()
        return vals

    def as_nice_string(self, section=None):
        '''Summarise the option in a user-readable format.'''
        if section is None:
            strval = ""
        else:
            strval = "[%s] " % (section)
        strval += "%s - \"%s\"\nDefault: %s\nDo not restore: %s\n" \
                 % (self.name, self.display_name(),
                    str(self.default()), str(self.no_restore()))
        strval += "Valid values: %s\nMultiple values allowed: %s\n" \
                  % (str(self.valid_input()),
                     str(self.multiple_values_allowed()))
        strval += "\"%s\"\n\n" % (str(self.doc()))
        return strval

    def write_config(self, file):
        '''Output value in configuration file format.'''
        file.write(self.name)
        file.write(':')
        file.write(str(self.value))
        file.write('\n')

class OptionsClass(object):
    def __init__(self):
        self._config = UpdatableConfigParser.UpdatableConfigParser()
        self._options = {}

    def update_file(self, file):
        '''Update the specified configuration file.'''
        # The underlying config object doesn't get kept up-to-date
        # because option values are stored in the nice option objects
        # and the config object can't handle those.  So we do a quick
        # update here (no-one else access the config object anyway).
        for sect, opt in self._options.keys():
            if self._config.has_option(sect, opt):
                self._config.set(sect, opt, str(self.get(sect, opt)))
            else:
                self._config.add_option(sect, opt,
                                        str(self.get(sect, opt)),
                                        optionsPathname)
        self._config.update_file(file)

    def load_defaults(self):
        '''Load default values (stored in the module itself).'''
        for section, opts in defaults.items():
            for opt in opts:
                o = Option(opt[0], opt[1], opt[2], opt[3], opt[4], opt[5],
                           opt[6])
                # start with default value
                o.set(opt[2])
                self._options[section, opt[0]] = o
                # A (really ugly) bit of backwards compatability
                # *** This will vanish soon, so do not make use of it in
                #     new code ***
                garbage, converter = all_options[section][opt[0]]
                if converter is not None:
                    value = converter(opt[2])
                old_name = section[0:1].lower() + section[1:] + "_" + opt[0]
                setattr(options, old_name, value)
                old_name = opt[0]
                setattr(options, old_name, value)

    # not necessary, but convenient shortcuts to self._options
    def display_name(self, sect, opt):
        '''A name for the option suitable for display to a user.'''
        return self._options[sect, opt].display_name()
    def default(self, sect, opt):
        '''The default value for the option.'''
        return self._options[sect, opt].default()
    def doc(self, sect, opt):
        '''Documentation for the option.'''
        return self._options[sect, opt].doc()
    def valid_input(self, sect, opt):
        '''Valid values for the option.'''
        return self._options[sect, opt].valid_input()
    def no_restore(self, sect, opt):
        '''Do not restore this option when restoring to defaults.'''
        return self._options[sect, opt].no_restore()
    def is_valid(self, sect, opt, value):
        '''Check if this is a valid value for this option.'''
        return self._options[sect, opt].is_valid(value)
    def multiple_values_allowed(self, sect, opt):
        '''Multiple values are allowed for this option.'''
        return self._options[sect, opt].multiple_values_allowed()

    def is_boolean(self, sect, opt):
        '''The option is a boolean value. (Support for Python 2.2).'''
        # This is necessary because of the Python 2.2 True=1, False=0
        # cheat.  The valid values are returned as 0 and 1, even if
        # they are actually False and True - but 0 and 1 are not
        # considered valid input (and 0 and 1 don't look as nice)
        # So, just for the 2.2 people, we have this helper function
        fetcher, converter = all_options[sect][opt]
        if fetcher == "getboolean":
            return True
        return False

    def convert(self, sect, opt, value):
        '''Convert option from a string to the appropriate type.'''
        fetcher, converter = all_options[sect][opt]
        return converter(value)

    def get(self, sect=None, opt=None):
        '''Get an option.'''
        if sect is None or opt is None:
            return None
        return self._options[sect, opt].get()

    def __getitem__(self, key):
        return self.get(key[0], key[1])

    def set(self, sect=None, opt=None, val=None):
        '''Set an option.'''
        if sect is None or opt is None:
            raise KeyError
        self.convert(sect, opt, val)
        if self.is_valid(sect, opt, val):
            self._options[sect, opt].set(val)
        else:
            print "Attempted to set [%s] %s with invalid value %s (%s)" % \
                  (sect, opt, val, type(val))
        
    def __setitem__(self, key, value):
        self.set(key[0], key[1], value)

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
                    # just for the moment, try and set it anyway
                    # for backwards compatability - this will go
                    # away very soon, so don't rely on this working
                    garbage, new_name = option.split('_', 1)
                    if self._options.has_key((section, new_name)):
                        fetcher, converter = goodopts[new_name]
                        value = getattr(c, fetcher)(section, option)
                        if converter is not None:
                            value = converter(value)
                        setattr(options, option, value) # ugly!
                        option = new_name
                    else:
                        nerrors += 1
                        continue
                else:
                    fetcher, converter = goodopts[option]
                    value = getattr(c, fetcher)(section, option)
                    if converter is not None:
                        value = converter(value)
                self.set(section, option, value)
                # just for the moment, here's some more
                # backwards compatability - this will go
                # away very soon, so don't rely on this working
                old_name = section[0:1].lower() + section[1:] + '_' + option
                setattr(options, old_name, value) # ugly!
        if nerrors:
            raise ValueError("errors while parsing .ini file")

    def sections(self):
        '''Return an alphabetical list of all the sections.'''
        all = []
        for sect, opt in self._options.keys():
            if sect not in all:
                all.append(sect)
        all.sort()
        return all

    def options(self, prepend_section_name=False):
        '''Return a alphabetical list of all the options, optionally
        prefixed with [section_name]'''
        all = []
        for sect, opt in self._options.keys():
            if prepend_section_name:
                all.append('[' + sect + ']' + opt)
            else:
                all.append(opt)
        all.sort()
        return all

    def display(self):
        '''Display options in a config file form.'''
        output = StringIO.StringIO()
        keys = self._options.keys()
        keys.sort()
        currentSection = None
        for sect, opt in keys:
            if sect != currentSection:
                if currentSection is not None:
                    output.write('\n')
                output.write('[')
                output.write(sect)
                output.write("]\n")
                currentSection = sect
            self._options[sect, opt].write_config(output)
        return output.getvalue()

    def display_full(self, section=None, option=None):
       '''Display options including all information.'''
       # Given that the Options class is no longer as nice looking
       # as it once was, this returns all the information, i.e.
       # the doc, default values, and so on
       output = StringIO.StringIO()

       # when section and option are both specified, this
       # is nothing more than a call to as_nice_string
       if section is not None and option is not None:
           output.write(self._options[section,
                                      option].as_nice_string(section))
           return output.getvalue()
       
       all = self._options.keys()
       all.sort()
       for sect, opt in all:
           if section is not None and sect != section:
               continue
           output.write(self._options[sect, opt].as_nice_string(sect))
       return output.getvalue()


# `optionsPathname` is the pathname of the last ini file in the list.
# This is where the web-based configuration page will write its changes.
# If no ini files are found, it defaults to bayescustomize.ini in the
# current working directory.
optionsPathname = None

options = OptionsClass()
options.load_defaults()
options.display()

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
