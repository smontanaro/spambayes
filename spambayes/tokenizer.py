"""Module to tokenize email messages for spam filtering."""

import email
import re
from sets import Set

from Options import options

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



# Find all the text components of the msg.  There's no point decoding
# binary blobs (like images).  If a multipart/alternative has both plain
# text and HTML versions of a msg, ignore the HTML part:  HTML decorations
# have monster-high spam probabilities, and innocent newbies often post
# using HTML.
def textparts(msg):
    text = Set()
    redundant_html = Set()
    for part in msg.walk():
        if part.get_content_type() == 'multipart/alternative':
            # Descend this part of the tree, adding any redundant HTML text
            # part to redundant_html.
            htmlpart = textpart = None
            stack = part.get_payload()[:]
            while stack:
                subpart = stack.pop()
                ctype = subpart.get_content_type()
                if ctype == 'text/plain':
                    textpart = subpart
                elif ctype == 'text/html':
                    htmlpart = subpart
                elif ctype == 'multipart/related':
                    stack.extend(subpart.get_payload())

            if textpart is not None:
                text.add(textpart)
                if htmlpart is not None:
                    redundant_html.add(htmlpart)
            elif htmlpart is not None:
                text.add(htmlpart)

        elif part.get_content_maintype() == 'text':
            text.add(part)

    return text - redundant_html

url_re = re.compile(r"""
    (https? | ftp)  # capture the protocol
    ://             # skip the boilerplate
    # Do a reasonable attempt at detecting the end.  It may or may not
    # be in HTML, may or may not be in quotes, etc.  If it's full of %
    # escapes, cool -- that's a clue too.
    ([^\s<>'"\x7f-\xff]+)  # capture the guts
""", re.VERBOSE)

urlsep_re = re.compile(r"[;?:@&=+,$.]")

has_highbit_char = re.compile(r"[\x80-\xff]").search

# Cheap-ass gimmick to probabilistically find HTML/XML tags.
html_re = re.compile(r"""
    <
    [^\s<>]     # e.g., don't match 'a < b' or '<<<' or 'i << 5' or 'a<>b'
    [^>]{0,128} # search for the end '>', but don't run wild
    >
""", re.VERBOSE)

received_host_re = re.compile(r'from (\S+)\s')
received_ip_re = re.compile(r'\s[[(]((\d{1,3}\.?){4})[\])]')

# I'm usually just splitting on whitespace, but for subject lines I want to
# break things like "Python/Perl comparison?" up.  OTOH, I don't want to
# break up the unitized numbers in spammish subject phrases like "Increase
# size 79%" or "Now only $29.95!".  Then again, I do want to break up
# "Python-Dev".
subject_word_re = re.compile(r"[\w\x80-\xff$.%]+")

# Anthony Baxter reported goodness from cracking src params.
# Finding a src= thingie is complicated if we insist it appear in an
# img or iframe tag, so this approximates reality with a fast and
# non-stack-blowing simple regexp.
src_re = re.compile(r"""
    \s
    src=['"]
    (?!https?:)     # we suck out http thingies via a different gimmick
    ([^'"]{1,128})  # capture the guts, but don't go wild
    ['"]
""", re.VERBOSE)

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

def tokenize_word(word, _len=len):
    n = _len(word)
    # Make sure this range matches in tokenize().
    if 3 <= n <= 12:
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

def crack_content_xyz(msg):
    x = msg.get_type()
    if x is not None:
        yield 'content-type:' + x.lower()

    x = msg.get_param('type')
    if x is not None:
        yield 'content-type/type:' + x.lower()

    for x in msg.get_charsets(None):
        if x is not None:
            yield 'charset:' + x.lower()

    x = msg.get('content-disposition')
    if x is not None:
        yield 'content-disposition:' + x.lower()

    fname = msg.get_filename()
    if fname is not None:
        for x in crack_filename(fname):
            yield 'filename:' + x

    if 0:   # disabled; see comment before function
        x = msg.get('content-transfer-encoding')
        if x is not None:
            yield 'content-transfer-encoding:' + x.lower()

