"""Options

Abstract:

Options.options is a globally shared options object.
This object is initialised when the module is loaded: the envar
BAYESCUSTOMIZE is checked for a list of names, if nothing is found
then the local directory and the home directory are checked for a
file called bayescustomize.ini or .spambayesrc (respectively) and
the initial values are loaded from this.

The Option class is defined in OptionsClass.py - this module
is responsible only for instantiating and loading the globally
shared instance.

To Do:
 o Suggestions?
"""

import sys, os

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

__all__ = ['options']

# Grab the stuff from the core options class.
from OptionsClass import *

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
     Received: headers.  This can give spectacular results for bogus
     reasons if your corpora are from different sources.""",
     BOOLEAN, RESTORE),

    ("address_headers", "Address headers to mine", ("from", "to", "cc", "sender", "reply-to"),
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

    ("summarize_email_suffixes", "Summarise email suffixes", False,
     """Try to capitalize on mail sent to multiple similar addresses.""",
     BOOLEAN, RESTORE),

    ("skip_max_word_size", "Long skip trigger length", 12,
     """Length of words that triggers 'long skips'. Longer than this
     triggers a skip.""",
     INTEGER, RESTORE),

    ("x-pick_apart_urls", "Extract clues about url structure", False,
     """(EXPERIMENTAL) Note whether url contains non-standard port or
     user/password elements.""",
     BOOLEAN, RESTORE),

    ("x-fancy_url_recognition", "Extract URLs without http:// prefix", False,
     """(EXPERIMENTAL) Recognize 'www.python.org' or ftp.python.org as URLs
     instead of just long words.""",
     BOOLEAN, RESTORE),

    ("replace_nonascii_chars", "Replace non-ascii characters", False,
     """If true, replace high-bit characters (ord(c) >= 128) and control
     characters with question marks.  This allows non-ASCII character
     strings to be identified with little training and small database
     burden.  It's appropriate only if your ham is plain 7-bit ASCII, or
     nearly so, so that the mere presence of non-ASCII character strings is
     known in advance to be a strong spam indicator.""",
     BOOLEAN, RESTORE),

    ("x-search_for_habeas_headers", "Search for Habeas Headers", False,
     """(EXPERIMENTAL) If true, search for the habeas headers (see
     http://www.habeas.com). If they are present and correct, this should
     be a strong ham sign, if they are present and incorrect, this should
     be a strong spam sign.""",
     BOOLEAN, RESTORE),

    ("x-reduce_habeas_headers", "Reduce Habeas Header Tokens to Single", False,
     """(EXPERIMENTAL) If SpamBayes is set to search for the Habeas
     headers, nine tokens are generated for messages with habeas headers.
     This should be fine, since messages with the headers should either be
     ham, or result in FN so that we can send them to habeas so they can
     be sued.  However, to reduce the strength of habeas headers, we offer
     the ability to reduce the nine tokens to one. (This option has no
     effect if search_for_habeas_headers is False)""",
     BOOLEAN, RESTORE),
  ),

  # These options are all experimental; it seemed better to put them into
  # their own category than have several interdependant experimental options.
  # If this capability is removed, the entire section can go.
  "URLRetriever" : (
    ("x-slurp_urls", "Tokenize text content at the end of URLs", False,
     """(EXPERIMENTAL) If this option is enabled, when a message normally
     scores in the 'unsure' range, and has fewer tokens than the maximum
     looked at, and contains URLs, then the text at those URLs is obtained
     and tokenized.  If those tokens result in the message moving to a
     score outside the 'unsure' range, then they are added to the
     tokens for the message.  This should be particularly effective
     for messages that contain only a single URL and no other text.""",
     BOOLEAN, RESTORE),

    ("x-cache_expiry_days", "Number of days to store URLs in cache", 7,
     """(EXPERIMENTAL) This is the number of days that local cached copies
     of the text at the URLs will be stored for.""",
     INTEGER, RESTORE),

    ("x-cache_directory", "URL Cache Directory", "url-cache",
     """(EXPERIMENTAL) So that SpamBayes doesn't need to retrieve the same
     URL over and over again, it stores local copies of the text at the
     end of the URL.  This is the directory that will be used for those
     copies.""",
     PATH, RESTORE),

    ("x-only_slurp_base", "Retrieve base url", False,
     """(EXPERIMENTAL) To try and speed things up, and to avoid following
     unique URLS, if this option is enabled, SpamBayes will convert the URL
     to as basic a form it we can.  All directory information is removed
     and the domain is reduced to the two (or three for those with a
     country TLD) top-most elements.  For example,
         http://www.massey.ac.nz/~tameyer/index.html?you=me
     would become
         http://massey.ac.nz
     and
         http://id.example.com
     would become http://example.com

     This should have two beneficial effects:
      o It's unlikely that any information could be contained in this 'base'
        url that could identify the user (unless they have a *lot* of domains).
      o Many urls (both spam and ham) will strip down into the same 'base' url.
        Since we have a limited form of caching, this means that a lot fewer
        urls will have to be retrieved.
     However, this does mean that if the 'base' url is hammy and the full is
     spammy, or vice-versa, that the slurp will give back the wrong information.
     Whether or not this is the case would have to be determined by testing.
     """,
     BOOLEAN, RESTORE),

    ("x-web_prefix", "Prefix for tokens from web pages", "",
     """(EXPERIMENTAL) It may be that what is hammy/spammy for you in email
     isn't from webpages.  You can then set this option (to "web:", for
     example), and effectively create an independent (sub)database for
     tokens derived from parsing web pages.""",
     r"[\S]+", RESTORE),
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
     """The maximum number of extreme words to look at in a message, where
     "extreme" means with spam probability farthest away from 0.5.  150
     appears to work well across all corpora tested.""",
     INTEGER, RESTORE),

    ("unknown_word_prob", "Unknown word probability", 0.5,
     """These two control the prior assumption about word probabilities.
     unknown_word_prob is essentially the probability given to a word that
     has never been seen before.  Nobody has reported an improvement via
     moving it away from 1/2, although Tim has measured a mean spamprob of
     a bit over 0.5 (0.51-0.55) in 3 well-trained classifiers.""",
     REAL, RESTORE),

    ("unknown_word_strength", "Unknown word strength", 0.45,
     """This adjusts how much weight to give the prior
     assumption relative to the probabilities estimated by counting.  At 0,
     the counting estimates are believed 100%, even to the extent of
     assigning certainty (0 or 1) to a word that has appeared in only ham
     or only spam.  This is a disaster.

     As unknown_word_strength tends toward infintity, all probabilities
     tend toward unknown_word_prob.  All reports were that a value near 0.4
     worked best, so this does not seem to be corpus-dependent.""",
     REAL, RESTORE),

    ("minimum_prob_strength", "Minimum probability strength", 0.1,
     """When scoring a message, ignore all words with
     abs(word.spamprob - 0.5) < minimum_prob_strength.
     This may be a hack, but it has proved to reduce error rates in many
     tests.  0.1 appeared to work well across all corpora.""",
     REAL, RESTORE),

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

    ("x-use_bigrams", "Use mixed uni/bi-grams scheme", False,
     """(EXPERIMENTAL) Generate both unigrams (words) and bigrams (pairs of
     words). However, extending an idea originally from Gary Robinson, the
     message is 'tiled' into non-overlapping unigrams and bigrams,
     approximating the strongest outcome over all possible tilings.

     Note that to really test this option you need to retrain with it on,
     so that your database includes the bigrams - if you subsequently turn
     it off, these tokens will have no effect.  This option will at least
     double your database size given the same training data, and will
     probably at least triple it.

     You may also wish to increase the max_discriminators (maximum number
     of extreme words) option if you enable this option, perhaps doubling or
     quadrupling it.  It's not yet clear.  Bigrams create many more hapaxes,
     and that seems to increase the brittleness of minimalist training
     regimes; increasing max_discriminators may help to soften that effect.
     OTOH, max_discriminators defaults to 150 in part because that makes it
     easy to prove that the chi-squared math is immune from numeric
     problems.  Increase it too much, and insane results will eventually
     result (including fatal floating-point exceptions on some boxes).

     This option is experimental, and may be removed in a future release.
     We would appreciate feedback about it if you use it - email
     spambayes@python.org with your comments and results.
     """,
     BOOLEAN, RESTORE),
  ),

  "Hammie": (
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
    ("persistent_use_database", "Use database for storage", "dbm",
     """SpamBayes can use either a database (quick to score one message)
     or a pickle (quick to train on huge amounts of messages). There is
     also (currently experimental) the ability to use a mySQL or
     PostgrepSQL database.  For historical reasons, if you set this to
     "True" you are selecting "dbm" and if you set this to "False" you
     are selecting "pickle".  We recommend explicitly selecting the type,
     (i.e. changing "True" to "dbm" and "False" to "pickle", or sticking
     with the default.""",
     # True == "dbm", False == "pickle", "True" == "dbm", "False" == "pickle"
     ("mysql", "pgsql", "dbm", "pickle", "True", "False", True, False), RESTORE),

    ("persistent_storage_file", "Storage file name", "hammie.db",
     """Spambayes builds a database of information that it gathers
     from incoming emails and from you, the user, to get better and
     better at classifying your email.  This option specifies the
     name of the database file.  If you don't give a full pathname,
     the name will be taken to be relative to the location of the
     most recent configuration file loaded.""",
     FILE_WITH_PATH, DO_NOT_RESTORE),

    ("messageinfo_storage_file", "Message information file name", "spambayes.messageinfo.db",
     """Spambayes builds a database of information about messages
     that it has already seen and trained or classified.  This
     database is used to ensure that these messages are not retrained
     or reclassified (unless specifically requested to).  This option
     specifies the name of the database file.  If you don't give a
     full pathname, the name will be taken to be relative to the location
     of the most recent configuration file loaded.""",
     FILE_WITH_PATH, DO_NOT_RESTORE),

    ("cache_use_gzip", "Use gzip", False,
     """Use gzip to compress the cache.""",
     BOOLEAN, RESTORE),

    ("cache_expiry_days", "Days before cached messages expire", 7,
     """Messages will be expired from the cache after this many days.
     After this time, you will no longer be able to train on these messages
     (note this does not effect the copy of the message that you have in
     your mail client).""",
     INTEGER, RESTORE),

    ("spam_cache", "Spam cache directory", "pop3proxy-spam-cache",
     """Directory that SpamBayes should cache spam in.  If this does
     not exist, it will be created.""",
     PATH, DO_NOT_RESTORE),

    ("ham_cache", "Ham cache directory", "pop3proxy-ham-cache",
     """Directory that SpamBayes should cache ham in.  If this does
     not exist, it will be created.""",
     PATH, DO_NOT_RESTORE),

    ("unknown_cache", "Unknown cache directory", "pop3proxy-unknown-cache",
     """Directory that SpamBayes should cache unclassified messages in.
     If this does not exist, it will be created.""",
     PATH, DO_NOT_RESTORE),

    ("cache_messages", "Cache messages", True,
     """You can disable the pop3proxy caching of messages.  This
     will make the proxy a bit faster, and make it use less space
     on your hard drive.  The proxy uses its cache for reviewing
     and training of messages, so if you disable caching you won't
     be able to do further training unless you re-enable it.
     Thus, you should only turn caching off when you are satisfied
     with the filtering that Spambayes is doing for you.""",
     BOOLEAN, RESTORE),

    ("no_cache_bulk_ham", "Suppress caching of bulk ham", False,
     """Where message caching is enabled, this option suppresses caching
     of messages which are classified as ham and marked as
     'Precedence: bulk' or 'Precedence: list'.  If you subscribe to a
     high-volume mailing list then your 'Review messages' page can be
     overwhelmed with list messages, making training a pain.  Once you've
     trained Spambayes on enough list traffic, you can use this option
     to prevent that traffic showing up in 'Review messages'.""",
     BOOLEAN, RESTORE),

    ("no_cache_large_messages", "Maximum size of cached messages", 0,
     """Where message caching is enabled, this option suppresses caching
     of messages which are larger than this value (measured in bytes).
     If you receive a lot of messages that include large attachments
     (and are correctly classified), you may not wish to cache these.
     If you set this to zero (0), then this option will have no effect.""",
     INTEGER, RESTORE),
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
    # three words:
    ("header_spam_string", "Spam disposition name", "spam",
     """The header that Spambayes inserts into each email has a name,
     (Classification eader name, above), and a value.  If the classifier
     determines that this email is probably spam, it places a header named
     as above with a value as specified by this string.  The default
     value should work just fine, but you may change it to anything
     that you wish.""",
     HEADER_VALUE, RESTORE),

    ("header_ham_string", "Ham disposition name", "ham",
     """As for Spam Designation, but for emails classified as Ham.""",
     HEADER_VALUE, RESTORE),

    ("header_unsure_string", "Unsure disposition name", "unsure",
     """As for Spam/Ham Designation, but for emails which the
     classifer wasn't sure about (ie. the spam probability fell between
     the Ham and Spam Cutoffs).  Emails that have this classification
     should always be the subject of training.""",
     HEADER_VALUE, RESTORE),

    ("header_score_digits", "Accuracy of reported score", 2,
     """Accuracy of the score in the header in decimal digits.""",
     INTEGER, RESTORE),

    ("header_score_logarithm", "Augment score with logarithm", False,
     """Set this option to augment scores of 1.00 or 0.00 by a
     logarithmic "one-ness" or "zero-ness" score (basically it shows the
     "number of zeros" or "number of nines" next to the score value).""",
     BOOLEAN, RESTORE),

    ("include_score", "Add probability (score) header", False,
     """You can have Spambayes insert a header with the calculated spam
     probability into each mail.  If you can view headers with your
     mailer, then you can see this information, which can be interesting
     and even instructive if you're a serious SpamBayes junkie.""",
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

    ("include_trained", "Add trained header", True,
     """sb_mboxtrain.py can add a header that details how a message was
     trained, which lets you keep track of it, and appropriately
     re-train messages.  However, if you would rather mboxtrain didn't
     rewrite the message files, you can disable this option.""",
     BOOLEAN, RESTORE),

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

    ("add_unique_id", "Add unique spambayes id", True,
     """If you wish to be able to find a specific message (via the 'find'
     box on the home page), or use the SMTP proxy to train using cached
     messages, you will need to know the unique id of each message.  This
     option adds this information to a header added to each message.""",
     BOOLEAN, RESTORE),

    ("notate_to", "Notate to", (),
     """Some email clients (Outlook Express, for example) can only set up
     filtering rules on a limited set of headers.  These clients cannot
     test for the existence/value of an arbitrary header and filter mail
     based on that information.  To accommodate these kind of mail clients,
     you can add "spam", "ham", or "unsure" to the recipient list.  A
     filter rule can then use this to see if one of these words (followed
     by a comma) is in the recipient list, and route the mail to an
     appropriate folder, or take whatever other action is supported and
     appropriate for the mail classification.

     As it interferes with replying, you may only wish to do this for
     spam messages; simply tick the boxes of the classifications take
     should be identified in this fashion.""",
     ("ham", "spam", "unsure"), RESTORE),

    ("notate_subject", "Classify in subject: header", (),
     """This option will add the same information as 'Notate To',
     but to the start of the mail subject line.""",
     ("ham", "spam", "unsure"), RESTORE),
  ),

  # pop3proxy settings: The only mandatory option is pop3proxy_servers, eg.
  # "pop3.my-isp.com:110", or a comma-separated list of those.  The ":110"
  # is optional.  If you specify more than one server in pop3proxy_servers,
  # you must specify the same number of ports in pop3proxy_ports.
  "pop3proxy" : (
    ("remote_servers", "Remote Servers", (),
     """The SpamBayes POP3 proxy intercepts incoming email and classifies
     it before sending it on to your email client.  You need to specify
     which POP3 server(s) you wish it to intercept - a POP3 server
     address typically looks like "pop3.myisp.net".  If you use more than
     one server, simply separate their names with commas.  You can get
     these server names from your existing email configuration, or from
     your ISP or system administrator.  If you are using Web-based email,
     you can't use the SpamBayes POP3 proxy (sorry!).  In your email
     client's configuration, where you would normally put your POP3 server
     address, you should now put the address of the machine running
     SpamBayes.""",
     SERVER, DO_NOT_RESTORE),

    ("listen_ports", "SpamBayes Ports", (),
     """Each POP3 server that is being monitored must be assigned to a
     'port' in the SpamBayes POP3 proxy.  This port must be different for
     each monitored server, and there must be a port for
     each monitored server.  Again, you need to configure your email
     client to use this port.  If there are multiple servers, you must
     specify the same number of ports as servers, separated by commas.
     If you don't know what to use here, and you only have one server,
     try 110, or if that doesn't work, try 8110.""",
     SERVER, DO_NOT_RESTORE),

    ("allow_remote_connections", "Allowed remote POP3 connections", "localhost",
     """Enter a list of trusted IPs, separated by commas. Remote POP
     connections from any of them will be allowed. You can trust any
     IP using a single '*' as field value. You can also trust ranges of
     IPs using the '*' character as a wildcard (for instance 192.168.0.*).
     The localhost IP will always be trusted. Type 'localhost' in the
     field to trust this only address.""",
     IP_LIST, RESTORE),
  ),

  "smtpproxy" : (
    ("remote_servers", "Remote Servers", (),
     """Use of the SMTP proxy is optional - if you would rather just train
     via the web interface, or the pop3dnd or mboxtrain scripts, then you
     can safely leave this option blank.  The Spambayes SMTP proxy
     intercepts outgoing email - if you forward mail to one of the
     addresses below, it is examined for an id and the message
     corresponding to that id is trained as ham/spam.  All other mail is
     sent along to your outgoing mail server.  You need to specify which
     SMTP server(s) you wish it to intercept - a SMTP server address
     typically looks like "smtp.myisp.net".  If you use more than one
     server, simply separate their names with commas.  You can get these
     server names from your existing email configuration, or from your ISP
     or system administrator.  If you are using Web-based email, you can't
     use the Spambayes SMTP proxy (sorry!).  In your email client's
     configuration, where you would normally put your SMTP server address,
     you should now put the address of the machine running SpamBayes.""",
     SERVER, DO_NOT_RESTORE),

    ("listen_ports", "SpamBayes Ports", (),
     """Each SMTP server that is being monitored must be assigned to a
     'port' in the Spambayes SMTP proxy.  This port must be different for
     each monitored server, and there must be a port for
     each monitored server.  Again, you need to configure your email
     client to use this port.  If there are multiple servers, you must
     specify the same number of ports as servers, separated by commas.""",
     SERVER, DO_NOT_RESTORE),

    ("allow_remote_connections", "Allowed remote SMTP connections", "localhost",
     """Enter a list of trusted IPs, separated by commas. Remote SMTP
     connections from any of them will be allowed. You can trust any
     IP using a single '*' as field value. You can also trust ranges of
     IPs using the '*' character as a wildcard (for instance 192.168.0.*).
     The localhost IP will always be trusted. Type 'localhost' in the
     field to trust this only address.  Note that you can unwittingly
     turn a SMTP server into an open proxy if you open this up, as
     connections to the server will appear to be from your machine, even
     if they are from a remote machine *through* your machine, to the
     server.  We do not recommend opening this up fully (i.e. using '*').
     """,
     IP_LIST, RESTORE),

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

    ("use_cached_message", "Lookup message in cache", False,
     """If this option is set, then the smtpproxy will attempt to
     look up the messages sent to it (for training) in the POP3 proxy cache
     or IMAP filter folders, and use that message as the training data.
     This avoids any problems where your mail client might change the
     message when forwarding, contaminating your training data.  If you can
     be sure that this won't occur, then the id-lookup can be avoided.

     Note that Outlook Express users cannot use the lookup option (because
     of the way messages are forwarded), and so if they wish to use the
     SMTP proxy they must enable this option (but as messages are altered,
     may not get the best results, and this is not recommended).""",
     BOOLEAN, RESTORE),
  ),

  "html_ui" : (
    ("port", "Port", 8880,
     """""",
     PORT, RESTORE),

    ("launch_browser", "Launch browser", False,
     """If this option is set, then whenever sb_server or sb_imapfilter is
     started the default web browser will be opened to the main web
     interface page.  Use of the -b switch when starting from the command
     line overrides this option.""",
     BOOLEAN, RESTORE),

    ("allow_remote_connections", "Allowed remote UI connections", "localhost",
     """Enter a list of trusted IPs, separated by commas. Remote
     connections from any of them will be allowed. You can trust any
     IP using a single '*' as field value. You can also trust ranges of
     IPs using the '*' character as a wildcard (for instance 192.168.0.*).
     The localhost IP will always be trusted. Type 'localhost' in the
     field to trust this only address.""",
     IP_LIST, RESTORE),

    ("display_headers", "Headers to display in message review", ("Subject", "From"),
     """When reviewing messages via the web user interface, you are
     presented with various information about the message.  By default, you
     are shown the subject and who the message is from.  You can add other
     message headers to display, however, such as the address the message
     is to, or the date that the message was sent.""",
     HEADER_NAME, RESTORE),

    ("display_received_time", "Display date received in message review", False,
     """When reviewing messages via the web user interface, you are
     presented with various information about the message.  If you set
     this option, you will be shown the date that the message was received.
     """,
     BOOLEAN, RESTORE),

    ("display_score", "Display score in message review", False,
     """When reviewing messages via the web user interface, you are
     presented with various information about the message.  If you
     set this option, this information will include the score that
     the message received when it was classified.  You might wish to
     see this purely out of curiousity, or you might wish to only
     train on messages that score towards the boundaries of the
     classification areas.  Note that in order to use this option,
     you must also enable the option to include the score in the
     message headers.""",
     BOOLEAN, RESTORE),

    ("display_adv_find", "Display the advanced find query", False,
     """Present advanced options in the 'Word Query' box on the front page,
     including wildcard and regular expression searching.""",
     BOOLEAN, RESTORE),

    ("default_ham_action", "Default training for ham", "ham",
     """When presented with the review list in the web interface,
     which button would you like checked by default when the message
     is classified as ham?""",
     ("ham", "spam", "discard", "defer"), RESTORE),

    ("default_spam_action", "Default training for spam", "spam",
     """When presented with the review list in the web interface,
     which button would you like checked by default when the message
     is classified as spam?""",
     ("ham", "spam", "discard", "defer"), RESTORE),

    ("default_unsure_action", "Default training for unsure", "defer",
     """When presented with the review list in the web interface,
     which button would you like checked by default when the message
     is classified as unsure?""",
     ("ham", "spam", "discard", "defer"), RESTORE),

    ("ham_discard_level", "Ham Discard Level", 0.0,
     """Hams scoring less than this percentage will default to being
        discarded in the training interface (they won't be trained). You'll
        need to turn off the 'Train when filtering' option, above, for this
        to have any effect""",
     REAL, RESTORE),

    ("spam_discard_level", "Spam Discard Level", 100.0,
     """Spams scoring more than this percentage will default to being
        discarded in the training interface (they won't be trained). You'll
        need to turn off the 'Train when filtering' option, above, for this
        to have any effect""",
     REAL, RESTORE),

    ("http_authentication", "HTTP Authentication", "None",
     """This option lets you choose the security level of the web interface.
     When selecting Basic or Digest, the user will be prompted a login and a
     password to access the web interface. The Basic option is faster, but
     transmits the password in clear on the network. The Digest option
     encrypts the password before transmission.""",
     ("None", "Basic", "Digest"), RESTORE),

    ("http_user_name", "User name", "admin",
     """If you activated the HTTP authentication option, you can modify the
     authorized user name here.""",
     r"[\w]+", RESTORE),

    ("http_password", "Password", "admin",
     """If you activated the HTTP authentication option, you can modify the
     authorized user password here.""",
     r"[\w]+", RESTORE),

    ("rows_per_section", "Rows per section", 10000,
     """Number of rows to display per ham/spam/unsure section.""",
     INTEGER, RESTORE),
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
     """Use SSL to connect to the server. This allows spambayes to connect
     without sending the password in plain text.

     Note that this does not check the server certificate at this point in
     time.""",
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

    ("move_trained_spam_to_folder", "Folder to move trained spam to", "",
     """When training, all messages in the spam training folder(s) (above)
     are examined - if they are new, they are used to train, if not, they
     are ignored.  This examination does take time, however, so if speed
     is an issue for you, you may wish to move messages out of this folder
     once they have been trained (either to delete them or to a storage
     folder).  If a folder name is specified here, this will happen
     automatically.  Note that the filter is not yet clever enough to
     move the mail to different folders depending on which folder it
     was originally in - *all* messages will be moved to the same
     folder.""",
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("move_trained_ham_to_folder", "Folder to move trained ham to", "",
     """When training, all messages in the ham training folder(s) (above)
     are examined - if they are new, they are used to train, if not, they
     are ignored.  This examination does take time, however, so if speed
     is an issue for you, you may wish to move messages out of this folder
     once they have been trained (either to delete them or to a storage
     folder).  If a folder name is specified here, this will happen
     automatically.  Note that the filter is not yet clever enough to
     move the mail to different folders depending on which folder it
     was originally in - *all* messages will be moved to the same
     folder.""",
     IMAP_FOLDER, DO_NOT_RESTORE),
  ),

  "ZODB" : (
    ("zeo_addr", "", "",
     """""",
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("event_log_file", "", "",
     """""",
     IMAP_ASTRING, RESTORE),

    ("folder_dir", "", "",
     """""",
     PATH, DO_NOT_RESTORE),

    ("ham_folders", "", "",
     """""",
     PATH, DO_NOT_RESTORE),

    ("spam_folders", "", "",
     """""",
     PATH, DO_NOT_RESTORE),

    ("event_log_severity", "", 0,
     """""",
     INTEGER, RESTORE),

    ("cache_size", "", 2000,
     """""",
     INTEGER, RESTORE),
  ),

  "imapserver" : (
    ("username", "Username", "",
     """The username to use when logging into the SpamBayes IMAP server.""",
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("password", "Password", "",
     """The password to use when logging into the SpamBayes IMAP server.""",
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("port", "IMAP Listen Port", 143,
     """The port to serve the SpamBayes IMAP server on.""",
     PORT, RESTORE),
  ),

  "globals" : (
    ("verbose", "Verbose", False,
     """""",
     BOOLEAN, RESTORE),

    ("dbm_type", "Database storage type", "best",
     """What DBM storage type should we use?  Must be best, db3hash,
     dbhash or gdbm.  Windows folk should steer clear of dbhash.  Default
     is "best", which will pick the best DBM type available on your
     platform.""",
     ("best", "db3hash", "dbhash", "gdbm"), RESTORE),

    ("proxy_username", "HTTP Proxy Username", "",
     """The username to give to the HTTP proxy when required.  If a
     username is not necessary, simply leave blank.""",
     r"[\w]+", DO_NOT_RESTORE),
    ("proxy_password", "HTTP Proxy Password", "",
     """The password to give to the HTTP proxy when required.  This is
     stored in clear text in your configuration file, so if that bothers
     you then don't do this.  You'll need to use a proxy that doesn't need
     authentication, or do without any SpamBayes HTTP activity.""",
     r"[\w]+", DO_NOT_RESTORE),
    ("proxy_server", "HTTP Proxy Server", "",
     """If a spambayes application needs to use HTTP, it will try to do so
     through this proxy server.  The port defaults to 8080, or can be
     entered with the server:port form.""",
     SERVER, DO_NOT_RESTORE),
  ),
}


# `optionsPathname` is the pathname of the last ini file in the list.
# This is where the web-based configuration page will write its changes.
# If no ini files are found, it defaults to bayescustomize.ini in the
# current working directory.
optionsPathname = None

# The global options object - created by load_options
options = None

def load_options():
    global optionsPathname, options
    options = OptionsClass()
    options.load_defaults(defaults)

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
        if sys.platform.startswith("win") and \
           not os.path.isfile(optionsPathname):
            # If we are on Windows and still don't have an INI, default to the
            # 'per-user' directory.
            try:
                from win32com.shell import shell, shellcon
            except ImportError:
                # We are on Windows, with no BAYESCUSTOMIZE set, no ini file
                # in the current directory, and no win32 extensions installed
                # to locate the "user" directory - seeing things are so lamely
                # setup, it is worth printing a warning
                print >>sys.stderr, "NOTE: We can not locate an INI file " \
                      "for SpamBayes, and the Python for Windows extensions " \
                      "are not installed, meaning we can't locate your " \
                      "'user' directory.  An empty configuration file at " \
                      "'%s' will be used." % optionsPathname.encode('mbcs')
            else:
                windowsUserDirectory = os.path.join(
                        shell.SHGetFolderPath(0,shellcon.CSIDL_APPDATA,0,0),
                        "SpamBayes", "Proxy")
                try:
                    if not os.path.isdir(windowsUserDirectory):
                        os.makedirs(windowsUserDirectory)
                except os.error:
                    # unable to make the directory - stick to default.
                    pass
                else:
                    optionsPathname = os.path.join(windowsUserDirectory,
                                                   'bayescustomize.ini')
                    # Not everyone is unicode aware - keep it a string.
                    optionsPathname = optionsPathname.encode("mbcs")
                    # If the file exists, then load it.
                    if os.path.exists(optionsPathname):
                        options.merge_file(optionsPathname)

    # Annoyingly, we have a special case.  The notate_to and notate_subject
    # allowed values have to be set to the same values as the header_x_
    # options, but this can't be done (AFAIK) dynmaically. If this isn't
    # the case, then if the header_x_string values are changed, the
    # notate_ options don't work.  Outlook Express users like both of
    # these options...so we fix it here.  See also sf #944109.
    header_strings = (options["Headers", "header_ham_string"],
                      options["Headers", "header_spam_string"],
                      options["Headers", "header_unsure_string"])
    notate_to = options.get_option("Headers", "notate_to")
    notate_subject = options.get_option("Headers", "notate_subject")
    notate_to.allowed_values = header_strings
    notate_subject.allowed_values = header_strings


def get_pathname_option(section, option):
    """Return the option relative to the path specified in the
    gloabl optionsPathname, unless it is already an absolute path."""
    filename = os.path.expanduser(options.get(section, option))
    if os.path.isabs(filename):
        return filename
    return os.path.join(os.path.dirname(optionsPathname), filename)

# Ideally, we should not create the objects at import time - but we have
# done it this way forever!
# We avoid having the options loading code at the module level, as then
# the only way to re-read is to reload this module, and as at 2.3, that
# doesn't work in a .zip file.
load_options()
