#! /usr/bin/env python
"""Module to tokenize email messages for spam filtering."""

from __future__ import generators

import email
import email.Message
import email.Header
import email.Utils
import email.Errors
import re
import math
import time
import os
import binascii
import urlparse
import urllib
try:
    # We have three possibilities for Set:
    #  (a) With Python 2.2 and earlier, we use our compatsets class
    #  (b) With Python 2.3, we use the sets.Set class
    #  (c) With Python 2.4 and later, we use the builtin set class
    Set = set
except NameError:
    try:
        from sets import Set
    except ImportError:
        from spambayes.compatsets import Set

from spambayes import classifier
from spambayes.Options import options

from spambayes.mboxutils import get_message

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


try:
    import dnscache
    cache = dnscache.cache(cachefile=options["Tokenizer", "lookup_ip_cache"])
    cache.printStatsAtEnd = True
except (IOError, ImportError):
    cache = None
else:
    import atexit
    atexit.register(cache.close)

 
# Patch encodings.aliases to recognize 'ansi_x3_4_1968'
from encodings.aliases import aliases # The aliases dictionary
if not aliases.has_key('ansi_x3_4_1968'):
    aliases['ansi_x3_4_1968'] = 'ascii'
del aliases # Not needed any more

##############################################################################
# To fold case or not to fold case?  I didn't want to fold case, because
# it hides information in English, and I have no idea what .lower() does
# to other languages; and, indeed, 'FREE' (all caps) turned out to be one
# of the strongest spam indicators in my content-only tests (== one with
# prob 0.99 *and* made it into spamprob's nbest list very often).
#
# Against preservering case, it makes the database size larger, and requires
# more training data to get enough "representative" mixed-case examples.
#
# Running my c.l.py tests didn't support my intuition that case was
# valuable, so it's getting folded away now.  Folding or not made no
# significant difference to the false positive rate, and folding made a
# small (but statistically significant all the same) reduction in the
# false negative rate.  There is one obvious difference:  after folding
# case, conference announcements no longer got high spam scores.  Their
# content was usually fine, but they were highly penalized for VISIT OUR
# WEBSITE FOR MORE INFORMATION! kinds of repeated SCREAMING.  That is
# indeed the language of advertising, and I halfway regret that folding
# away case no longer picks on them.
#
# Since the f-p rate didn't change, but conference announcements escaped
# that category, something else took their place.  It seems to be highly
# off-topic messages, like debates about Microsoft's place in the world.
# Talk about "money" and "lucrative" is indistinguishable now from talk
# about "MONEY" and "LUCRATIVE", and spam mentions MONEY a lot.


##############################################################################
# Character n-grams or words?
#
# With careful multiple-corpora c.l.py tests sticking to case-folded decoded
# text-only portions, and ignoring headers, and with identical special
# parsing & tagging of embedded URLs:
#
# Character 3-grams gave 5x as many false positives as split-on-whitespace
# (s-o-w).  The f-n rate was also significantly worse, but within a factor
# of 2.  So character 3-grams lost across the board.
#
# Character 5-grams gave 32% more f-ps than split-on-whitespace, but the
# s-o-w fp rate across 20,000 presumed-hams was 0.1%, and this is the
# difference between 23 and 34 f-ps.  There aren't enough there to say that's
# significnatly more with killer-high confidence.  There were plenty of f-ns,
# though, and the f-n rate with character 5-grams was substantially *worse*
# than with character 3-grams (which in turn was substantially worse than
# with s-o-w).
#
# Training on character 5-grams creates many more unique tokens than s-o-w:
# a typical run bloated to 150MB process size.  It also ran a lot slower than
# s-o-w, partly related to heavy indexing of a huge out-of-cache wordinfo
# dict.  I rarely noticed disk activity when running s-o-w, so rarely bothered
# to look at process size; it was under 30MB last time I looked.
#
# Figuring out *why* a msg scored as it did proved much more mysterious when
# working with character n-grams:  they often had no obvious "meaning".  In
# contrast, it was always easy to figure out what s-o-w was picking up on.
# 5-grams flagged a msg from Christian Tismer as spam, where he was discussing
# the speed of tasklets under his new implementation of stackless:
#
#     prob = 0.99999998959
#     prob('ed sw') = 0.01
#     prob('http0:pgp') = 0.01
#     prob('http0:python') = 0.01
#     prob('hlon ') = 0.99
#     prob('http0:wwwkeys') = 0.01
#     prob('http0:starship') = 0.01
#     prob('http0:stackless') = 0.01
#     prob('n xp ') = 0.99
#     prob('on xp') = 0.99
#     prob('p 150') = 0.99
#     prob('lon x') = 0.99
#     prob(' amd ') = 0.99
#     prob(' xp 1') = 0.99
#     prob(' athl') = 0.99
#     prob('1500+') = 0.99
#     prob('xp 15') = 0.99
#
# The spam decision was baffling until I realized that *all* the high-
# probablity spam 5-grams there came out of a single phrase:
#
#     AMD Athlon XP 1500+
#
# So Christian was punished for using a machine lots of spam tries to sell
# <wink>.  In a classic Bayesian classifier, this probably wouldn't have
# mattered, but Graham's throws away almost all the 5-grams from a msg,
# saving only the about-a-dozen farthest from a neutral 0.5.  So one bad
# phrase can kill you!  This appears to happen very rarely, but happened
# more than once.
#
# The conclusion is that character n-grams have almost nothing to recommend
# them under Graham's scheme:  harder to work with, slower, much larger
# database, worse results, and prone to rare mysterious disasters.
#
# There's one area they won hands-down:  detecting spam in what I assume are
# Asian languages.  The s-o-w scheme sometimes finds only line-ends to split
# on then, and then a "hey, this 'word' is way too big!  let's ignore it"
# gimmick kicks in, and produces no tokens at all.
#
# [Later:  we produce character 5-grams then under the s-o-w scheme, instead
# ignoring the blob, but only if there are high-bit characters in the blob;
# e.g., there's no point 5-gramming uuencoded lines, and doing so would
# bloat the database size.]
#
# Interesting:  despite that odd example above, the *kinds* of f-p mistakes
# 5-grams made were very much like s-o-w made -- I recognized almost all of
# the 5-gram f-p messages from previous s-o-w runs.  For example, both
# schemes have a particular hatred for conference announcements, although
# s-o-w stopped hating them after folding case.  But 5-grams still hate them.
# Both schemes also hate msgs discussing HTML with examples, with about equal
# passion.   Both schemes hate brief "please subscribe [unsubscribe] me"
# msgs, although 5-grams seems to hate them more.


