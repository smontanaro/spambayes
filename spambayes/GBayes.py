#!/usr/bin/env python

# A driver for the classifier module.  Barry Warsaw is the primary author.

"""Usage: %(program)s [options]

Where:
    -h
        show usage and exit
    -g mboxfile
        mbox of known good messages (non-spam)
    -s mboxfile
        mbox of known spam messages
    -u mboxfile
        mbox of unknown messages
    -p file
        use file as the persistent pickle.  loads data from this file if it
        exists, and saves data to this file at the end.  omit for one shot.
    -c num
        train the system with just `num' number of messages from both the
        known spam and known good files.  the system works best with
        approximately the same number of messages from both collections.
    -m threshold
        mark messages with a threshold above float `threshold' with a header
        such as "X-Bayes-Score: score".  use the -o option to output the
        marked folder.
    -o file
        with -m, output all messages, with marks, to file
    -t func
        tokenize using function 'func'.  for a list of functions, run w/ -H.
    -H
        describe all available tokenizing functions, then exit
When called without any options or arguments, a short self-test is run.
"""

import sys
import getopt
import cPickle as pickle
import mailbox
import email
import errno

from classifier import GrahamBayes

program = sys.argv[0]

# For the heck of it, a simple tokenizer to create word streams.
import re
_token_re = re.compile(r"[\w$\-]+")
del re

def tokenize_words_foldcase(string):
    r"""tokenize w/ re '[\w$\-]+', fold case"""
    return _token_re.findall(string.lower())

def tokenize_words(string):
    r"""tokenize w/ re '[\w$\-]+'"""
    return _token_re.findall(string)

def tokenize_split_foldcase(string):
    r"""tokenize using simple string split(), fold case"""
    return string.lower().split()

def tokenize_split(string):
    r"""tokenize using simple string split()"""
    return string.split()

def tokenize_wordpairs_foldcase(string):
    r"""tokenize w/ re '[\w$\-]+' -> 'w1 w2', 'w3 w4', ..., fold case"""
    lst = _token_re.findall(string.lower())
    for i in range(0, len(lst), 2):
        yield " ".join(lst[i:i+2])

def tokenize_words_and_pairs(string):
    r"""tokenize w/ re '[\w$\-]+' -> w1, w2, 'w1 w2', w3, w4, 'w3 w4' ..."""
    lst = _token_re.findall(string.lower())
    lst.append("")
    for i in range(0, len(lst)-1, 2):
        a = lst[i]
        b = lst[i+1]
        yield a
        if b:
            yield b
            yield "%s %s" % (a, b)

# Do an N-gram generator instead.  Fold case and collapse runs of whitespace.
# Probably a good idea to fold punctuation characters into one (or just a
# few) representatives too.
def tokenize_5gram_foldcase_wscollapse(string, N=5):
    r"""tokenize w/ 5-char runs, fold case, normalize whitespace"""
    normalized = " ".join(string.lower().split())
    return tokenize_ngram(normalized, N)

def tokenize_ngram(string, N):
    for i in xrange(len(string)-N+1):
        yield string[i : i+N]

def tokenize_5gram(string):
    r"""tokenize w/ strict 5-char runs"""
    return tokenize_ngram(string, 5)

def tokenize_10gram(string):
    r"""tokenize w/ strict 10-char runs"""
    return tokenize_ngram(string, 10)

def tokenize_15gram(string):
    r"""tokenize w/ strict 15-char runs"""
    return tokenize_ngram(string, 15)

# add user-visible string as key and function as value - function's docstring
# serves as help string when -H is used, so keep it brief!
tokenizers = {
    "5gram": tokenize_5gram,
    "5gram_fold_normws": tokenize_5gram_foldcase_wscollapse,
    "10gram": tokenize_10gram,
    "15gram": tokenize_15gram,
    "word_and_pairs": tokenize_words_and_pairs,
    "wordpairs_fold": tokenize_wordpairs_foldcase,
    "split": tokenize_split,
    "split_fold": tokenize_split_foldcase,
    "words": tokenize_words,
    "words_fold": tokenize_words_foldcase,
    }

spam1 = """
Hello tim_chandler , Want to save money ?
Now is a good time to consider refinancing. Rates are low so you can cut
your current payments and save money.


http://64.251.22.101/interest/index%38%30%300%2E%68t%6D


Take off list on site [s5]
"""

