"""Options

Classes:
    Option - Holds information about an option
    OptionsClass - A collection of options

Abstract:

Options.options is a globally shared options object.
This object is initialised when the module is loaded: the envar
BAYESCUSTOMIZE is checked for a list of names, if nothing is found
then the local directory and the home directory are checked for a
file called bayescustomize.ini or .spambayesrc (respectively) and
the initial values are loaded from this.

The Option class holds information about an option - the name of the
option, a nice name (to display), documentation, default value,
possible values (a tuple or a regex pattern), whether multiple values
are allowed, and whether the option should be reset when restoring to
defaults (options like server names should *not* be).

The OptionsClass class provides facility for a collection of Options.
It is expected that manipulation of the options will be carried out
via an instance of this class.

To Do:
 o Get rid of the really ugly backwards compatability code (that adds
   many, many attributes to the options object) as soon as all the
   modules are changed over.
 o Once the above is done, and we have waited a suitable time, stop
   allowing invalid options in configuration files
 o Find a regex expert to come up with *good* patterns for domains,
   email addresses, and so forth.
 o str(Option) should really call Option.unconvert since this is what
   it does.  Try putting that in and running all the tests.
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
"""

import sys
import os
import shutil
from tempfile import TemporaryFile

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
try:
    from sets import Set
except ImportError:
    from compatsets import Set

import re
import types
import locale

try:
    True, False, bool
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0
    def bool(val):
        return not not val

# Backwards compatibility stuff - this will be removed at some point
# This table allows easy conversion from the (old_section, old_option)
# names to the (new_section, new_option) names.
conversion_table = {("Hammie", "clue_mailheader_cutoff"):
                        ("Headers", "clue_mailheader_cutoff"),
                    ("Hammie", "header_score_digits"):
                        ("Headers", "header_score_digits"),
                    ("Hammie", "header_score_logarithm"):
                        ("Headers", "header_score_logarithm"),
                    ("Hammie", "header_name"):
                        ("Headers", "classification_header_name"),
                    ("Hammie", "header_ham_string"):
                        ("Headers", "header_ham_string"),
                    ("Hammie", "header_spam_string"):
                        ("Headers", "header_spam_string"),
                    ("Hammie", "header_unsure_string"):
                        ("Headers", "header_unsure_string"),
                    ("Hammie", "trained_header"):
                        ("Headers", "trained_header_name"),
                    ("pop3proxy", "evidence_header_name"):
                        ("Headers", "evidence_header_name"),
                    ("pop3proxy", "mailid_header_name"):
                        ("Headers", "mailid_header_name"),
                    ("pop3proxy", "prob_header_name"):
                        ("Headers", "score_header_name"),
                    ("pop3proxy", "thermostat_header_name"):
                        ("Headers", "thermostat_header_name"),
                    ("pop3proxy", "include_evidence"):
                        ("Headers", "include_evidence"),
                    ("pop3proxy", "include_prob"):
                        ("Headers", "include_score"),
                    ("pop3proxy", "include_thermostat"):
                        ("Headers", "include_thermostat"),
                    ("pop3proxy", "ports"):
                        ("pop3proxy", "listen_ports"),
                    ("pop3proxy", "servers"):
                        ("pop3proxy", "remote_servers"),
                    ("smtpproxy", "ports"):
                        ("smtpproxy", "listen_ports"),
                    ("smtpproxy", "servers"):
                        ("smtpproxy", "remote_servers"),
                    ("hammiefilter", "persistent_storage_file"):
                        ("Storage", "persistent_storage_file"),
                    ("hammiefilter", "persistent_use_database"):
                        ("Storage", "persistent_use_database"),
                    ("pop3proxy", "persistent_storage_file"):
                        ("Storage", "persistent_storage_file"),
                    ("pop3proxy", "persistent_use_database"):
                        ("Storage", "persistent_use_database"),
}

# These are handy references to commonly used regex/tuples defining
# permitted values. Although the majority of options use one of these,
# you may use any regex or tuple you wish.
HEADER_NAME = r"[\w\.\-\*]+"
HEADER_VALUE = r"[\w\.\-\*]+"
INTEGER = r"[\d]+"              # actually, a *positive* integer
REAL = r"[\d]+[\.]?[\d]*"       # likewise, a *positive* real
BOOLEAN = (False, True)
SERVER = r"([\w\.\-]+(:[\d]+)?)"  # in the form server:port
PORT = r"[\d]+"
EMAIL_ADDRESS = r"[\w\-\.]+@[\w\-\.]+"
PATH = r"[\w\.\-~:\\/\*]+"
VARIABLE_PATH = PATH + r"%"
FILE = r"[\S]+"
FILE_WITH_PATH = PATH
# IMAP seems to allow any character at all in a folder name,
# but we want to use the comma as a delimiter for lists, so
# we don't allow this.  If anyone has folders with commas in the
# names, please let us know and we'll figure out something else.
# ImapUI.py prints out a warning if this is the case.
IMAP_FOLDER = r"[^,]+"

# IMAP's astring should also be valid in the form:
#   "{" number "}" CRLF *CHAR8
#   where number represents the number of CHAR8 octets
# but this is too complex for us at the moment.
IMAP_ASTRING = ""
for i in range(1, 128):
    if not chr(i) in ['"', '\\', '\n', '\r']:
        IMAP_ASTRING += chr(i)
IMAP_ASTRING = r"\"?\\?[" + re.escape(IMAP_ASTRING) + r"]+\"?"

# Similarly, each option must specify whether it should be reset to
# this value on a "reset to defaults" command.  Most should, but with some
# like a server name that defaults to "", this would be pointless.
# Again, for ease of reading, we define these here:
RESTORE = True
DO_NOT_RESTORE = False