##############################################################################
# How to tokenize?
#
# I started with string.split() merely for speed.  Over time I realized it
# was making interesting context distinctions qualitatively akin to n-gram
# schemes; e.g., "free!!" is a much stronger spam indicator than "free".  But
# unlike n-grams (whether word- or character- based) under Graham's scoring
# scheme, this mild context dependence never seems to go over the edge in
# giving "too much" credence to an unlucky phrase.
#
# OTOH, compared to "searching for words", it increases the size of the
# database substantially, less than but close to a factor of 2.  This is very
# much less than a word bigram scheme bloats it, but as always an increase
# isn't justified unless the results are better.
#
# Following are stats comparing
#
#    for token in text.split():  # left column
#
# to
#
#    for token in re.findall(r"[\w$\-\x80-\xff]+", text):  # right column
#
# text is case-normalized (text.lower()) in both cases, and the runs were
# identical in all other respects.  The results clearly favor the split()
# gimmick, although they vaguely suggest that some sort of compromise
# may do as well with less database burden; e.g., *perhaps* folding runs of
# "punctuation" characters into a canonical representative could do that.
# But the database size is reasonable without that, and plain split() avoids
# having to worry about how to "fold punctuation" in languages other than
# English.
#
#    false positive percentages
#        0.000  0.000  tied
#        0.000  0.050  lost
#        0.050  0.150  lost
#        0.000  0.025  lost
#        0.025  0.050  lost
#        0.025  0.075  lost
#        0.050  0.150  lost
#        0.025  0.000  won
#        0.025  0.075  lost
#        0.000  0.025  lost
#        0.075  0.150  lost
#        0.050  0.050  tied
#        0.025  0.050  lost
#        0.000  0.025  lost
#        0.050  0.025  won
#        0.025  0.000  won
#        0.025  0.025  tied
#        0.000  0.025  lost
#        0.025  0.075  lost
#        0.050  0.175  lost
#
#    won   3 times
#    tied  3 times
#    lost 14 times
#
#    total unique fp went from 8 to 20
#
#    false negative percentages
#        0.945  1.200  lost
#        0.836  1.018  lost
#        1.200  1.200  tied
#        1.418  1.636  lost
#        1.455  1.418  won
#        1.091  1.309  lost
#        1.091  1.272  lost
#        1.236  1.563  lost
#        1.564  1.855  lost
#        1.236  1.491  lost
#        1.563  1.599  lost
#        1.563  1.781  lost
#        1.236  1.709  lost
#        0.836  0.982  lost
#        0.873  1.382  lost
#        1.236  1.527  lost
#        1.273  1.418  lost
#        1.018  1.273  lost
#        1.091  1.091  tied
#        1.490  1.454  won
#
#    won   2 times
#    tied  2 times
#    lost 16 times
#
#    total unique fn went from 292 to 302
#
# Later:  Here's another tokenization scheme with more promise.
#
#     fold case, ignore punctuation, strip a trailing 's' from words (to
#     stop Guido griping about "hotel" and "hotels" getting scored as
#     distinct clues <wink>) and save both word bigrams and word unigrams
#
# This was the code:
#
#     # Tokenize everything in the body.
#     lastw = ''
#     for w in word_re.findall(text):
#         n = len(w)
#         # Make sure this range matches in tokenize_word().
#         if 3 <= n <= 12:
#             if w[-1] == 's':
#                 w = w[:-1]
#             yield w
#             if lastw:
#                 yield lastw + w
#             lastw = w + ' '
#
#         elif n >= 3:
#             lastw = ''
#             for t in tokenize_word(w):
#                 yield t
#
# where
#
#     word_re = re.compile(r"[\w$\-\x80-\xff]+")
#
# This at least doubled the process size.  It helped the f-n rate
# significantly, but probably hurt the f-p rate (the f-p rate is too low
# with only 4000 hams per run to be confident about changes of such small
# *absolute* magnitude -- 0.025% is a single message in the f-p table):
#
# false positive percentages
#     0.000  0.000  tied
#     0.000  0.075  lost  +(was 0)
#     0.050  0.125  lost  +150.00%
#     0.025  0.000  won   -100.00%
#     0.075  0.025  won    -66.67%
#     0.000  0.050  lost  +(was 0)
#     0.100  0.175  lost   +75.00%
#     0.050  0.050  tied
#     0.025  0.050  lost  +100.00%
#     0.025  0.000  won   -100.00%
#     0.050  0.125  lost  +150.00%
#     0.050  0.025  won    -50.00%
#     0.050  0.050  tied
#     0.000  0.025  lost  +(was 0)
#     0.000  0.025  lost  +(was 0)
#     0.075  0.050  won    -33.33%
#     0.025  0.050  lost  +100.00%
#     0.000  0.000  tied
#     0.025  0.100  lost  +300.00%
#     0.050  0.150  lost  +200.00%
#
# won   5 times
# tied  4 times
# lost 11 times
#
# total unique fp went from 13 to 21
#
# false negative percentages
#     0.327  0.218  won    -33.33%
#     0.400  0.218  won    -45.50%
#     0.327  0.218  won    -33.33%
#     0.691  0.691  tied
#     0.545  0.327  won    -40.00%
#     0.291  0.218  won    -25.09%
#     0.218  0.291  lost   +33.49%
#     0.654  0.473  won    -27.68%
#     0.364  0.327  won    -10.16%
#     0.291  0.182  won    -37.46%
#     0.327  0.254  won    -22.32%
#     0.691  0.509  won    -26.34%
#     0.582  0.473  won    -18.73%
#     0.291  0.255  won    -12.37%
#     0.364  0.218  won    -40.11%
#     0.436  0.327  won    -25.00%
#     0.436  0.473  lost    +8.49%
#     0.218  0.218  tied
#     0.291  0.255  won    -12.37%
#     0.254  0.364  lost   +43.31%
#
# won  15 times
# tied  2 times
# lost  3 times
#
# total unique fn went from 106 to 94