spam2 = """
<BODY vLink=#ff0000 link=#ff0000 bgColor=#ffffff>
<CENTER>
<table border="0" cellspacing="0" cellpadding="0" width="602">
<tr>
  <td bgcolor="#000000">
        <table border="0" cellspacing="4" cellpadding="0" width="100%">
        <tr>
          <td bgcolor="#ffffff" height="110">
                <P align=center><A href="http://61.172.246.53">
                    <FONT color=#000000 size=7>HGH Spray</FONT></A><BR>Human
                    Growth Hormone
                Releaser</P>
          </td>
        </tr>
        <tr>
          <td bgcolor="#ffcc00">
                <BLOCKQUOTE>
                <P align=center><FONT face="Arial, Helvetica, sans-serif" color=#003300
                size=3><STRONG><BR>As seen on NBC, CBS, CNN, and even Oprah! The health
                discovery that actually reverses aging while burning fat, without
                dieting or exercise! This&nbsp;proven discovery has even been reported
                on by the New England&nbsp;Journal of Medicine. Forget aging and dieting
                forever!&nbsp;<BR>And it's Guaranteed! &nbsp;<BR><BR></STRONG></FONT><A
                href="http://61.172.246.53/">
                <FONT face="Arial, Helvetica, sans-serif" color=#000000 size=3>Click
                Here</FONT></A></P></BLOCKQUOTE>

                <HR width="85%">
                <P align=center><B><FONT face="Arial, Helvetica, sans-serif" size=3>Would
                you like to lose weight while you sleep!<BR>No dieting!<BR>No hunger
                pains!<BR>No Cravings!<BR>No strenuous exercise!<BR>Change your life
                forever!</FONT> </B></P>
                <br>

                <TABLE cellSpacing=0 cellPadding=3 border=0 align="center">
                <TR>
                  <TD width=157><FONT face=Verdana size=2><B>1.Body Fat Loss</B></FONT></TD>
                  <TD align=right width=148><FONT face=Verdana size=2><B>82% improvement.</B></FONT></TD>
                </TR>

                <TR>
                  <TD width=157><FONT face=Verdana size=2><B>2.Wrinkle Reduction</B></FONT></TD>
                  <TD align=right width=148><FONT face=Verdana size=2><B>61% improvement.</B></FONT></TD>
                </TR>

                <TR>
                  <TD width=157><FONT face=Verdana size=2><B>3.Energy Level</B></FONT></TD>
                  <TD align=right width=148><FONT face=Verdana size=2><B>84% improvement.</B></FONT></TD>
                </TR>

                <TR>
                  <TD width=157><FONT face=Verdana size=2><B>4.Muscle Strength</B></FONT></TD>
                  <TD align=right width=148><FONT face=Verdana size=2><B>88% improvement.</B></FONT></TD>
                </TR>

                <TR>
                  <TD width=157><FONT face=Verdana size=2><B>5.Virility</B></FONT></TD>
                  <TD align=right width=148><FONT face=Verdana size=2><B>75% improvement.</B></FONT></TD>
                </TR>

                <TR>
                  <TD width=157><FONT face=Verdana size=2><B>6.Emotional Stability</B></FONT></TD>
                  <TD align=right width=148><FONT face=Verdana size=2><B>67% improvement.</B></FONT></TD>
                </TR>

                <TR>
                  <TD width=157><FONT face=Verdana size=2><B>7.Memory</B></FONT></TD>
                  <TD align=right width=148><FONT face=Verdana size=2><B>62% improvement.</B></FONT></TD>
                </TR>

                </TABLE>

                <br><br>
                <P align=center><B><FONT face="Arial, Helvetica, sans-serif" size=6>100%
                GUARANTEED! </FONT></B></P>
                <P align=center><A href="http://61.172.246.53">
                <FONT face="Arial, Helvetica, sans-serif" color=#000000 size=3>Click
        Here</FONT></A></P><br>
                  </td>
        </tr>
        </table>
  </td>
</tr>
</table>
</CENTER>
<STRONG><FONT face="Arial, Helvetica, sans-serif" color=tan size=1>We are
strongly against sending unsolicited emails to those who do not wish
to receive our special mailings. You have opted in to one or more of our
affiliate sites requesting to be notified of any special offers we may run
from time to time. We also have attained the services of an independent 3rd
party to overlook list management and removal services. This is NOT
unsolicited email. If you do not wish to receive further mailings, please
click this link. <br><a href="http://61.172.246.53/remove_page.html">Please
accept our apologies</a> if you have been sent this email in error. We honor
all removal requests.
</FONT></STRONG> <BR><BR><BR>
<BR>
</FONT>
</BODY>
</HTML>
"""