__all__ = ['options']

# Format:
# defaults is a dictionary, where the keys are the section names
# each key maps to a tuple consisting of:
#   option name, display name, default,
#   doc string, possible values, restore on restore-to-defaults

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
     BOOLEAN, RESTORE),

    ("basic_header_tokenize_only", "Only basic header tokenising", False,
     """If true and basic_header_tokenize is also true, then
     basic_header_tokenize is the only action performed.""",
     BOOLEAN, RESTORE),

    ("basic_header_skip", "Basic headers to skip", ("received date x-.*",),
     """If basic_header_tokenize is true, then basic_header_skip is a set
     of headers that should be skipped.""",
     HEADER_NAME, RESTORE),

    ("check_octets", "Check application/octet-stream sections", False,
     """If true, the first few characters of application/octet-stream
     sections are used, undecoded.  What 'few' means is decided by
     octet_prefix_size.""",
     BOOLEAN, RESTORE),

    ("octet_prefix_size", "Number of characters of octet stream to process", 5,
     """The number of characters of the application/octet-stream sections
     to use, if check_octets is set to true.""",
     INTEGER, RESTORE),

    ("count_all_header_lines", "Count all header lines", False,
     """Generate tokens just counting the number of instances of each kind
     of header line, in a case-sensitive way.

     Depending on data collection, some headers are not safe to count.
     For example, if ham is collected from a mailing list but spam from
     your regular inbox traffic, the presence of a header like List-Info
     will be a very strong ham clue, but a bogus one.  In that case, set
     count_all_header_lines to False, and adjust safe_headers instead.""",
     BOOLEAN, RESTORE),

    ("record_header_absence", "Record header absence", False,
     """When True, generate a "noheader:HEADERNAME" token for each header
     in safe_headers (below) that *doesn't* appear in the headers.  This
     helped in various of Tim's python.org tests, but appeared to hurt a
     little in Anthony Baxter's tests.""",
     BOOLEAN, RESTORE),

    ("safe_headers", "Safe headers", ("abuse-reports-to", "date", "errors-to",
                                      "from", "importance", "in-reply-to",
                                      "message-id", "mime-version",
                                      "organization", "received",
                                      "reply-to", "return-path", "subject",
                                      "to", "user-agent", "x-abuse-info",
                                      "x-complaints-to", "x-face"),
     """Like count_all_header_lines, but restricted to headers in this list.
     safe_headers is ignored when count_all_header_lines is true, unless
     record_header_absence is also true.""",
     HEADER_NAME, RESTORE),

    ("mine_received_headers", "Mine the received headers", False,
     """A lot of clues can be gotten from IP addresses and names in
     Received: headers.  Again this can give spectacular results for bogus
     reasons if your test corpora are from different sources. Else set this
     to true.""",
     BOOLEAN, RESTORE),

    ("address_headers", "Address headers to mine", ("from",),
     """Mine the following address headers. If you have mixed source
     corpuses (as opposed to a mixed sauce walrus, which is delicious!)
     then you probably don't want to use 'to' or 'cc') Address headers will
     be decoded, and will generate charset tokens as well as the real
     address.  Others to consider: to, cc, reply-to, errors-to, sender,
     ...""",
     HEADER_NAME, RESTORE),

    ("generate_long_skips", "Generate long skips", True,
     """If legitimate mail contains things that look like text to the
     tokenizer and turning turning off this option helps (perhaps binary
     attachments get 'defanged' by something upstream from this operation
     and thus look like text), this may help, and should be an alert that
     perhaps the tokenizer is broken.""",
     BOOLEAN, RESTORE),

    ("summarize_email_prefixes", "Summarise email prefixes", False,
     """Try to capitalize on mail sent to multiple similar addresses.""",
     BOOLEAN, RESTORE),

    ("summarize_email_suffixes", "Summarise email prefixes", False,
     """Try to capitalize on mail sent to multiple similar addresses.""",
     BOOLEAN, RESTORE),

    ("skip_max_word_size", "Long skip trigger length", 12,
     """Length of words that triggers 'long skips'. Longer than this
     triggers a skip.""",
     INTEGER, RESTORE),

    ("generate_time_buckets", "Generate time buckets", False,
     """Generate tokens which resemble the posting time in 10-minute
     buckets:  'time:'  hour  ':'  minute//10""",
     BOOLEAN, RESTORE),

    ("extract_dow", "Extract day-of-week", False,
     """Extract day of the week tokens from the Date: header.""",
     BOOLEAN, RESTORE),

    ("replace_nonascii_chars", "", False,
     """If true, replace high-bit characters (ord(c) >= 128) and control
     characters with question marks.  This allows non-ASCII character
     strings to be identified with little training and small database
     burden.  It's appropriate only if your ham is plain 7-bit ASCII, or
     nearly so, so that the mere presence of non-ASCII character strings is
     known in advance to be a strong spam indicator.""",
     BOOLEAN, RESTORE),

    ("search_for_habeas_headers", "", False,
     """If true, search for the habeas headers (see http://www.habeas.com)
     If they are present and correct, this is a strong ham sign, if they
     are present and incorrect, this is a strong spam sign""",
     BOOLEAN, RESTORE),

    ("reduce_habeas_headers", "", False,
     """If search_for_habeas_headers is set, nine tokens are generated for
     messages with habeas headers.  This should be fine, since messages
     with the headers should either be ham, or result in FN so that we can
     send them to habeas so they can be sued.  However, to reduce the
     strength of habeas headers, we offer the ability to reduce the nine
     tokens to one. (This option has no effect if search_for_habeas_headers
     is False)""",
     BOOLEAN, RESTORE),
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
     REAL, RESTORE),

    ("spam_cutoff", "Spam cutoff", 0.90,
     """Emails with a spam probability above the Spam Cutoff are
     classified as Spam - just like the Ham Cutoff but at the other
     end of the scale.  Messages that fall between the two values
     are classified as Unsure.""",
     REAL, RESTORE),
  ),
 
  # These control various displays in class TestDriver.Driver, and
  # Tester.Test.
  "TestDriver" : (
    ("nbuckets", "Number of buckets", 200,
     """Number of buckets in histograms.""",
     INTEGER, RESTORE),

    ("show_histograms", "Show histograms", True,
     """""",
     BOOLEAN, RESTORE),

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
     BOOLEAN, RESTORE),

    ("best_cutoff_fp_weight", "Best cutoff false positive weight", 10.00,
     """""",
     REAL, RESTORE),

    ("best_cutoff_fn_weight", "Best cutoff false negative weight", 1.00,
     """""",
     REAL, RESTORE),

    ("best_cutoff_unsure_weight", "Best cutoff unsure weight", 0.20,
     """""",
     REAL, RESTORE),

    ("percentiles", "Percentiles", (5, 25, 75, 95),
     """Histogram analysis also displays percentiles.  For each percentile
     p in the list, the score S such that p% of all scores are <= S is
     given. Note that percentile 50 is the median, and is displayed (along
     with the min score and max score) independent of this option.""",
     INTEGER, RESTORE),

    ("show_spam_lo", "", 1.0,
     """Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything.""",
     REAL, RESTORE),

    ("show_spam_hi", "", 0.0,
     """Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything.""",
     REAL, RESTORE),

    ("show_ham_lo", "", 1.0,
     """Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything.""",
     REAL, RESTORE),

    ("show_ham_hi", "", 0.0,
     """Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything.""",
     REAL, RESTORE),

    ("show_false_positives", "Show false positives", True,
     """""",
     BOOLEAN, RESTORE),

    ("show_false_negatives", "Show false negatives", False,
     """""",
     BOOLEAN, RESTORE),

    ("show_unsure", "Show unsure", False,
     """""",
     BOOLEAN, RESTORE),

    ("show_charlimit", "Show character limit", 3000,
     """The maximum # of characters to display for a msg displayed due to
     the show_xyz options above.""",
     INTEGER, RESTORE),

    ("save_trained_pickles", "Save trained pickles", False,
     """If save_trained_pickles is true, Driver.train() saves a binary
     pickle of the classifier after training.  The file basename is given
     by pickle_basename, the extension is .pik, and increasing integers are
     appended to pickle_basename.  By default (if save_trained_pickles is
     true), the filenames are class1.pik, class2.pik, ...  If a file of
     that name already exists, it is overwritten.  pickle_basename is
     ignored when save_trained_pickles is false.""",
     BOOLEAN, RESTORE),

    ("pickle_basename", "Pickle basename", "class",
     """""",
     r"[\w]+", RESTORE),

    ("save_histogram_pickles", "Save histogram pickles", False,
     """If save_histogram_pickles is true, Driver.train() saves a binary
     pickle of the spam and ham histogram for "all test runs". The file
     basename is given by pickle_basename, the suffix _spamhist.pik
     or _hamhist.pik is appended  to the basename.""",
     BOOLEAN, RESTORE),

    ("spam_directories", "Spam directories", "Data/Spam/Set%d",
     """default locations for timcv and timtest - these get the set number
     interpolated.""",
     VARIABLE_PATH, RESTORE),

    ("ham_directories", "Ham directories", "Data/Ham/Set%d",
     """default locations for timcv and timtest - these get the set number
     interpolated.""",
     VARIABLE_PATH, RESTORE),
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
     BOOLEAN, RESTORE),
  ),
 
  "Classifier": (
    ("max_discriminators", "Maximum number of extreme words", 150,
     """The maximum number of extreme words to look at in a msg, where
     "extreme" means with spamprob farthest away from 0.5.  150 appears to
     work well across all corpora tested.""",
     INTEGER, RESTORE),

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
     REAL, RESTORE),

    ("unknown_word_strength", "Unknown word strength", 0.45,
     """As unknown_word_strength tends toward infintity, all probabilities
     tend toward unknown_word_prob.  All reports were that a value near 0.4
     worked best, so this does not seem to be corpus-dependent.""",
     REAL, RESTORE),
 
    ("minimum_prob_strength", "Minimum probability strength", 0.1,
     """When scoring a message, ignore all words with
     abs(word.spamprob - 0.5) < minimum_prob_strength.
     This may be a hack, but it has proved to reduce error rates in many
     tests.  0.1 appeared to work well across all corpora.""",
     REAL, RESTORE),
 
    ("use_gary_combining", "Use gary-combining", False,
     """The combining scheme currently detailed on the Robinon web page.
     The middle ground here is touchy, varying across corpus, and within
     a corpus across amounts of training data.  It almost never gives
     extreme scores (near 0.0 or 1.0), but the tail ends of the ham and
     spam distributions overlap.""",
     BOOLEAN, RESTORE),
 
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
     BOOLEAN, RESTORE),

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
     BOOLEAN, RESTORE),
  ),
 
  "Hammie": (
    ("debug_header", "Add debug header", False,
     """Enable debugging information in the header.""",
     BOOLEAN, RESTORE),
 
    ("debug_header_name", "Debug header name", "X-Spambayes-Debug",
     """Name of a debugging header for spambayes hackers, showing the
     strongest clues that have resulted in the classification in the
     standard header.""",
     HEADER_NAME, RESTORE),
 
    ("train_on_filter", "Train when filtering", False,
     """Train when filtering?  After filtering a message, hammie can then
     train itself on the judgement (ham or spam).  This can speed things up
     with a procmail-based solution.  If you do enable this, please make
     sure to retrain any mistakes.  Otherwise, your word database will
     slowly become useless.""",
     BOOLEAN, RESTORE),
  ),

  # These options control where Spambayes data will be stored, and in
  # what form.  They are used by many Spambayes applications (including
  # pop3proxy, smtpproxy, imapfilter and hammie), and mean that data
  # (such as the message database) is shared between the applications.
  # If this is not the desired behaviour, you must have a different
  # value for each of these options in a configuration file that gets
  # loaded by the appropriate application only.
  "Storage" : (
    ("persistent_use_database", "", True,
     """hammiefilter can use either a database (quick to score one message)
     or a pickle (quick to train on huge amounts of messages). Set this to
     True to use a database by default.""",
     BOOLEAN, RESTORE),

    ("persistent_storage_file", "Storage file name", "hammie.db",
     """Spambayes builds a database of information that it gathers
     from incoming emails and from you, the user, to get better and
     better at classifying your email.  This option specifies the
     name of the database file.  If you don't give a full pathname,
     the name will be taken to be relative to the current working
     directory.""",
     FILE_WITH_PATH, DO_NOT_RESTORE),
  ),

  # These options control the various headers that some Spambayes
  # applications add to incoming mail, including imapfilter, pop3proxy,
  # and hammie.
  "Headers" : (
    # The name of the header that hammie, pop3proxy, and any other spambayes
    # software, adds to emails in filter mode.  This will definately contain
    # the "classification" of the mail, and may also (i.e. with hammie)
    # contain the score
    ("classification_header_name", "Classification header name", "X-Spambayes-Classification",
     """Spambayes classifies each message by inserting a new header into
     the message.  This header can then be used by your email client
     (provided your client supports filtering) to move spam into a
     separate folder (recommended), delete it (not recommended), etc.
     This option specifies the name of the header that Spambayes inserts.
     The default value should work just fine, but you may change it to
     anything that you wish.""",
     HEADER_NAME, RESTORE),

    # The three disposition names are added to the header as the following
    # Three words:
    ("header_spam_string", "Spam disposition name", "spam",
     """The header that Spambayes inserts into each email has a name,
     (Header Name, above), and a value.  If the classifier determines
     that this email is probably spam, it places a header named as
     above with a value as specified by this string.  The default
     value should work just fine, but you may change it to anything
     that you wish.""",
     HEADER_VALUE, RESTORE),
 
    ("header_ham_string", "Ham disposition name", "ham",
     """As for Spam Designation, but for emails classified as
     Ham.""",
     HEADER_VALUE, RESTORE),

    ("header_unsure_string", "Unsure disposition name", "unsure",
     """As for Spam/Ham Designation, but for emails which the
     classifer wasn't sure about (ie. the spam probability fell between
     the Ham and Spam Cutoffs).  Emails that have this classification
     should always be the subject of training.""",
     HEADER_VALUE, RESTORE),
 
    ("header_score_digits", "Accuracy of reported score", 2,
     """Accuracy of the score in the header in decimal digits""",
     INTEGER, RESTORE),
    
    ("header_score_logarithm", "Augment score with logarithm", False,
     """Set this to "True", to augment scores of 1.00 or 0.00 by a
     logarithmic "one-ness" or "zero-ness" score (basically it shows the
     "number of zeros" or "number of nines" next to the score value).""",
     BOOLEAN, RESTORE),

    ("include_score", "Add probability (score) header", False,
     """You can have Spambayes insert a header with the calculated spam
     probability into each mail.  If you can view headers with your
     mailer, then you can see this information, which can be interesting
     and even instructive if you're a serious Spambayes junkie.""",
     BOOLEAN, RESTORE),

    ("score_header_name", "Probability (score) header name", "X-Spambayes-Spam-Probability",
     """""",
     HEADER_NAME, RESTORE),

    ("include_thermostat", "Add level header", False,
     """You can have spambayes insert a header with the calculated spam
     probability, expressed as a number of '*'s, into each mail (the more
     '*'s, the higher the probability it is spam). If your mailer
     supports it, you can use this information to fine tune your
     classification of ham/spam, ignoring the classification given.""",
     BOOLEAN, RESTORE),

    ("thermostat_header_name", "Level header name", "X-Spambayes-Level",
     """""",
     HEADER_NAME, RESTORE),

    ("include_evidence", "Add evidence header", False,
     """You can have spambayes insert a header into mail, with the
     evidence that it used to classify that message (a collection of
     words with ham and spam probabilities).  If you can view headers
     with your mailer, then this may give you some insight as to why
     a particular message was scored in a particular way.""",
     BOOLEAN, RESTORE),

    ("evidence_header_name", "Evidence header name", "X-Spambayes-Evidence",
     """""",
     HEADER_NAME, RESTORE),

    ("mailid_header_name", "Spambayes id header name", "X-Spambayes-MailId",
     """""",
     HEADER_NAME, RESTORE),

    ("trained_header_name", "Trained header name", "X-Spambayes-Trained",
     """When training on a message, the name of the header to add with how
     it was trained""",
     HEADER_NAME, RESTORE),

    ("clue_mailheader_cutoff", "Debug header cutoff", 0.5,
     """The range of clues that are added to the "debug" header in the
     E-mail. All clues that have their probability smaller than this number,
     or larger than one minus this number are added to the header such that
     you can see why spambayes thinks this is ham/spam or why it is unsure.
     The default is to show all clues, but you can reduce that by setting
     showclue to a lower value, such as 0.1""",
     REAL, RESTORE),
  ),

  # pop3proxy settings - pop3proxy also respects the options in the Hammie
  # section, with the exception of the extra header details at the moment.
  # The only mandatory option is pop3proxy_servers, eg.
  # "pop3.my-isp.com:110", or a comma-separated list of those.  The ":110"
  # is optional.  If you specify more than one server in pop3proxy_servers,
  # you must specify the same number of ports in pop3proxy_ports.
  "pop3proxy" : (
    ("remote_servers", "Servers", (),
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
     SERVER, DO_NOT_RESTORE),

    ("listen_ports", "Ports", (),
     """Each POP3 server that is being monitored must be assigned to a
     'port' in the Spambayes POP3 proxy.  This port must be different for
     each monitored server, and there must be a port for
     each monitored server.  Again, you need to configure your email
     client to use this port.  If there are multiple servers, you must
     specify the same number of ports as servers, separated by commas.""",
     PORT, DO_NOT_RESTORE),

    ("cache_use_gzip", "Use gzip", False,
     """""",
     BOOLEAN, RESTORE),
    
    ("cache_expiry_days", "Days before cached messages expire", 7,
     """""",
     INTEGER, RESTORE),

    ("spam_cache", "Spam cache directory", "pop3proxy-spam-cache",
     """""",
     PATH, DO_NOT_RESTORE),
    
    ("ham_cache", "Ham cache directory", "pop3proxy-ham-cache",
     """""",
     PATH, DO_NOT_RESTORE),
    
    ("unknown_cache", "Unknown cache directory", "pop3proxy-unknown-cache",
     """""",
     PATH, DO_NOT_RESTORE),

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
     BOOLEAN, RESTORE),

    ("notate_subject", "Classify in subject: header", False,
     """This option will add the same information as 'Notate To',
     but to the start of the mail subject line.""",
     BOOLEAN, RESTORE),

    ("cache_messages", "Cache messages", True,
     """You can disable the pop3proxy caching of messages.  This
     will make the proxy a bit faster, and make it use less space
     on your hard drive.  The proxy uses its cache for reviewing
     and training of messages, so if you disable caching you won't
     be able to do further training unless you re-enable it.
     Thus, you should only turn caching off when you are satisfied
     with the filtering that Spambayes is doing for you.""",
     BOOLEAN, RESTORE),

    ("add_mailid_to", "Add unique spambayes id", (),
     """If you wish to be able to find a specific message (via the 'find'
     box on the home page), or use the SMTP proxy to
     train, you will need to know the unique id of each message.  If your
     mailer allows you to view all message headers, and includes all these
     headers in forwarded/bounced mail, then the best place for this id
     is in the headers of incoming mail.  Unfortunately, some mail clients
     do not offer these capabilities.  For these clients, you will need to
     have the id added to the body of the message.  If you are not sure,
     the safest option is to use both.""",
     ("header", "body"), True),

    ("strip_incoming_mailids", "Strip incoming spambayes ids", False,
     """If you receive messages from other spambayes users, you might
     find that incoming mail (generally replies) already has an id,
     particularly if they have set the id to appear in the body (see
     above).  This might confuse the SMTP proxy when it tries to identify
     the message to train, and make it difficult for you to identify
     the correct id to find a message.  This option strips all spambayes
     ids from incoming mail.""",
     BOOLEAN, RESTORE),
  ),

  "smtpproxy" : (

    ("remote_servers", "Servers", (),
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
     SERVER, DO_NOT_RESTORE),

    ("listen_ports", "Ports", (),
     """Each SMTP server that is being monitored must be assigned to a
     'port' in the Spambayes SMTP proxy.  This port must be different for
     each monitored server, and there must be a port for
     each monitored server.  Again, you need to configure your email
     client to use this port.  If there are multiple servers, you must
     specify the same number of ports as servers, separated by commas.""",
     PORT, DO_NOT_RESTORE),

    ("ham_address", "Train as ham address", "spambayes_ham@localhost",
     """When a message is received that you wish to train on (for example,
     one that was incorrectly classified), you need to forward or bounce
     it to one of two special addresses so that the SMTP proxy can identify
     it.  If you wish to train it as ham, forward or bounce it to this
     address.  You will want to use an address that is not
     a valid email address, like ham@nowhere.nothing.""",
     EMAIL_ADDRESS, RESTORE),

    ("spam_address", "Train as spam address", "spambayes_spam@localhost",
     """As with Ham Address above, but the address that you need to forward
     or bounce mail that you wish to train as spam.  You will want to use
     an address that is not a valid email address, like
     spam@nowhere.nothing.""",
     EMAIL_ADDRESS, RESTORE),
  ),

  "html_ui" : (
    ("port", "Port", 8880,
     """""",
     PORT, RESTORE),

    ("launch_browser", "Launch browser", False,
     """""",
     BOOLEAN, RESTORE),

    ("allow_remote_connections", "Allow remote connections", False,
     """""",
     BOOLEAN, RESTORE),
  ),

  "Outlook" : (
    ("train_recovered_spam", "", True,
     """""",
     BOOLEAN, RESTORE),

    ("train_manual_spam", "", True,
     """""",
     BOOLEAN, RESTORE),

    ("spam_action", "", "Untouched",
     """""",
     ("Untouched", "Moved", "Copied"), RESTORE),

    ("unsure_action", "", "Untouched",
     """""",
     ("Untouched", "Moved", "Copied"), RESTORE),

    ("filter_enabled", "", False,
     """""",
     BOOLEAN, RESTORE),

    ("field_score_name", "", "Spam",
     """""",
     r"[\w]+", RESTORE),

    ("delete_as_spam_marks_as_read", "", False,
     """""",
     BOOLEAN, RESTORE),

    ("rescore", "", True,
     """""",
     BOOLEAN, RESTORE),
  ),
 
  "globals" : (
    ("verbose", "Verbose", False,
     """""",
     BOOLEAN, RESTORE),

    ("dbm_type", "Database storage type", "best",
     """What DBM storage type should we use?  Must be best, db3hash, dbhash,
     gdbm, or dumbdbm.  Windows folk should steer clear of dbhash.  Default
     is "best", which will pick the best DBM type available on your
     platform.""",
     ("best", "bd3hash", "dbhash", "gdbm", "dumbdbm"), RESTORE),
  ),

  "imap" : (
    ("server", "Server", (),
     """This is the name and port of the imap server that stores your mail,
     and which the imap filter will connect to - for example:
     mail.example.com or imap.example.com:143.  The default IMAP port is
     143, or 993 if using SSL; if you connect via one of those ports, you
     can leave this blank. If you use more than one server, then things are
     a bit more complicated for you at the moment, sorry.  You will need to
     have multiple instances of the imap filter running, each with a
     different server (and possibly username and password) value.  You can
     do this if you have a different configuration file for each instance,
     but you'll have to do it by hand for the moment.  Please let the
     mailing list know if you are in this situation so that we can consider
     coming up with a better solution.""",
     SERVER, DO_NOT_RESTORE),

    ("username", "Username", (),
     """This is the id that you use to log into your imap server.  If your
     address is funkyguy@example.com, then your username is probably
     funkyguy. If you are using multiple imap servers, or multiple accounts
     on the same server, please see the comments regarding the server
     value.""",
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("password", "Password", (),
     """That is that password that you use to log into your imap server.
     This will be stored in plain text in your configuration file, and if
     you have set the web user interface to allow remote connections, then
     it will be available for the whole world to see in plain text.  If
     I've just freaked you out, don't panic <wink>.  You can leave this
     blank and use the -p command line option to imapfilter.py and you will
     be prompted for your password.""",
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("expunge", "Purge//Expunge", False,
     """Permanently remove *all* messages flagged with //Deleted on logout.
     If you do not know what this means, then please leave this as
     False.""",
     BOOLEAN, RESTORE),

    ("use_ssl", "Connect via a secure socket layer", False,
     """NOT YET IMPLEMENTED""",
     BOOLEAN, DO_NOT_RESTORE),

    ("filter_folders", "Folders to filter", ("INBOX",),
     """Comma delimited list of folders to be filtered""",
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("unsure_folder", "Folder for unsure messages", "",
     """""",
     IMAP_FOLDER, DO_NOT_RESTORE),
    
    ("spam_folder", "Folder for suspected spam", "",
     """""",
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("ham_train_folders", "Folders with mail to be trained as ham", (),
     """Comma delimited list of folders that will be examined for messages
     to train as ham.""",
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("spam_train_folders", "Folders with mail to be trained as spam", (),
     """Comma delimited list of folders that will be examined for messages
     to train as spam.""",
     IMAP_FOLDER, DO_NOT_RESTORE),
  ),
}

class Option(object):
    def __init__(self, name, nice_name="", default=None,
                 help_text="", allowed=None, restore=True):
        self.name = name
        self.nice_name = nice_name
        self.default_value = default
        self.explanation_text = help_text
        self.allowed_values = allowed
        self.restore = restore
        self.value = None
        self.delimiter = None

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
        return type(self.value) == types.TupleType
    
    def is_valid(self, value):
        '''Check if this is a valid value for this option.'''
# XXX This test is in the original code, but makes no sense....
# XXX self.allowed_values defaults to None, and if that is the
# XXX current value, then whatever is passed would be invalid
# XXX I agree this is a silly state to be in, but it is possible
# XXX I suppose that self.allowed_values should default to *any*
# XXX rather than None, but I'm not sure how to express that,
# XXX unless the regex r"." is correct.
        if self.allowed_values is None:
            return False

        if type(self.value) == types.TupleType:
            return self.is_valid_multiple(value)
        else:
            return self.is_valid_single(value)

    def is_valid_multiple(self, value):
        '''Return True iff value is a valid value for this option.
        Use if multiple values are allowed.'''
        if type(value) == types.TupleType:
            for val in value:
                if not self.is_valid_single(val):
                    return False
            return True
        return self.is_valid_single(value)

    def is_valid_single(self, value):
        '''Return True iff value is a valid value for this option.
        Use if multiple values are not allowed.'''
        if type(self.allowed_values) == types.TupleType:
            if value in self.allowed_values:
                return True
            else:
                return False
        else:
            # special handling for booleans, thanks to Python 2.2
            if self.is_boolean and (value == True or value == False):
                return True
            if type(value) != type(self.value) and \
               type(self.value) != types.TupleType:
                # This is very strict!  If the value is meant to be
                # a real number and an integer is passed in, it will fail.
                # (So pass 1. instead of 1, for example)
                return False
            avals = self._split_values(value)
            # in this case, allowed_values must be a regex, and
            # _split_values must match once and only once
            if len(avals) == 1:
                return True
            else:
                # either no match or too many matches
                return False
            
    def _split_values(self, value):
        # do the regex mojo here
        try:
            r = re.compile(self.allowed_values)
        except:
            print self.allowed_values
            raise
        s = str(value)
        i = 0
        vals = ()
        while True:
            m = r.search(s[i:])
            if m is None:
                break
            vals += (m.group(),)
            delimiter = s[i:i + m.start()]
            if self.delimiter is None and delimiter != "":
                self.delimiter = delimiter
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
        file.write(': ')
        file.write(self.unconvert())
        file.write('\n')

    def convert(self, value):
        '''Convert value from a string to the appropriate type.'''
        svt = type(self.value)
        if svt == type(value):
            # already the correct type
            return value
        if self.is_boolean():
            if str(value) == "True" or value == 1:
                return True
            elif str(value) == "False" or value == 0:
                return False
            raise TypeError, self.name + " must be True or False"
        if self.multiple_values_allowed():
            # This will fall apart if the allowed_value is a tuple,
            # but not a homogenous one...
            if type(self.allowed_values) in types.StringTypes:
                vals = list(self._split_values(value))
            else:
                vals = value.split()
            if len(self.default_value) > 0:
                to_type = type(self.default_value[0])
            else:
                to_type = types.StringType
            for i in range(0, len(vals)):
                vals[i] = self._convert(vals[i], to_type)
            return tuple(vals)
        else:
            return self._convert(value, svt)
        raise TypeError, self.name + " has an invalid type."

    def _convert(self, value, to_type):
        '''Convert an int, float or string to the specified type.'''
        if to_type == type(value):
            # already the correct type
            return value
        if to_type == types.IntType:
            return locale.atoi(value)
        if to_type == types.FloatType:
            return locale.atof(value)
        if to_type in types.StringTypes:
            return str(value)
        raise TypeError, "Invalid type."

    def unconvert(self):
        '''Convert value from the appropriate type to a string.'''
        if type(self.value) in types.StringTypes:
            # nothing to do
            return self.value
        if self.is_boolean():
            # A wee bit extra for Python 2.2
            if self.value == True:
                return "True"
            else:
                return "False"
        if type(self.value) == types.TupleType:
            if len(self.value) == 0:
                return ""
            if len(self.value) == 1:
                v = self.value[0]
                if type(v) == types.FloatType:
                    return locale.str(self.value[0])
                return str(v)
            # We need to separate out the items
            strval = ""
            # We use a character that is invalid as the separator
            # so that it will reparse correctly.  We could try all
            # characters, but we make do with this set of commonly
            # used ones - note that the first one that works will
            # be used.  Perhaps a nicer solution than this would be
            # to specifiy a valid delimiter for all options that
            # can have multiple values.  Note that we have None at
            # the end so that this will crash and die if none of
            # the separators works <wink>.
            if self.delimiter is None:
                if type(self.allowed_values) == types.TupleType:
                    self.delimiter = ' '
                else:
                    v0 = self.value[0]
                    v1 = self.value[1]
                    for sep in [' ', ',', ':', ';', '/', '\\', None]:
                        # we know at this point that len(self.value) is at
                        # least two, because len==0 and len==1 were dealt
                        # with as special cases
                        test_str = str(v0) + sep + str(v1)
                        test_tuple = self._split_values(test_str)
                        if test_tuple[0] == str(v0) and \
                           test_tuple[1] == str(v1) and \
                           len(test_tuple) == 2:
                            break
                    # cache this so we don't always need to do the above
                    self.delimiter = sep
            for v in self.value:
                if type(v) == types.FloatType:
                    v = locale.str(v)
                else:
                    v = str(v)
                strval += v + self.delimiter
            strval = strval[:-len(self.delimiter)] # trailing seperator
        else:
            # Otherwise, we just hope str() will do the job
            strval = str(self.value)
        return strval

    def is_boolean(self):
        '''Return True iff the option is a boolean value.'''
        # This is necessary because of the Python 2.2 True=1, False=0
        # cheat.  The valid values are returned as 0 and 1, even if
        # they are actually False and True - but 0 and 1 are not
        # considered valid input (and 0 and 1 don't look as nice)
        # So, just for the 2.2 people, we have this helper function
        try:
            if type(self.allowed_values) == types.TupleType and \
               len(self.allowed_values) > 0 and \
               type(self.allowed_values[0]) == types.BooleanType:
                return True
            return False
        except AttributeError:
            # If the user has Python 2.2 and an option has valid values
            # of (0, 1) - i.e. integers, then this function will return
            # the wrong value.  I don't know what to do about that without
            # explicitly stating which options are boolean
            if self.allowed_values == (False, True):
                return True
            return False


class OptionsClass(object):
    def __init__(self):
        self._options = {}

    #
    # Regular expressions for parsing section headers and options.
    # Lifted straight from ConfigParser
    #
    SECTCRE = re.compile(
        r'\['                                 # [
        r'(?P<header>[^]]+)'                  # very permissive!
        r'\]'                                 # ]
        )
    OPTCRE = re.compile(
        r'(?P<option>[^:=\s][^:=]*)'          # very permissive!
        r'\s*(?P<vi>[:=])\s*'                 # any number of space/tab,
                                              # followed by separator
                                              # (either : or =), followed
                                              # by any # space/tab
        r'(?P<value>.*)$'                     # everything up to EOL
        )

    def update_file(self, filename):
        '''Update the specified configuration file.'''
        sectname = None
        optname = None
        out = TemporaryFile("w")
        if os.path.exists(filename):
            f = file(filename, "r")
        else:
            # doesn't exist, so create it - all the changed options will
            # be added to it
            if options["globals", "verbose"]:
                print "Creating new configuration file", filename
            f = file(filename, "w")
            f.close()
            f = file(filename, "r")
        written = []
        vi = ": " # default; uses the one from the file where possible
        while True:
            line = f.readline()
            if not line:
                break
            # comment or blank line?
            if line.strip() == '' or line[0] in '#;':
                out.write(line)
                continue
            if line.split(None, 1)[0].lower() == 'rem' and line[0] in "rR":
                # no leading whitespace
                out.write(line)
                continue
            # continuation line?
            if line[0].isspace() and sectname is not None and optname:
                continue
            # a section header or option header?
            else:
                # is it a section header?
                mo = self.SECTCRE.match(line)
                if mo:
                    # Add any missing from the previous section
                    if sectname is not None:
                        self._add_missing(out, written, sectname, vi, False)
                    sectname = mo.group('header')
                    # So sections can't start with a continuation line
                    optname = None
                    if sectname in self.sections():
                        out.write(line)
                # an option line?
                else:
                    mo = self.OPTCRE.match(line)
                    if mo:
                        optname, vi, optval = mo.group('option', 'vi', 'value')
                        if vi in ('=', ':') and ';' in optval:
                            # ';' is a comment delimiter only if it follows
                            # a spacing character
                            pos = optval.find(';')
                            if pos != -1 and optval[pos-1].isspace():
                                optval = optval[:pos]
                        optval = optval.strip()
                        # allow empty values
                        if optval == '""':
                            optval = ''
                        optname = optname.rstrip().lower()
                        if self._options.has_key((sectname, optname)):
                            out.write(optname)
                            out.write(vi)
                            out.write(self.unconvert(sectname, optname))
                            out.write('\n')
                            written.append((sectname, optname))
        for sect in self.sections():
            self._add_missing(out, written, sect, vi)
        f.close()
        out.flush()
        if options["globals", "verbose"]:
            # save a backup of the old file
            shutil.copyfile(filename, filename + ".bak")
        # copy the new file across
        f = file(filename)
        shutil.copyfileobj(out, f)
        out.close()
        f.close()
    
    def _add_missing(self, out, written, sect, vi, label=True):
        # add any missing ones, where the value does not equal the default
        for opt in self.options_in_section(sect):
            if not (sect, opt) in written and \
               self.get(sect, opt) != self.default(sect, opt):
                if label:
                    out.write('[')
                    out.write(sect)
                    out.write("]\n")
                    label = False
                out.write(opt)
                out.write(vi)
                out.write(self.unconvert(sect, opt))
                out.write('\n')
                written.append((sect, opt))

    def load_defaults(self):
        '''Load default values (stored in this module).'''
        for section, opts in defaults.items():
            for opt in opts:
                o = Option(opt[0], opt[1], opt[2], opt[3], opt[4], opt[5])
                self._options[section, opt[0]] = o
                # start with default value
                o.set(opt[2])
                # A (really ugly) bit of backwards compatability
                # *** This will vanish soon, so do not make use of it in
                #     new code ***
                self._oldset(section, opt[0], opt[2])

    def _oldset(self, section, option, value):
        # A (really ugly) bit of backwards compatability
        # *** This will vanish soon, so do not make use of it in
        #     new code ***
        setattr(options, option, value)
        old_name = section[0:1].lower() + section[1:] + "_" + option
        setattr(options, old_name, value)
                
    def merge_files(self, file_list):
        for file in file_list:
            self.merge_file(file)

    def merge_file(self, filename):
        import ConfigParser
        c = ConfigParser.ConfigParser()
        c.read(filename)
        for sect in c.sections():
            for opt in c.options(sect):
                value = c.get(sect, opt)
                # backward compatibility guff
                if opt[:len(sect) + 1].lower() == sect.lower() + '_':
                    opt = opt[len(sect)+1:]
                if conversion_table.has_key((sect, opt)):
                    section, option = conversion_table[sect, opt]
                else:
                    section = sect
                    option = opt
                # end of backward compatibility guff
                if not self._options.has_key((section, option)):
                    print "Invalid option %s in section %s in file %s" % \
                          (opt, sect, filename)
                else:
                    if self.multiple_values_allowed(section, option):
                        value = self.convert(section, option, value)
                    self.set(section, option, self.convert(section, option,
                                                           value))
                    # backward compatibility guff
                    self._oldset(sect, opt, value)
                    # end of backward compatibility guff

    # not strictly necessary, but convenient shortcuts to self._options
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
        return self._options[sect, opt].is_boolean()

    def convert(self, sect, opt, value):
        '''Convert value from a string to the appropriate type.'''
        return self._options[sect, opt].convert(value)

    def unconvert(self, sect, opt):
        '''Convert value from the appropriate type to a string.'''
        return self._options[sect, opt].unconvert()

    def get(self, sect, opt):
        '''Get an option.'''
        if conversion_table.has_key((sect, opt)):
            sect, opt = conversion_table[sect, opt]
        return self._options[sect, opt].get()

    def __getitem__(self, key):
        return self.get(key[0], key[1])

    def set(self, sect, opt, val=None):
        '''Set an option.'''
        if conversion_table.has_key((sect, opt)):
            sect, opt = conversion_table[sect, opt]
        if self.is_valid(sect, opt, val):
            self._options[sect, opt].set(val)
            # backwards compatibility stuff
            self._oldset(sect, opt, val)
        else:
            print "Attempted to set [%s] %s with invalid value %s (%s)" % \
                  (sect, opt, val, type(val))
        
    def __setitem__(self, key, value):
        self.set(key[0], key[1], value)

    def sections(self):
        '''Return an alphabetical list of all the sections.'''
        all = []
        for sect, opt in self._options.keys():
            if sect not in all:
                all.append(sect)
        all.sort()
        return all
    
    def options_in_section(self, section):
        '''Return an alphabetical list of all the options in this section.'''
        all = []
        for sect, opt in self._options.keys():
            if sect == section:
                all.append(opt)
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

alternate = None
if hasattr(os, 'getenv'):
    alternate = os.getenv('BAYESCUSTOMIZE')
if alternate:
    filenames = alternate.split(os.pathsep)
    options.merge_files(filenames)
    optionsPathname = os.path.abspath(filenames[-1])
else:
    alts = []
    for path in ['bayescustomize.ini', '~/.spambayesrc']:
        epath = os.path.expanduser(path)
        if os.path.exists(epath):
            alts.append(epath)
    if alts:
        options.merge_files(alts)
        optionsPathname = os.path.abspath(alts[-1])

if not optionsPathname:
    optionsPathname = os.path.abspath('bayescustomize.ini')