##############################################################################
# What about HTML?
#
# Computer geeks seem to view use of HTML in mailing lists and newsgroups as
# a mortal sin.  Normal people don't, but so it goes:  in a technical list/
# group, every HTML decoration has spamprob 0.99, there are lots of unique
# HTML decorations, and lots of them appear at the very start of the message
# so that Graham's scoring scheme latches on to them tight.  As a result,
# any plain text message just containing an HTML example is likely to be
# judged spam (every HTML decoration is an extreme).
#
# So if a message is multipart/alternative with both text/plain and text/html
# branches, we ignore the latter, else newbies would never get a message
# through.  If a message is just HTML, it has virtually no chance of getting
# through.
#
# In an effort to let normal people use mailing lists too <wink>, and to
# alleviate the woes of messages merely *discussing* HTML practice, I
# added a gimmick to strip HTML tags after case-normalization and after
# special tagging of embedded URLs.  This consisted of a regexp sub pattern,
# where instances got replaced by single blanks:
#
#    html_re = re.compile(r"""
#        <
#        [^\s<>]     # e.g., don't match 'a < b' or '<<<' or 'i << 5' or 'a<>b'
#        [^>]{0,128} # search for the end '>', but don't chew up the world
#        >
#    """, re.VERBOSE)
#
# and then
#
#    text = html_re.sub(' ', text)
#
# Alas, little good came of this:
#
#    false positive percentages
#        0.000  0.000  tied
#        0.000  0.000  tied
#        0.050  0.075  lost
#        0.000  0.000  tied
#        0.025  0.025  tied
#        0.025  0.025  tied
#        0.050  0.050  tied
#        0.025  0.025  tied
#        0.025  0.025  tied
#        0.000  0.050  lost
#        0.075  0.100  lost
#        0.050  0.050  tied
#        0.025  0.025  tied
#        0.000  0.025  lost
#        0.050  0.050  tied
#        0.025  0.025  tied
#        0.025  0.025  tied
#        0.000  0.000  tied
#        0.025  0.050  lost
#        0.050  0.050  tied
#
#    won   0 times
#    tied 15 times
#    lost  5 times
#
#    total unique fp went from 8 to 12
#
#    false negative percentages
#        0.945  1.164  lost
#        0.836  1.418  lost
#        1.200  1.272  lost
#        1.418  1.272  won
#        1.455  1.273  won
#        1.091  1.382  lost
#        1.091  1.309  lost
#        1.236  1.381  lost
#        1.564  1.745  lost
#        1.236  1.564  lost
#        1.563  1.781  lost
#        1.563  1.745  lost
#        1.236  1.455  lost
#        0.836  0.982  lost
#        0.873  1.309  lost
#        1.236  1.381  lost
#        1.273  1.273  tied
#        1.018  1.273  lost
#        1.091  1.200  lost
#        1.490  1.599  lost
#
#    won   2 times
#    tied  1 times
#    lost 17 times
#
#    total unique fn went from 292 to 327
#
# The messages merely discussing HTML were no longer fps, so it did what it
# intended there.  But the f-n rate nearly doubled on at least one run -- so
# strong a set of spam indicators is the mere presence of HTML.  The increase
# in the number of fps despite that the HTML-discussing msgs left that
# category remains mysterious to me, but it wasn't a significant increase
# so I let it drop.
#
# Later:  If I simply give up on making mailing lists friendly to my sisters
# (they're not nerds, and create wonderfully attractive HTML msgs), a
# compromise is to strip HTML tags from only text/plain msgs.  That's
# principled enough so far as it goes, and eliminates the HTML-discussing
# false positives.  It remains disturbing that the f-n rate on pure HTML
# msgs increases significantly when stripping tags, so the code here doesn't
# do that part.  However, even after stripping tags, the rates above show that
# at least 98% of spams are still correctly identified as spam.
#
# So, if another way is found to slash the f-n rate, the decision here not
# to strip HTML from HTML-only msgs should be revisited.
#
# Later, after the f-n rate got slashed via other means:
#
# false positive percentages
#     0.000  0.000  tied
#     0.000  0.000  tied
#     0.050  0.075  lost   +50.00%
#     0.025  0.025  tied
#     0.075  0.025  won    -66.67%
#     0.000  0.000  tied
#     0.100  0.100  tied
#     0.050  0.075  lost   +50.00%
#     0.025  0.025  tied
#     0.025  0.000  won   -100.00%
#     0.050  0.075  lost   +50.00%
#     0.050  0.050  tied
#     0.050  0.025  won    -50.00%
#     0.000  0.000  tied
#     0.000  0.000  tied
#     0.075  0.075  tied
#     0.025  0.025  tied
#     0.000  0.000  tied
#     0.025  0.025  tied
#     0.050  0.050  tied
#
# won   3 times
# tied 14 times
# lost  3 times
#
# total unique fp went from 13 to 11
#
# false negative percentages
#     0.327  0.400  lost   +22.32%
#     0.400  0.400  tied
#     0.327  0.473  lost   +44.65%
#     0.691  0.654  won     -5.35%
#     0.545  0.473  won    -13.21%
#     0.291  0.364  lost   +25.09%
#     0.218  0.291  lost   +33.49%
#     0.654  0.654  tied
#     0.364  0.473  lost   +29.95%
#     0.291  0.327  lost   +12.37%
#     0.327  0.291  won    -11.01%
#     0.691  0.654  won     -5.35%
#     0.582  0.655  lost   +12.54%
#     0.291  0.400  lost   +37.46%
#     0.364  0.436  lost   +19.78%
#     0.436  0.582  lost   +33.49%
#     0.436  0.364  won    -16.51%
#     0.218  0.291  lost   +33.49%
#     0.291  0.400  lost   +37.46%
#     0.254  0.327  lost   +28.74%
#
# won   5 times
# tied  2 times
# lost 13 times
#
# total unique fn went from 106 to 122
#
# So HTML decorations are still a significant clue when the ham is composed
# of c.l.py traffic.  Again, this should be revisited if the f-n rate is
# slashed again.
#
# Later:  As the amount of training data increased, the effect of retaining
# HTML tags decreased to insignificance.  options.retain_pure_html_tags
# was introduced to control this, and it defaulted to False.  Later, as the
# algorithm improved, retain_pure_html_tags was removed.
#
# Later:  The decision to ignore "redundant" HTML is also dubious, since
# the text/plain and text/html alternatives may have entirely different
# content.  options.ignore_redundant_html was introduced to control this,
# and it defaults to False.  Later:  ignore_redundant_html was also removed.

##############################################################################
# How big should "a word" be?
#
# As I write this, words less than 3 chars are ignored completely, and words
# with more than 12 are special-cased, replaced with a summary "I skipped
# about so-and-so many chars starting with such-and-such a letter" token.
# This makes sense for English if most of the info is in "regular size"
# words.
#
# A test run boosting to 13 had no effect on f-p rate, and did a little
# better or worse than 12 across runs -- overall, no significant difference.
# The database size is smaller at 12, so there's nothing in favor of 13.
# A test at 11 showed a slight but consistent bad effect on the f-n rate
# (lost 12 times, won once, tied 7 times).
#
# A test with no lower bound showed a significant increase in the f-n rate.
# Curious, but not worth digging into.  Boosting the lower bound to 4 is a
# worse idea:  f-p and f-n rates both suffered significantly then.  I didn't
# try testing with lower bound 2.
#
# Anthony Baxter found that boosting the option skip_max_word_size to 20
# from its default of 12 produced a quite dramatic decrease in the number
# of 'unsure' messages.  However, this was coupled with a large increase
# in the FN rate, and it remains unclear whether simply shifting cutoffs
# would have given the same tradeoff (not enough data was posted to tell).
#
# On Tim's c.l.py test, 10-fold CV, ham_cutoff=0.20 and spam_cutoff=0.80:
#
# -> <stat> tested 2000 hams & 1400 spams against 18000 hams & 12600 spams
# [ditto]
#
# filename:    max12   max20
# ham:spam:  20000:14000
#                    20000:14000
# fp total:        2       2       the same
# fp %:         0.01    0.01
# fn total:        0       0       the same
# fn %:         0.00    0.00
# unsure t:      103     100       slight decrease
# unsure %:     0.30    0.29
# real cost:  $40.60  $40.00       slight improvement with these cutoffs
# best cost:  $27.00  $27.40       best possible got slightly worse
# h mean:       0.28    0.27
# h sdev:       2.99    2.92
# s mean:      99.94   99.93
# s sdev:       1.41    1.47
# mean diff:   99.66   99.66
# k:           22.65   22.70
#
# "Best possible" in max20 would have been to boost ham_cutoff to 0.50(!),
# and drop spam_cutoff a little to 0.78.  This would have traded away most
# of the unsures in return for letting 3 spam through:
#
# -> smallest ham & spam cutoffs 0.5 & 0.78
# ->     fp 2; fn 3; unsure ham 11; unsure spam 11
# ->     fp rate 0.01%; fn rate 0.0214%; unsure rate 0.0647%
#
# Best possible in max12 was much the same:
#
# -> largest ham & spam cutoffs 0.5 & 0.78
# ->     fp 2; fn 3; unsure ham 12; unsure spam 8
# ->     fp rate 0.01%; fn rate 0.0214%; unsure rate 0.0588%
#
# The classifier pickle size increased by about 1.5 MB (~8.4% bigger).
#
# Rob Hooft's results were worse:
#
# -> <stat> tested 1600 hams & 580 spams against 14400 hams & 5220 spams
# [...]
# -> <stat> tested 1600 hams & 580 spams against 14400 hams & 5220 spams
# filename:   skip12  skip20
# ham:spam:  16000:5800
#                     16000:5800
# fp total:       12      13
# fp %:         0.07    0.08
# fn total:        7       7
# fn %:         0.12    0.12
# unsure t:      178     184
# unsure %:     0.82    0.84
# real cost: $162.60 $173.80
# best cost: $106.20 $109.60
# h mean:       0.51    0.52
# h sdev:       4.87    4.92
# s mean:      99.42   99.39
# s sdev:       5.22    5.34
# mean diff:   98.91   98.87
# k:            9.80    9.64


# textparts(msg) returns a set containing all the text components of msg.
# There's no point decoding binary blobs (like images).  If a text/plain
# and text/html part happen to have redundant content, it doesn't matter
# to results, since training and scoring are done on the set of all
# words in the msg, without regard to how many times a given word appears.
def textparts(msg):
    """Return a set of all msg parts with content maintype 'text'."""
    return Set(filter(lambda part: part.get_content_maintype() == 'text',
                      msg.walk()))