spam3 = """
<html><body><img
src="http://www.coolidgehosting.org/image.folder/life3/RylxYGt3IElnkqt2Fni3r69tigMVw.gif">
<div align="center"> <center> <table border="0" cellpadding="0" cellspacing="0"
style="border-collapse: collapse" bordercolor="#111111" width="671"
id="AutoNumber1"> <tr>  <td width="100%">
<img border="0" src="http://www.coolidgehosting.org/images/top.jpg"
width="671" height="51"></td> </tr> <tr>  <td width="100%">
<table border="0" cellpadding="0" cellspacing="0"
style="border-collapse: collapse" bordercolor="#111111" width="100%"
id="AutoNumber2">   <tr>    <td width="150">    <img border="0"
src="http://www.coolidgehosting.org/images/left.jpg" width="150" height="200">
</td>    <td valign="top"><b>Tim_one, Need Affordable Life Insurance?</b>
<ul>     <li>Save <u>up to 75%</u> on your policy!</li>
<li>Choose from the top insurance companies!</li>
<li>Instant Online Quote!</li>    </ul>    <p align="left">And best of all...
there's <b>absolutely no obligation!</b></p>    <p align="left"><b>
<a href="http://rd.yahoo.com/dir/?http://www.coolidgehosting.org/life3/?random=2xwYGit3aI2Ecnq9tFnw326AtygkMyc">
Click     here</a></b> to see how relatively inexpensive it can be to<br>
secure your     family's future and achieve a comfortable piece of mind.</td>
</tr>  </table>  </td> </tr></table> </center></div><p>&nbsp;</p></body></html>
"""

good1 = """
Jean Jordaan wrote:
> 'Fraid so ;>  It contains a vintage dtml-calendar tag.
>   http://www.zope.org/Members/teyc/CalendarTag
>
> Hmm I think I see what you mean: one needn't manually pass on the
> namespace to a ZPT?

Yeah, Page Templates are a bit more clever, sadly, DTML methods aren't :-(

Chris
"""

good2 = """
> alert the user.  It works minimized, but I don't know how to make
> it work even when the window itself is closed.

I'm sorry but I don't know the answer to that. And, alas, to judge
from the lack of replies better than this one, it appears that no one
else here knows either. There's probably something in Mark Hammond's
win32all extensions:

http://starship.python.net/crew/mhammond/win32/Downloads.html

(which you may already have) to do it, but I'm not enough of a
Windows guy to be able to suggest what.

The best I can suggest is that you post to comp.lang.python or
(equivalently) to the main Python list. There's more information
about them at:

http://www.python.org/psa/MailingLists.html

Regards,
Matt
"""

good3 = """
>>>>> "JH" == Jeremy Hylton <jeremy@zope.com> writes:

>>>>> "FG" == Florent Guillaume <fg@nuxeo.com> writes:

    FG> If you're reading a bunch of log messages to see what the
    FG> activity was on a piece of code, with the intent of trying to
    FG> see what exactly was impacted, it's not practical to
    FG> constantly refer to an external source of information (go to
    FG> the collector) or go back and forth between branches to find
    FG> out what the checkin message was for the changes to the trunk.

    JH> I agree!  I think it's helpful to include at least a brief
    JH> summary of the changes made on the other branch when doing a
    JH> merge.

Don't forget, checkins will also be read via cvs log years from now.
When you're searching for the patch that changed the foobar widget,
you're going to /really/ appreciate log messages that were written
with care and sufficient detail.

-Barry

""" #'

def _test():
    b = GrahamBayes()
    tokenize = tokenize_words_foldcase
    b.learn(tokenize(spam1), True)
    b.learn(tokenize(spam2), True)
    b.learn(tokenize(good1), False)
    b.learn(tokenize(good2), False)

    print "P(spam3 is spam) =", b.spamprob(tokenize(spam3))
    print "P(good3 is spam) =", b.spamprob(tokenize(good3))


def usage(code, msg=''):
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)