def breakdown_host(host):
    parts = host.split('.')
    for i in range(1, len(parts) + 1):
        yield '.'.join(parts[-i:])

def breakdown_ipaddr(ipaddr):
    parts = ipaddr.split('.')
    for i in range(1, 5):
        yield '.'.join(parts[:i])

uuencode_begin_re = re.compile(r"""
    ^begin \s+
    (\S+) \s+   # capture mode
    (\S+) \s*   # capture filename
    $
""", re.VERBOSE | re.MULTILINE)

uuencode_end_re = re.compile(r"^end\s*\n", re.MULTILINE)

# Strip out uuencoded sections and produce tokens.  The return value
# is (new_text, sequence_of_tokens), where new_text no longer contains
# uuencoded stuff.  Note that we're not bothering to decode it!  Maybe
# we should.
def crack_uuencode(text):
    new_text = []
    tokens = []
    i = 0
    while True:
        # Invariant:  Through text[:i], all non-uuencoded text is in
        # new_text, and tokens contains summary clues for all uuencoded
        # portions.  text[i:] hasn't been looked at yet.
        m = uuencode_begin_re.search(text, i)
        if not m:
            new_text.append(text[i:])
            break
        start, end = m.span()
        new_text.append(text[i : start])
        mode, fname = m.groups()
        tokens.append('uuencode mode:%s' % mode)
        tokens.extend(['uuencode:%s' % x for x in crack_filename(fname)])
        m = uuencode_end_re.search(text, end)
        if not m:
            break
        i = m.end()

    return ''.join(new_text), tokens

def crack_urls(text):
    new_text = []
    clues = []
    pushclue = clues.append
    i = 0
    while True:
        # Invariant:  Through text[:i], all non-URL text is in new_text, and
        # clues contains clues for all URLs.  text[i:] hasn't been looked at
        # yet.
        m = url_re.search(text, i)
        if not m:
            new_text.append(text[i:])
            break
        proto, guts = m.groups()
        start, end = m.span()
        new_text.append(text[i : start])
        new_text.append(' ')

        pushclue("proto:" + proto)
        # Lose the trailing punctuation for casual embedding, like:
        #     The code is at http://mystuff.org/here?  Didn't resolve.
        # or
        #     I found it at http://mystuff.org/there/.  Thanks!
        assert guts
        while guts and guts[-1] in '.:?!/':
            guts = guts[:-1]
        for i, piece in enumerate(guts.split('/')):
            prefix = "%s%s:" % (proto, i < 2 and str(i) or '>1')
            for chunk in urlsep_re.split(piece):
                pushclue(prefix + chunk)

        i = end

    return ''.join(new_text), clues