def octetparts(msg):
    """Return a set of all msg parts with type 'application/octet-stream'."""
    return Set(filter(lambda part:
                      part.get_content_type() == 'application/octet-stream',
                      msg.walk()))

def imageparts(msg):
    """Return a list of all msg parts with type 'image/*'."""
    # Don't want a set here because we want to be able to process them in
    # order.
    return filter(lambda part:
                  part.get_content_type().startswith('image/'),
                  msg.walk())

has_highbit_char = re.compile(r"[\x80-\xff]").search

# Cheap-ass gimmick to probabilistically find HTML/XML tags.
# Note that <style and HTML comments are handled by crack_html_style()
# and crack_html_comment() instead -- they can be very long, and long
# minimal matches have a nasty habit of blowing the C stack.
html_re = re.compile(r"""
    <
    (?![\s<>])  # e.g., don't match 'a < b' or '<<<' or 'i<<5' or 'a<>b'
    # guessing that other tags are usually "short"
    [^>]{0,256} # search for the end '>', but don't run wild
    >
""", re.VERBOSE | re.DOTALL)

# Trailing letter serves to reject "hostnames" which are really ip
# addresses.  Some spammers forge their apparent ip addresses, so you get
# Received: headers which look like:
#   Received: from 199.249.165.175 ([218.5.93.116])
#       by manatee.mojam.com (8.12.1-20030917/8.12.1) with SMTP id
#       hBIERsqI018090
#       for <itinerary@musi-cal.com>; Thu, 18 Dec 2003 08:28:11 -0600
# "199.249.165.175" is who the spamhaus said it was.  That's really the
# ip address of the receiving host (manatee.mojam.com), which correctly
# identified the sender's ip address as 218.5.93.116.
#
# Similarly, the more complex character set instead of just \S serves to
# reject Received: headers where the message bounces from one user to
# another on the local machine:
#   Received: (from itin@localhost)
#       by manatee.mojam.com (8.12.1-20030917/8.12.1/Submit) id hBIEQFxF018044
#       for skip@manatee.mojam.com; Thu, 18 Dec 2003 08:26:15 -0600
received_host_re = re.compile(r'from ([a-z0-9._-]+[a-z])[)\s]')
# 99% of the time, the receiving host places the sender's ip address in
# square brackets as it should, but every once in awhile it turns up in
# parens.  Yahoo seems to be guilty of this minor infraction:
#   Received: from unknown (66.218.66.218)
#       by m19.grp.scd.yahoo.com with QMQP; 19 Dec 2003 04:06:53 -0000
received_ip_re = re.compile(r'[[(]((\d{1,3}\.?){4})[])]')

message_id_re = re.compile(r'\s*<[^@]+@([^>]+)>\s*')

# I'm usually just splitting on whitespace, but for subject lines I want to
# break things like "Python/Perl comparison?" up.  OTOH, I don't want to
# break up the unitized numbers in spammish subject phrases like "Increase
# size 79%" or "Now only $29.95!".  Then again, I do want to break up
# "Python-Dev".  Runs of punctuation are also interesting in subject lines.
subject_word_re = re.compile(r"[\w\x80-\xff$.%]+")
punctuation_run_re = re.compile(r'\W+')

fname_sep_re = re.compile(r'[/\\:]')

def crack_filename(fname):
    yield "fname:" + fname
    components = fname_sep_re.split(fname)
    morethan1 = len(components) > 1
    for component in components:
        if morethan1:
            yield "fname comp:" + component
        pieces = urlsep_re.split(component)
        if len(pieces) > 1:
            for piece in pieces:
                yield "fname piece:" + piece