def describe_tokenizers(tokenize):
    print >> sys.stderr, "Possible tokenizing functions are:"
    keys = tokenizers.keys()
    keys.sort()
    maxlen = max(map(len, keys))
    default = "unknown"
    for k in keys:
        func = tokenizers[k]
        if tokenize == func:
            default = k
        doc = func.__doc__ or "???"
        if maxlen + 4 + len(doc) > 78:
            sp = "\n"+" "*5
        else:
            sp = " "*(maxlen-len(k)+1)
        print >> sys.stderr, "  %s:%s%s" % (k, sp, doc)
    if default:
        print >> sys.stderr, "Default tokenizer is", default
    sys.exit(0)


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hHg:s:u:p:c:m:o:t:')
    except getopt.error, msg:
        usage(1, msg)

    if not opts and not args:
        # Called without options or arguments, run the self-test
        _test()
        return

    threshold = count = good = spam = unknown = pck = mark = output = None
    tokenize = tokenize_words_foldcase
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-H':
            describe_tokenizers(tokenize)
        elif opt == '-g':
            good = arg
        elif opt == '-s':
            spam = arg
        elif opt == '-u':
            unknown = arg
        elif opt == '-t':
            tokenize = tokenizers.get(arg)
            if tokenize is None:
                usage(1, "Unrecognized tokenize function: %s" % arg)
        elif opt == '-p':
            pck = arg
        elif opt == '-c':
            count = int(arg)
        elif opt == '-m':
            threshold = float(arg)
        elif opt == '-o':
            output = arg

    if args:
        usage(1)

    save = False
    bayes = None
    if pck:
        try:
            fp = open(pck, 'rb')
        except IOError, e:
            if e.errno <> errno.ENOENT: raise
        else:
            bayes = pickle.load(fp)
            fp.close()
    if bayes is None:
        bayes = GrahamBayes()

    def _factory(fp):
        # Guido sez: IMO, for body encoding, we should do the same level of
        # decoding that a typical mail client does, so that we "see" the same
        # thing an end user sees.  This means base64, but not uuencode
        # (because most mailers don't unpack that automatically).  We may save
        # time base64-decoding by not botherin with attachments, since those
        # aren't shown by default.
        try:
            return email.message_from_file(fp)
        except email.Errors.MessageParseError:
            return ''

    # Assume Unix mailbox format
    if good:
        print 'training with the known good messages'
        fp = open(good)
        mbox = mailbox.PortableUnixMailbox(fp, _factory)
        i = 0
        for msg in mbox:
            # For now we'll take an extremely naive view of messages; we won't
            # decode them at all, just to see what happens.  Later, we might
            # want to uu- or base64-decode, or do other pre-processing on the
            # message.
            bayes.learn(tokenize(str(msg)), False, False)
            i += 1
            if count is not None and i > count:
                break
        fp.close()
        save = True
        print 'done training', i, 'messages'

    if spam:
        print 'training with the known spam messages'
        fp = open(spam)
        mbox = mailbox.PortableUnixMailbox(fp, _factory)
        i = 0
        for msg in mbox:
            # For now we'll take an extremely naive view of messages; we won't
            # decode them at all, just to see what happens.  Later, we might
            # want to uu- or base64-decode, or do other pre-processing on the
            # message.
            bayes.learn(tokenize(str(msg)), True, False)
            i += 1
            if count is not None and i > count:
                break
        fp.close()
        save = True
        print 'done training', i, 'messages'

    bayes.update_probabilities()

    if pck and save:
        fp = open(pck, 'wb')
        pickle.dump(bayes, fp, 1)
        fp.close()

    if unknown:
        if output:
            output = open(output, 'w')
        print 'classifying the unknown'
        fp = open(unknown)
        mbox = mailbox.PortableUnixMailbox(fp, email.message_from_file)
        pos = 0
        allcnt = 0
        spamcnt = goodcnt = 0
        for msg in mbox:
            msgid = msg.get('message-id', '<file offset %d>' % pos)
            pos = fp.tell()
            # For now we'll take an extremely naive view of messages; we won't
            # decode them at all, just to see what happens.  Later, we might
            # want to uu- or base64-decode, or do other pre-processing on the
            # message.
            try:
                prob = bayes.spamprob(tokenize(str(msg)))
            except ValueError:
                # Sigh, bad Content-Type
                continue
            if threshold is not None and prob > threshold:
                msg['X-Bayes-Score'] = str(prob)
            print 'P(%s) =' % msgid, prob
            if output:
                print >> output, msg
            # XXX hardcode
            if prob > 0.90:
                spamcnt += 1
            if prob < 0.09:
                goodcnt += 1
            allcnt += 1
        if output:
            output.close()
        fp.close()
        print 'Num messages =', allcnt
        print 'Good count =', goodcnt
        print 'Spam count =', spamcnt
        print 'Hard to tell =', allcnt - (goodcnt + spamcnt)


if __name__ == '__main__':
    main()