class Tokenizer:

    def get_message(self, obj):
        if isinstance(obj, email.Message.Message):
            return obj
        else:
            # Create an email Message object.
            try:
                if hasattr(obj, "readline"):
                    return email.message_from_file(obj)
                else:
                    return email.message_from_string(obj)
            except email.Errors.MessageParseError:
                return None

    def tokenize(self, obj):
        msg = self.get_message(obj)
        if msg is None:
            yield 'control: MessageParseError'
            # XXX Fall back to the raw body text?
            return

        for tok in self.tokenize_headers(msg):
            yield tok
        for tok in self.tokenize_body(msg):
            yield tok

    def tokenize_headers(self, msg):
        # Special tagging of header lines.

        # XXX TODO Neil Schemenauer has gotten a good start on this
        # XXX (pvt email).  The headers in my spam and ham corpora are
        # XXX so different (they came from different sources) that if
        # XXX I include them the classifier's job is trivial.  Only
        # XXX some "safe" header lines are included here, where "safe"
        # XXX is specific to my sorry <wink> corpora.
        # XXX Jeremy Hylton also reported good results from the general
        # XXX header-mining in mboxtest.MyTokenizer.tokenize_headers.

        # Content-{Type, Disposition} and their params, and charsets.
        for x in msg.walk():
            for w in crack_content_xyz(x):
                yield w

        # Subject:
        # Don't ignore case in Subject lines; e.g., 'free' versus 'FREE' is
        # especially significant in this context.  Experiment showed a small
        # but real benefit to keeping case intact in this specific context.
        x = msg.get('subject', '')
        for w in subject_word_re.findall(x):
            for t in tokenize_word(w):
                yield 'subject:' + t

        # Dang -- I can't use Sender:.  If I do,
        #     'sender:email name:python-list-admin'
        # becomes the most powerful indicator in the whole database.
        #
        # From:
        # Reply-To:
        for field in ('from',):# 'reply-to',):
            prefix = field + ':'
            x = msg.get(field, 'none').lower()
            for w in x.split():
                for t in tokenize_word(w):
                    yield prefix + t

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
        if options.mine_received_headers:
            for header in msg.get_all("received", ()):
                for pat, breakdown in [(received_host_re, breakdown_host),
                                       (received_ip_re, breakdown_ipaddr)]:
                    m = pat.search(header)
                    if m:
                        for tok in breakdown(m.group(1).lower()):
                            yield 'received:' + tok

        # As suggested by Anthony Baxter, merely counting the number of
        # header lines, and in a case-sensitive way, has real value.
        # For example, all-caps SUBJECT is a strong spam clue, while
        # X-Complaints-To a strong ham clue.
        x2n = {}
        if options.count_all_header_lines:
            for x in msg.keys():
                x2n[x] = x2n.get(x, 0) + 1
        else:
            # Do a "safe" approximation to that.  When spam and ham are
            # collected from different sources, the count of some header
            # lines can be a too strong a discriminator for accidental
            # reasons.
            safe_headers = options.safe_headers
            for x in msg.keys():
                if x.lower() in safe_headers:
                    x2n[x] = x2n.get(x, 0) + 1
        for x in x2n.items():
            yield "header:%s:%d" % x

    def tokenize_body(self, msg):
        """Generate a stream of tokens from an email Message.

        If a multipart/alternative section has both text/plain and text/html
        sections, the text/html section is ignored.  This may not be a good
        idea (e.g., the sections may have different content).

        HTML tags are always stripped from text/plain sections.

        options.retain_pure_html_tags controls whether HTML tags are
        also stripped from text/html sections.
        """

        # Find, decode (base64, qp), and tokenize textual parts of the body.
        for part in textparts(msg):
            # Decode, or take it as-is if decoding fails.
            try:
                text = part.get_payload(decode=True)
            except:
                yield "control: couldn't decode"
                text = part.get_payload(decode=False)

            if text is None:
                yield 'control: payload is None'
                continue

            # Normalize case.
            text = text.lower()

            # Get rid of uuencoded sections.
            text, tokens = crack_uuencode(text)
            for t in tokens:
                yield t

            # Special tagging of embedded URLs.
            text, tokens = crack_urls(text)
            for t in tokens:
                yield t

            # Anthony Baxter reported goodness from tokenizing src= params.
            # XXX This made no difference in my tests:  both error rates
            # XXX across 20 runs were identical before and after.  I suspect
            # XXX this is because Anthony got most good out of the http
            # XXX thingies in <img src="http://bozo.bozo.com">, but we
            # XXX picked those up in the last step (in src params and
            # XXX everywhere else).  So this code is commented out.
            ## for fname in src_re.findall(text):
            ##     for x in crack_filename(fname):
            ##         yield "src:" + x

            # Remove HTML/XML tags.
            if (part.get_content_type() == "text/plain" or
                    not options.retain_pure_html_tags):
                text = html_re.sub(' ', text)

            # Tokenize everything in the body.
            for w in text.split():
                n = len(w)
                # Make sure this range matches in tokenize_word().
                if 3 <= n <= 12:
                    yield w

                elif n >= 3:
                    for t in tokenize_word(w):
                        yield t

tokenize = Tokenizer().tokenize