def tokenize_word(word, _len=len, maxword=options["Tokenizer",
                                                  "skip_max_word_size"]):
    n = _len(word)
    # Make sure this range matches in tokenize().
    if 3 <= n <= maxword:
        yield word

    elif n >= 3:
        # A long word.

        # Don't want to skip embedded email addresses.
        # An earlier scheme also split up the y in x@y on '.'.  Not splitting
        # improved the f-n rate; the f-p rate didn't care either way.
        if n < 40 and '.' in word and word.count('@') == 1:
            p1, p2 = word.split('@')
            yield 'email name:' + p1
            yield 'email addr:' + p2

        else:
            # There's value in generating a token indicating roughly how
            # many chars were skipped.  This has real benefit for the f-n
            # rate, but is neutral for the f-p rate.  I don't know why!
            # XXX Figure out why, and/or see if some other way of summarizing
            # XXX this info has greater benefit.
            if options["Tokenizer", "generate_long_skips"]:
                yield "skip:%c %d" % (word[0], n // 10 * 10)
            if has_highbit_char(word):
                hicount = 0
                for i in map(ord, word):
                    if i >= 128:
                        hicount += 1
                yield "8bit%%:%d" % round(hicount * 100.0 / len(word))

# Generate tokens for:
#    Content-Type
#        and its type= param
#    Content-Dispostion
#        and its filename= param
#    all the charsets
#
# This has huge benefit for the f-n rate, and virtually no effect on the f-p
# rate, although it does reduce the variance of the f-p rate across different
# training sets (really marginal msgs, like a brief HTML msg saying just
# "unsubscribe me", are almost always tagged as spam now; before they were
# right on the edge, and now the multipart/alternative pushes them over it
# more consistently).
#
# XXX I put all of this in as one chunk.  I don't know which parts are
# XXX most effective; it could be that some parts don't help at all.  But
# XXX given the nature of the c.l.py tests, it's not surprising that the
# XXX     'content-type:text/html'
# XXX token is now the single most powerful spam indicator (== makes it
# XXX into the nbest list most often).  What *is* a little surprising is
# XXX that this doesn't push more mixed-type msgs into the f-p camp --
# XXX unlike looking at *all* HTML tags, this is just one spam indicator
# XXX instead of dozens, so relevant msg content can cancel it out.
#
# A bug in this code prevented Content-Transfer-Encoding from getting
# picked up.  Fixing that bug showed that it didn't help, so the corrected
# code is disabled now (left column without Content-Transfer-Encoding,
# right column with it);
#
# false positive percentages
#    0.000  0.000  tied
#    0.000  0.000  tied
#    0.100  0.100  tied
#    0.000  0.000  tied
#    0.025  0.025  tied
#    0.025  0.025  tied
#    0.100  0.100  tied
#    0.025  0.025  tied
#    0.025  0.025  tied
#    0.050  0.050  tied
#    0.100  0.100  tied
#    0.025  0.025  tied
#    0.025  0.025  tied
#    0.025  0.025  tied
#    0.025  0.025  tied
#    0.025  0.025  tied
#    0.025  0.025  tied
#    0.000  0.025  lost  +(was 0)
#    0.025  0.025  tied
#    0.100  0.100  tied
#
# won   0 times
# tied 19 times
# lost  1 times
#
# total unique fp went from 9 to 10
#
# false negative percentages
#    0.364  0.400  lost    +9.89%
#    0.400  0.364  won     -9.00%
#    0.400  0.436  lost    +9.00%
#    0.909  0.872  won     -4.07%
#    0.836  0.836  tied
#    0.618  0.618  tied
#    0.291  0.291  tied
#    1.018  0.981  won     -3.63%
#    0.982  0.982  tied
#    0.727  0.727  tied
#    0.800  0.800  tied
#    1.163  1.127  won     -3.10%
#    0.764  0.836  lost    +9.42%
#    0.473  0.473  tied
#    0.473  0.618  lost   +30.66%
#    0.727  0.763  lost    +4.95%
#    0.655  0.618  won     -5.65%
#    0.509  0.473  won     -7.07%
#    0.545  0.582  lost    +6.79%
#    0.509  0.509  tied
#
# won   6 times
# tied  8 times
# lost  6 times
#
# total unique fn went from 168 to 169

# For support of the replace_nonascii_chars option, build a string.translate
# table that maps all high-bit chars and control chars to a '?' character.

non_ascii_translate_tab = ['?'] * 256
# leave blank up to (but not including) DEL alone
for i in range(32, 127):
    non_ascii_translate_tab[i] = chr(i)
# leave "normal" whitespace alone
for ch in ' \t\r\n':
    non_ascii_translate_tab[ord(ch)] = ch
del i, ch

non_ascii_translate_tab = ''.join(non_ascii_translate_tab)


def crack_content_xyz(msg):
    yield 'content-type:' + msg.get_content_type()

    x = msg.get_param('type')
    if x is not None:
        yield 'content-type/type:' + x.lower()

    try:
        for x in msg.get_charsets(None):
            if x is not None:
                yield 'charset:' + x.lower()
    except UnicodeEncodeError:
        # Bad messages can cause an exception here.
        # See [ 1175439 ] UnicodeEncodeError raised for bogus Content-Type
        #                 header
        yield 'charset:invalid_unicode'

    x = msg.get('content-disposition')
    if x is not None:
        yield 'content-disposition:' + x.lower()

    try:
        fname = msg.get_filename()
        if fname is not None:
            for x in crack_filename(fname):
                yield 'filename:' + x
    except TypeError:
        # bug in email pkg?  see the thread beginning at
        # http://mail.python.org/pipermail/spambayes/2003-September/008006.html
        # and
        # http://mail.python.org/pipermail/spambayes-dev/2003-September/001177.html
        yield "filename:<bogus>"

    if 0:   # disabled; see comment before function
        x = msg.get('content-transfer-encoding')
        if x is not None:
            yield 'content-transfer-encoding:' + x.lower()

# The base64 decoder is actually very forgiving, but flubs one case:
# if no padding is required (no trailing '='), it continues to read
# following lines as if they were still part of the base64 part.  We're
# actually stricter here.  The *point* is that some mailers tack plain
# text on to the end of base64-encoded text sections.

# Match a line of base64, up to & including the trailing newline.
# We allow for optional leading and trailing whitespace, and don't care
# about line length, but other than that are strict.  Group 1 is non-empty
# after a match iff the last significant char on the line is '='; in that
# case, it must be the last line of the base64 section.
base64_re = re.compile(r"""
    [ \t]*
    [a-zA-Z0-9+/]*
    (=*)
    [ \t]*
    \r?
    \n
""", re.VERBOSE)

def try_to_repair_damaged_base64(text):
    i = 0
    while True:
        # text[:i] looks like base64.  Does the line starting at i also?
        m = base64_re.match(text, i)
        if not m:
            break
        i = m.end()
        if m.group(1):
            # This line has a trailing '=' -- the base64 part is done.
            break
    base64text = ''
    if i:
        base64 = text[:i]
        try:
            base64text = binascii.a2b_base64(base64)
        except:
            # There's no point in tokenizing raw base64 gibberish.
            pass
    return base64text + text[i:]

def breakdown_host(host):
    parts = host.split('.')
    for i in range(1, len(parts) + 1):
        yield '.'.join(parts[-i:])

def breakdown_ipaddr(ipaddr):
    parts = ipaddr.split('.')
    for i in range(1, 5):
        yield '.'.join(parts[:i])

def log2(n, log=math.log, c=math.log(2)):
    return log(n)/c


class Stripper(object):

    # The retained portions are catenated together with self.separator.
    # CAUTION:  This used to be blank.  But then I noticed spam putting
    # HTML comments embedded in words, like
    #     FR<!--slkdflskjf-->EE!
    # Breaking this into "FR" and "EE!" wasn't a real help <wink>.
    separator = ''  # a subclass can override if this isn't appropriate

    def __init__(self, find_start, find_end):
        # find_start and find_end have signature
        #     string, int -> match_object
        # where the search starts at string[int:int].  If a match isn't found,
        # they must return None.  The match_object for find_start, if not
        # None, is passed to self.tokenize, which returns a (possibly empty)
        # list of tokens to generate.  Subclasses may override tokenize().
        # Text between find_start and find_end is thrown away, except for
        # whatever tokenize() produces.  A match_object must support method
        #     span() -> int, int    # the slice bounds of what was matched
        self.find_start = find_start
        self.find_end = find_end

    # Efficiency note:  This is cheaper than it looks if there aren't any
    # special sections.  Under the covers, string[0:] is optimized to
    # return string (no new object is built), and likewise ' '.join([string])
    # is optimized to return string.  It would actually slow this code down
    # to special-case these "do nothing" special cases at the Python level!

    def analyze(self, text):
        i = 0
        retained = []
        pushretained = retained.append
        tokens = []
        while True:
            m = self.find_start(text, i)
            if not m:
                pushretained(text[i:])
                break
            start, end = m.span()
            pushretained(text[i : start])
            tokens.extend(self.tokenize(m))
            m = self.find_end(text, end)
            if not m:
                # No matching end - act as if the open
                # tag did not exist.
                pushretained(text[start:])
                break
            dummy, i = m.span()
        return self.separator.join(retained), tokens

    def tokenize(self, match_object):
        # Override this if you want to suck info out of the start pattern.
        return []

# Strip out uuencoded sections and produce tokens.  The return value
# is (new_text, sequence_of_tokens), where new_text no longer contains
# uuencoded stuff.  Note that we're not bothering to decode it!  Maybe
# we should.  One of my persistent false negatives is a spam containing
# nothing but a uuencoded money.txt; OTOH, uuencode seems to be on
# its way out (that's an old spam).

uuencode_begin_re = re.compile(r"""
    ^begin \s+
    (\S+) \s+   # capture mode
    (\S+) \s*   # capture filename
    $
""", re.VERBOSE | re.MULTILINE)

uuencode_end_re = re.compile(r"^end\s*\n", re.MULTILINE)

class UUencodeStripper(Stripper):
    def __init__(self):
        Stripper.__init__(self, uuencode_begin_re.search,
                                uuencode_end_re.search)

    def tokenize(self, m):
        mode, fname = m.groups()
        return (['uuencode mode:%s' % mode] +
                ['uuencode:%s' % x for x in crack_filename(fname)])

crack_uuencode = UUencodeStripper().analyze


# Strip and specially tokenize embedded URLish thingies.

url_fancy_re = re.compile(r""" 
    \b                      # the preceeding character must not be alphanumeric
    (?: 
        (?:
            (https? | ftp)  # capture the protocol
            ://             # skip the boilerplate
        )|
        (?= ftp\.[^\.\s<>"'\x7f-\xff] )|  # allow the protocol to be missing, but only if
        (?= www\.[^\.\s<>"'\x7f-\xff] )   # the rest of the url starts "www.x" or "ftp.x" 
    )
    # Do a reasonable attempt at detecting the end.  It may or may not
    # be in HTML, may or may not be in quotes, etc.  If it's full of %
    # escapes, cool -- that's a clue too.
    ([^\s<>"'\x7f-\xff]+)  # capture the guts
""", re.VERBOSE)                        # '

url_re = re.compile(r"""
    (https? | ftp)  # capture the protocol
    ://             # skip the boilerplate
    # Do a reasonable attempt at detecting the end.  It may or may not
    # be in HTML, may or may not be in quotes, etc.  If it's full of %
    # escapes, cool -- that's a clue too.
    ([^\s<>"'\x7f-\xff]+)  # capture the guts
""", re.VERBOSE)                        # '


urlsep_re = re.compile(r"[;?:@&=+,$.]")

class URLStripper(Stripper):
    def __init__(self):
        # The empty regexp matches anything at once.
        if options["Tokenizer", "x-fancy_url_recognition"]:
            search = url_fancy_re.search
        else:
            search = url_re.search
        Stripper.__init__(self, search, re.compile("").search)

    def tokenize(self, m):
        proto, guts = m.groups()
        assert guts
        if proto is None:
            if guts.lower().startswith("www"):
                proto = "http"
            elif guts.lower().startswith("ftp"):
                proto = "ftp"
            else:
                proto = "unknown"
        tokens = ["proto:" + proto]
        pushclue = tokens.append

        if options["Tokenizer", "x-pick_apart_urls"]:
            url = proto + "://" + guts

            escapes = re.findall(r'%..', guts)
            # roughly how many %nn escapes are there?
            if escapes:
                pushclue("url:%%%d" % int(log2(len(escapes))))
            # %nn escapes are usually intentional obfuscation.  Generate a
            # lot of correlated tokens if the URL contains a lot of them.
            # The classifier will learn which specific ones are and aren't
            # spammy.
            tokens.extend(["url:" + escape for escape in escapes])

            # now remove any obfuscation and probe around a bit
            url = urllib.unquote(url)
            scheme, netloc, path, params, query, frag = urlparse.urlparse(url)

            if cache is not None and options["Tokenizer", "x-lookup_ip"]:
                ips=cache.lookup(netloc)
                if len(ips)==0:
                    pushclue("url-ip:timeout")
                else:
                    for ip in ips: # Should we limit to one A record?
                        pushclue("url-ip:%s/32" % ip)
                        dottedQuadList=ip.split(".")
                        pushclue("url-ip:%s/8" % dottedQuadList[0])
                        pushclue("url-ip:%s.%s/16" % (dottedQuadList[0],
                                                      dottedQuadList[1]))
                        pushclue("url-ip:%s.%s.%s/24" % (dottedQuadList[0],
                                                         dottedQuadList[1],
                                                         dottedQuadList[2]))

            # one common technique in bogus "please (re-)authorize yourself"
            # scams is to make it appear as if you're visiting a valid
            # payment-oriented site like PayPal, CitiBank or eBay, when you
            # actually aren't.  The company's web server appears as the
            # beginning of an often long username element in the URL such as
            # http://www.paypal.com%65%43%99%35@10.0.1.1/iwantyourccinfo
            # generally with an innocuous-looking fragment of text or a
            # valid URL as the highlighted link.  Usernames should rarely
            # appear in URLs (perhaps in a local bookmark you established),
            # and never in a URL you receive from an unsolicited email or
            # another website.
            user_pwd, host_port = urllib.splituser(netloc)
            if user_pwd is not None:
                pushclue("url:has user")

            host, port = urllib.splitport(host_port)
            # web servers listening on non-standard ports are suspicious ...
            if port is not None:
                if (scheme == "http" and port != '80' or
                    scheme == "https" and port != '443'):
                    pushclue("url:non-standard %s port" % scheme)

            # ... as are web servers associated with raw ip addresses
            if re.match("(\d+\.?){4,4}$", host) is not None:
                pushclue("url:ip addr")

            # make sure we later tokenize the unobfuscated url bits
            proto, guts = url.split("://", 1)

        # Lose the trailing punctuation for casual embedding, like:
        #     The code is at http://mystuff.org/here?  Didn't resolve.
        # or
        #     I found it at http://mystuff.org/there/.  Thanks!
        while guts and guts[-1] in '.:?!/':
            guts = guts[:-1]
        for piece in guts.split('/'):
            for chunk in urlsep_re.split(piece):
                pushclue("url:" + chunk)
        return tokens

received_complaints_re = re.compile(r'\([a-z]+(?:\s+[a-z]+)+\)')

class SlurpingURLStripper(URLStripper):
    def __init__(self):
        URLStripper.__init__(self)

    def analyze(self, text):
        # If there are no URLS, then we need to clear the
        # wordstream, or whatever was there from the last message
        # will be used.
        classifier.slurp_wordstream = None
        # Continue as normal.
        return URLStripper.analyze(self, text)

    def tokenize(self, m):
        # XXX Note that the 'slurped' tokens are *always* trained
        # XXX on; it would be simple to change/parameterize this.
        tokens = URLStripper.tokenize(self, m)
        if not options["URLRetriever", "x-slurp_urls"]:
            return tokens

        proto, guts = m.groups()
        if proto != "http":
            return tokens

        assert guts
        while guts and guts[-1] in '.:;?!/)':
            guts = guts[:-1]

        classifier.slurp_wordstream = (proto, guts)
        return tokens

if options["URLRetriever", "x-slurp_urls"]:
    crack_urls = SlurpingURLStripper().analyze
else:
    crack_urls = URLStripper().analyze

# Nuke HTML <style gimmicks.
html_style_start_re = re.compile(r"""
    < \s* style\b [^>]* >
""", re.VERBOSE)

class StyleStripper(Stripper):
    def __init__(self):
        Stripper.__init__(self, html_style_start_re.search,
                                re.compile(r"</style>").search)

crack_html_style = StyleStripper().analyze

# Nuke HTML comments.

class CommentStripper(Stripper):
    def __init__(self):
        Stripper.__init__(self,
                          re.compile(r"<!--|<\s*comment\s*[^>]*>").search,
                          re.compile(r"-->|</comment>").search)

crack_html_comment = CommentStripper().analyze

# Nuke stuff between <noframes> </noframes> tags.
class NoframesStripper(Stripper):
    def __init__(self):
        Stripper.__init__(self,
                          re.compile(r"<\s*noframes\s*>").search,
                          re.compile(r"</noframes\s*>").search)

crack_noframes = NoframesStripper().analyze

# Scan HTML for constructs often seen in viruses and worms.
# <script  </script
# <iframe  </iframe
# src=cid:
# height=0  width=0

virus_re = re.compile(r"""
    < /? \s* (?: script | iframe) \b
|   \b src= ['"]? cid:
|   \b (?: height | width) = ['"]? 0
""", re.VERBOSE)                        # '

def find_html_virus_clues(text):
    for bingo in virus_re.findall(text):
        yield bingo



numeric_entity_re = re.compile(r'&#(\d+);')
def numeric_entity_replacer(m):
    try:
        return chr(int(m.group(1)))
    except:
        return '?'


breaking_entity_re = re.compile(r"""
    &nbsp;
|   < (?: p
      |   br
      )
    >
""", re.VERBOSE)

class Tokenizer:

    date_hms_re = re.compile(r' (?P<hour>[0-9][0-9])'
                             r':(?P<minute>[0-9][0-9])'
                             r'(?::[0-9][0-9])? ')

    date_formats = ("%a, %d %b %Y %H:%M:%S (%Z)",
                    "%a, %d %b %Y %H:%M:%S %Z",
                    "%d %b %Y %H:%M:%S (%Z)",
                    "%d %b %Y %H:%M:%S %Z",
                    "%a, %d %b %Y %H:%M (%Z)",
                    "%a, %d %b %Y %H:%M %Z",
                    "%d %b %Y %H:%M (%Z)",
                    "%d %b %Y %H:%M %Z")

    def __init__(self):
        self.setup()

    def setup(self):
        """Get the tokenizer ready to use; this should be called after
        all options have been set."""
        # We put this here, rather than in __init__, so that this can be
        # done after we set options at runtime (since the tokenizer
        # instance is generally created when this module is imported).
        if options["Tokenizer", "basic_header_tokenize"]:
            self.basic_skip = [re.compile(s)
                               for s in options["Tokenizer",
                                                "basic_header_skip"]]

    def get_message(self, obj):
        return get_message(obj)

    def tokenize(self, obj):
        msg = self.get_message(obj)

        for tok in self.tokenize_headers(msg):
            yield tok
        for tok in self.tokenize_body(msg):
            yield tok

    def tokenize_headers(self, msg):
        # Special tagging of header lines and MIME metadata.

        # Content-{Type, Disposition} and their params, and charsets.
        # This is done for all MIME sections.
        for x in msg.walk():
            for w in crack_content_xyz(x):
                yield w

        # The rest is solely tokenization of header lines.
        # XXX The headers in my (Tim's) spam and ham corpora are so different
        # XXX (they came from different sources) that including several kinds
        # XXX of header analysis renders the classifier's job trivial.  So
        # XXX lots of this is crippled now, controlled by an ever-growing
        # XXX collection of funky options.

        # Basic header tokenization
        # Tokenize the contents of each header field in the way Subject lines
        # are tokenized later.
        # XXX Different kinds of tokenization have gotten better results on
        # XXX different header lines.  No experiments have been run on
        # XXX whether the best choice is being made for each of the header
        # XXX lines tokenized by this section.
        # The name of the header is used as a tag.  Tokens look like
        # "header:word".  The basic approach is simple and effective, but
        # also very sensitive to biases in the ham and spam collections.
        # For example, if the ham and spam were collected at different
        # times, several headers with date/time information will become
        # the best discriminators.
        # (Not just Date, but Received and X-From_.)
        if options["Tokenizer", "basic_header_tokenize"]:
            for k, v in msg.items():
                k = k.lower()
                for rx in self.basic_skip:
                    if rx.match(k):
                        break   # do nothing -- we're supposed to skip this
                else:
                    # Never found a match -- don't skip this.
                    for w in subject_word_re.findall(v):
                        for t in tokenize_word(w):
                            yield "%s:%s" % (k, t)
            if options["Tokenizer", "basic_header_tokenize_only"]:
                return

        # Habeas Headers - see http://www.habeas.com
        if options["Tokenizer", "x-search_for_habeas_headers"]:
            habeas_headers = [
("X-Habeas-SWE-1", "winter into spring"),
("X-Habeas-SWE-2", "brightly anticipated"),
("X-Habeas-SWE-3", "like Habeas SWE (tm)"),
("X-Habeas-SWE-4", "Copyright 2002 Habeas (tm)"),
("X-Habeas-SWE-5", "Sender Warranted Email (SWE) (tm). The sender of this"),
("X-Habeas-SWE-6", "email in exchange for a license for this Habeas"),
("X-Habeas-SWE-7", "warrant mark warrants that this is a Habeas Compliant"),
("X-Habeas-SWE-8", "Message (HCM) and not spam. Please report use of this"),
("X-Habeas-SWE-9", "mark in spam to <http://www.habeas.com/report/>.")
            ]
            valid_habeas = 0
            invalid_habeas = False
            for opt, val in habeas_headers:
                habeas = msg.get(opt)
                if habeas is not None:
                    if options["Tokenizer", "x-reduce_habeas_headers"]:
                        if habeas == val:
                            valid_habeas += 1
                        else:
                            invalid_habeas = True
                    else:
                        if habeas == val:
                            yield opt.lower() + ":valid"
                        else:
                            yield opt.lower() + ":invalid"
            if options["Tokenizer", "x-reduce_habeas_headers"]:
                # If there was any invalid line, we record as invalid.
                # If all nine lines were correct, we record as valid.
                # Otherwise we ignore.
                if invalid_habeas == True:
                    yield "x-habeas-swe:invalid"
                elif valid_habeas == 9:
                    yield "x-habeas-swe:valid"

        # Subject:
        # Don't ignore case in Subject lines; e.g., 'free' versus 'FREE' is
        # especially significant in this context.  Experiment showed a small
        # but real benefit to keeping case intact in this specific context.
        x = msg.get('subject', '')
        try:
            subjcharsetlist = email.Header.decode_header(x)
        except (binascii.Error, email.Errors.HeaderParseError):
            subjcharsetlist = [(x, 'invalid')]
        for x, subjcharset in subjcharsetlist:
            if subjcharset is not None:
                yield 'subjectcharset:' + subjcharset
            # this is a workaround for a bug in the csv module in Python
            # <= 2.3.4 and 2.4.0 (fixed in 2.5)
            x = x.replace('\r', ' ')
            for w in subject_word_re.findall(x):
                for t in tokenize_word(w):
                    yield 'subject:' + t
            for w in punctuation_run_re.findall(x):
                yield 'subject:' + w

        # Dang -- I can't use Sender:.  If I do,
        #     'sender:email name:python-list-admin'
        # becomes the most powerful indicator in the whole database.
        #
        # From:         # this helps both rates
        # Reply-To:     # my error rates are too low now to tell about this
        #               # one (smalls wins & losses across runs, overall
        #               # not significant), so leaving it out
        # To:, Cc:      # These can help, if your ham and spam are sourced
        #               # from the same location. If not, they'll be horrible.
        for field in options["Tokenizer", "address_headers"]:
            addrlist = msg.get_all(field, [])
            if not addrlist:
                yield field + ":none"
                continue

            noname_count = 0
            for name, addr in email.Utils.getaddresses(addrlist):
                if name:
                    try:
                        subjcharsetlist = email.Header.decode_header(name)
                    except (binascii.Error, email.Errors.HeaderParseError):
                        subjcharsetlist = [(name, 'invalid')]
                    for name, charset in subjcharsetlist:
                        yield "%s:name:%s" % (field, name.lower())
                        if charset is not None:
                            yield "%s:charset:%s" % (field, charset)
                else:
                    noname_count += 1
                if addr:
                    for w in addr.lower().split('@'):
                        yield "%s:addr:%s" % (field, w)
                else:
                    yield field + ":addr:none"

            if noname_count:
                yield "%s:no real name:2**%d" % (field,
                                                 round(log2(noname_count)))

        # Spammers sometimes send out mail alphabetically to fairly large
        # numbers of addresses.  This results in headers like:
        #   To: <itinerart@videotron.ca>
        #   Cc: <itinerant@skyful.com>, <itinerant@netillusions.net>,
        #       <itineraries@musi-cal.com>, <itinerario@rullet.leidenuniv.nl>,
        #       <itinerance@sorengo.com>
        #
        # This token attempts to exploit that property.  The above would
        # give a common prefix of "itinera" for 6 addresses, yielding a
        # gross score of 42.  We group scores into buckets by dividing by 10
        # to yield a final token value of "pfxlen:04".  The length test
        # eliminates the bad case where the message was sent to a single
        # individual.
        if options["Tokenizer", "summarize_email_prefixes"]:
            all_addrs = []
            addresses = msg.get_all('to', []) + msg.get_all('cc', [])
            for name, addr in email.Utils.getaddresses(addresses):
                all_addrs.append(addr.lower())

            if len(all_addrs) > 1:
                # don't be fooled by "os.path." - commonprefix
                # operates char-by-char!
                pfx = os.path.commonprefix(all_addrs)
                if pfx:
                    score = (len(pfx) * len(all_addrs)) // 10
                    # After staring at pfxlen:* values generated from a large
                    # number of ham & spam I saw that any scores greater
                    # than 3 were always associated with spam.  Collapsing
                    # all such scores into a single token avoids a bunch of
                    # hapaxes like "pfxlen:28".
                    if score > 3:
                        yield "pfxlen:big"
                    else:
                        yield "pfxlen:%d" % score

        # same idea as above, but works for addresses in the same domain
        # like
        #   To: "skip" <bugs@mojam.com>, <chris@mojam.com>,
        #       <concertmaster@mojam.com>, <concerts@mojam.com>,
        #       <design@mojam.com>, <rob@mojam.com>, <skip@mojam.com>
        if options["Tokenizer", "summarize_email_suffixes"]:
            all_addrs = []
            addresses = msg.get_all('to', []) + msg.get_all('cc', [])
            for name, addr in email.Utils.getaddresses(addresses):
                # flip address code so following logic is the same as
                # that for prefixes
                addr = list(addr)
                addr.reverse()
                addr = "".join(addr)
                all_addrs.append(addr.lower())

            if len(all_addrs) > 1:
                # don't be fooled by "os.path." - commonprefix
                # operates char-by-char!
                sfx = os.path.commonprefix(all_addrs)
                if sfx:
                    score = (len(sfx) * len(all_addrs)) // 10
                    # Similar analysis as above regarding suffix length
                    # I suspect the best cutoff is probably dependent on
                    # how long the recipient domain is (e.g. "mojam.com" vs.
                    # "montanaro.dyndns.org")
                    if score > 5:
                        yield "sfxlen:big"
                    else:
                        yield "sfxlen:%d" % score

        # To:
        # Cc:
        # Count the number of addresses in each of the recipient headers.
        for field in ('to', 'cc'):
            count = 0
            for addrs in msg.get_all(field, []):
                count += len(addrs.split(','))
            if count > 0:
                yield '%s:2**%d' % (field, round(log2(count)))

        # These headers seem to work best if they're not tokenized:  just
        # normalize case and whitespace.
        # X-Mailer:  This is a pure and significant win for the f-n rate; f-p
        #            rate isn't affected.
        for field in ('x-mailer',):
            prefix = field + ':'
            x = msg.get(field, 'none').lower()
            yield prefix + ' '.join(x.split())

        # Received:
        # Neil Schemenauer reports good results from this.
        if options["Tokenizer", "mine_received_headers"]:
            for header in msg.get_all("received", ()):
                # everything here should be case insensitive and not be
                # split across continuation lines, so normalize whitespace
                # and letter case just once per header
                header = ' '.join(header.split()).lower()

                for clue in received_complaints_re.findall(header):
                    yield 'received:' + clue

                for pat, breakdown in [(received_host_re, breakdown_host),
                                       (received_ip_re, breakdown_ipaddr)]:
                    m = pat.search(header)
                    if m:
                        for tok in breakdown(m.group(1)):
                            yield 'received:' + tok

        # Message-Id:  This seems to be a small win and should not
        # adversely affect a mixed source corpus so it's always enabled.
        msgid = msg.get("message-id", "")
        m = message_id_re.match(msgid)
        if m:
            # looks okay, return the hostname
            yield 'message-id:@%s' % m.group(1)
        else:
            # might be weird instead of invalid but who cares?
            yield 'message-id:invalid'

        # As suggested by Anthony Baxter, merely counting the number of
        # header lines, and in a case-sensitive way, has real value.
        # For example, all-caps SUBJECT is a strong spam clue, while
        # X-Complaints-To a strong ham clue.
        x2n = {}
        if options["Tokenizer", "count_all_header_lines"]:
            for x in msg.keys():
                x2n[x] = x2n.get(x, 0) + 1
        else:
            # Do a "safe" approximation to that.  When spam and ham are
            # collected from different sources, the count of some header
            # lines can be a too strong a discriminator for accidental
            # reasons.
            safe_headers = options["Tokenizer", "safe_headers"]
            for x in msg.keys():
                if x.lower() in safe_headers:
                    x2n[x] = x2n.get(x, 0) + 1
        for x in x2n.items():
            yield "header:%s:%d" % x
        if options["Tokenizer", "record_header_absence"]:
            for k in x2n:
                if not k.lower() in options["Tokenizer", "safe_headers"]:
                    yield "noheader:" + k

    def tokenize_text(self, text, maxword=options["Tokenizer",
                                                  "skip_max_word_size"]):
        """Tokenize everything in the chunk of text we were handed."""
        short_runs = Set()
        short_count = 0
        for w in text.split():
            n = len(w)
            if n < 3:
                # count how many short words we see in a row - meant to
                # latch onto crap like this:
                # X j A m N j A d X h
                # M k E z R d I p D u I m A c
                # C o I d A t L j I v S j
                short_count += 1
            else:
                if short_count:
                    short_runs.add(short_count)
                    short_count = 0
                # Make sure this range matches in tokenize_word().
                if 3 <= n <= maxword:
                    yield w

                elif n >= 3:
                    for t in tokenize_word(w):
                        yield t
        if short_runs and options["Tokenizer", "x-short_runs"]:
            yield "short:%d" % int(log2(max(short_runs)))

    def tokenize_body(self, msg):
        """Generate a stream of tokens from an email Message.

        If options['Tokenizer', 'check_octets'] is True, the first few
        undecoded characters of application/octet-stream parts of the
        message body become tokens.
        """

        if options["Tokenizer", "check_octets"]:
            # Find, decode application/octet-stream parts of the body,
            # tokenizing the first few characters of each chunk.
            for part in octetparts(msg):
                try:
                    text = part.get_payload(decode=True)
                except:
                    yield "control: couldn't decode octet"
                    text = part.get_payload(decode=False)

                if text is None:
                    yield "control: octet payload is None"
                    continue

                yield "octet:%s" % text[:options["Tokenizer",
                                                 "octet_prefix_size"]]

        parts = imageparts(msg)
        if options["Tokenizer", "x-image_size"]:
            # Find image/* parts of the body, calculating the log(size) of
            # each image.
            
            total_len = 0
            for part in parts:
                try:
                    text = part.get_payload(decode=True)
                except:
                    yield "control: couldn't decode image"
                    text = part.get_payload(decode=False)

                total_len += len(text or "")
                if text is None:
                    yield "control: image payload is None"

            if total_len:
                yield "image-size:2**%d" % round(log2(total_len))

        if options["Tokenizer", "x-crack_images"]:
            from spambayes.ImageStripper import ImageStripper
            text, tokens = ImageStripper().analyze(parts)
            for t in tokens:
                yield t
            for t in self.tokenize_text(text):
                yield t

        # Find, decode (base64, qp), and tokenize textual parts of the body.
        for part in textparts(msg):
            # Decode, or take it as-is if decoding fails.
            try:
                text = part.get_payload(decode=True)
            except:
                yield "control: couldn't decode"
                text = part.get_payload(decode=False)
                if text is not None:
                    text = try_to_repair_damaged_base64(text)

            if text is None:
                yield 'control: payload is None'
                continue

            # Replace numeric character entities (like &#97; for the letter
            # 'a').
            text = numeric_entity_re.sub(numeric_entity_replacer, text)

            # Normalize case.
            text = text.lower()

            if options["Tokenizer", "replace_nonascii_chars"]:
                # Replace high-bit chars and control chars with '?'.
                text = text.translate(non_ascii_translate_tab)

            for t in find_html_virus_clues(text):
                yield "virus:%s" % t

            # Get rid of uuencoded sections, embedded URLs, <style gimmicks,
            # and HTML comments.
            for cracker in (crack_uuencode,
                            crack_urls,
                            crack_html_style,
                            crack_html_comment,
                            crack_noframes):
                text, tokens = cracker(text)
                for t in tokens:
                    yield t

            # Remove HTML/XML tags.  Also &nbsp;.  <br> and <p> tags should
            # create a space too.
            text = breaking_entity_re.sub(' ', text)
            # It's important to eliminate HTML tags rather than, e.g.,
            # replace them with a blank (as this code used to do), else
            # simple tricks like
            #    Wr<!$FS|i|R3$s80sA >inkle Reduc<!$FS|i|R3$s80sA >tion
            # can be used to disguise words.  <br> and <p> were special-
            # cased just above (because browsers break text on those,
            # they can't be used to hide words effectively).
            text = html_re.sub('', text)

            for t in self.tokenize_text(text):
                yield t

global_tokenizer = Tokenizer()
tokenize = global_tokenizer.tokenize
