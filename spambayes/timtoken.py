import re

import email

from sets import Set

__all__ = ['tokenize']


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
            stack = part.get_payload()
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
# XXX So, if another way is found to slash the f-n rate, the decision here
# XXX not to strip HTML from HTML-only msgs should be revisited.

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

# I'm usually just splitting on whitespace, but for subject lines I want to
# break things like "Python/Perl comparison?" up.  OTOH, I don't want to
# break up the unitized numbers in spammish subject phrases like "Increase
# size 79%" or "Now only $29.95!".  Then again, I do want to break up
# "Python-Dev".
subject_word_re = re.compile(r"[\w\x80-\xff$.%]+")

def tokenize_word(word, _len=len):
    n = _len(word)

    # Make sure this range matches in tokenize().
    if 3 <= n <= 12:
        yield word

    elif n >= 3:
        # A long word.

        # Don't want to skip embedded email addresses.
        if n < 40 and '.' in word and word.count('@') == 1:
            p1, p2 = word.split('@')
            yield 'email name:' + p1
            for piece in p2.split('.'):
                yield 'email addr:' + piece

        # If there are any high-bit chars,
        # tokenize it as byte 5-grams.
        # XXX This really won't work for high-bit languages -- the scoring
        # XXX scheme throws almost everything away, and one bad phrase can
        # XXX generate enough bad 5-grams to dominate the final score.
        # XXX This also increases the database size substantially.
        elif has_highbit_char(word):
            for i in xrange(n-4):
                yield "5g:" + word[i : i+5]

        else:
            # It's a long string of "normal" chars.  Ignore it.
            # For example, it may be an embedded URL (which we already
            # tagged), or a uuencoded line.
            # There's value in generating a token indicating roughly how
            # many chars were skipped.  This has real benefit for the f-n
            # rate, but is neutral for the f-p rate.  I don't know why!
            # XXX Figure out why, and/or see if some other way of summarizing
            # XXX this info has greater benefit.
            yield "skip:%c %d" % (word[0], n // 10 * 10)

# Generate tokens for:
#    Content-Type
#        and its type= param
#    Content-Dispostion
#        and its filename= param
#    all the charsets
#
# This has huge benefit for the f-n rate, and virtually none on the f-p rate,
# although it does reduce the variance of the f-p rate across different
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
        for x in fname.lower().split('/'):
            for y in x.split('.'):
                yield 'filename:' + y

    if 0:   # disabled; see comment before function
        x = msg.get('content-transfer-encoding')
        if x is not None:
            yield 'content-transfer-encoding:' + x.lower()

def tokenize(obj):
    # Create an email Message object.
    if isinstance(obj, email.Message.Message):
        msg = obj
    elif hasattr(obj, "readline"):
        try:
            msg = email.message_from_file(obj)
        except email.Errors.MessageParseError:
            yield 'control: MessageParseError'
            # XXX Fall back to the raw body text?
            return
    else:
        try:
            msg = email.message_from_string(obj)
        except email.Errors.MessageParseError:
            yield 'control: MessageParseError'
            # XXX Fall back to the raw body text?
            return

    # Special tagging of header lines.
    # XXX TODO Neil Schemenauer has gotten a good start on this (pvt email).
    # XXX The headers in my spam and ham corpora are so different (they came
    # XXX from different sources) that if I include them the classifier's
    # XXX job is trivial.  Only some "safe" header lines are included here,
    # XXX where "safe" is specific to my sorry <wink> corpora.

    # Content-{Type, Disposition} and their params, and charsets.
    t = ''
    for x in msg.walk():
        for w in crack_content_xyz(x):
            yield t + w
        t = '>'

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
    # User-Agent:  Skipping it, as it made no difference.  Very few spams
    #              had a User-Agent field, but lots of hams didn't either,
    #              and the spam probability of User-Agent was very close to
    #              0.5 (== not a valuable discriminator) across all training
    #              sets.
    for field in ('x-mailer',):
        prefix = field + ':'
        x = msg.get(field, 'none').lower()
        yield prefix + ' '.join(x.split())

    # Organization:
    # Oddly enough, tokenizing this doesn't make any difference to results.
    # However, noting its mere absence is strong enough to give a tiny
    # improvement in the f-n rate, and since recording that requires only
    # one token across the whole database, the cost is also tiny.
    if msg.get('organization', None) is None:
        yield "bool:noorg"

    # XXX Following is a great idea due to Anthony Baxter.  I can't use it
    # XXX on my test data because the header lines are so different between
    # XXX my ham and spam that it makes a large improvement for bogus
    # XXX reasons.  So it's commented out.  But it's clearly a good thing
    # XXX to do on "normal" data, and subsumes the Organization trick above
    # XXX in a much more general way, yet at comparable cost.
    ### X-UIDL:
    ### Anthony Baxter's idea.  This has spamprob 0.99!  The value is clearly
    ### irrelevant, just the presence or absence matters.  However, it's
    ### extremely rare in my spam sets, so doesn't have much value.
    ###
    ### As also suggested by Anthony, we can capture all such header oddities
    ### just by generating tags for the count of how many times each header
    ### field appears.
    ##x2n = {}
    ##for x in msg.keys():
    ##    x2n[x] = x2n.get(x, 0) + 1
    ##for x in x2n.items():
    ##    yield "header:%s:%d" % x

    # Find, decode (base64, qp), and tokenize the textual parts of the body.
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

        # Special tagging of embedded URLs.
        for proto, guts in url_re.findall(text):
            yield "proto:" + proto
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
                    yield prefix + chunk

        # Remove HTML/XML tags if it's a plain text message.
        if part.get_content_type() == "text/plain":
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
