Copyright (C) 2002 Python Software Foundation; All Rights Reserved

The Python Software Foundation (PSF) holds copyright on all material
in this project.  You may use it under the terms of the PSF license;
see LICENSE.txt.


Assorted clues.


What's Here?
============
Lots of mondo cool undocumented code.  What else could there be <wink>?

The focus of this project so far has not been to produce the fastest or
smallest filters, but to set up a flexible pure-Python implementation
for doing algorithm research.  Lots of people are making fast/small
implementations, and it takes an entirely different kind of effort to
make genuine algorithm improvements.  I think we've done quite well at
that so far.  The focus of this codebase may change to small/fast
later -- as is, the false positive rate has gotten too small to measure
reliably across test sets with 4000 hams + 2750 spams, but the false
negative rate is still over 1%.  Later:  the f-n rate has also gotten
too small to measure reliably across that much training data.

The code in this project requires Python 2.2 (or later).


Primary Core Files
==================
Options.py
    Uses ConfigParser to allow fiddling various aspects of the classifier,
    tokenizer, and test drivers.  Create a file named bayescustomize.ini to
    alter the defaults; all options and their default values can be found
    in the string "defaults" near the top of Options.py, which is really
    an .ini file embedded in the module.  Modules wishing to control
    aspects of their operation merely do

        from Options import options

    near the start, and consult attributes of options.

    As an alternative to bayescustomize.ini, you can set the environment
    variable BAYESCUSTOMIZE to a list of one or more .ini files, these will
    be read in, in order, and applied to the options. This allows you to
    tweak individual runs by combining fragments of .ini files.  The
    character used to separate different .ini files is platform-dependent.
    On Unix, Linux and Mac OS X systems it is ':'.  On Windows it is ';'.
    On Mac OS 9 and earlier systems it is a NL character.

    *NOTE* The separator character changed after the second alpha version of
    the first release.  Previously, if multiple files were specified in
    BAYESCUSTOMIZE they were space-separated.

classifier.py
    The classifier, which is the soul of the method.

tokenizer.py
    An implementation of tokenize() that Tim can't seem to help but keep
    working on <wink>.  Generates a token stream from a message, which
    the classifier trains on or predicts against.

chi2.py
    A collection of statistics functions.


Apps
====
hammie.py
    A spamassassin-like filter which uses tokenizer and classifier (above).

hammiefilter.py
    A simpler hammie front-end that doesn't print anything.  Useful for
    procmail filering and scoring from your MUA.

mboxtrain.py
    Trainer for Maildir, MH, or mbox mailboxes.  Remembers which
    messages it saw the last time you ran it, and will only train on new
    messages or messages which should be retrained.  

    The idea is to run this automatically every night on your Inbox and
    Spam folders, and then sort misclassified messages by hand.  This
    will work with any IMAP4 mail client, or any client running on the
    server.

pop3proxy.py
    A spam-classifying POP3 proxy.  It adds a spam-judgement header to
    each mail as it's retrieved, so you can use your email client's
    filters to deal with them without needing to fiddle with your email
    delivery system.

    Also acts as a web server providing a user interface that allows you
    to train the classifier, classify messages interactively, and query
    the token database.  This piece will at some point be split out into
    a separate module.

mailsort.py
    A delivery agent that uses a CDB of word probabilities and delivers
    a message to one of two Maildir message folders, depending on the
    classifier score.  Note that both Maildirs must be on the same
    device.

hammiesrv.py
    A stab at making hammie into a client/server model, using XML-RPC.

hammiecli.py
    A client for hammiesrv.


Test Driver Core
================
Tester.py
    A test-driver class that feeds streams of msgs to a classifier
    instance, and keeps track of right/wrong percentages, and lists
    of false positives and false negatives.

TestDriver.py
    A flexible higher layer of test helpers, building on Tester above.
    For example, it's usable for building simple test drivers, NxN test
    grids, and N-fold cross-validation drivers.  See also rates.py,
    cmp.py, and table.py below.

msgs.py
    Some simple classes to wrap raw msgs, and to produce streams of
    msgs.  The test drivers use these.


Concrete Test Drivers
=====================
mboxtest.py
    A concrete test driver like timtest.py, but working with a pair of
    mailbox files rather than the specialized timtest setup.

timcv.py
    An N-fold cross-validating test driver.  Assumes "a standard" data
        directory setup (see below)) rather than the specialized mboxtest
        setup.
    N classifiers are built.
    1 run is done with each classifier.
    Each classifier is trained on N-1 sets, and predicts against the sole
        remaining set (the set not used to train the classifier).
    mboxtest does the same.
    This (or mboxtest) is the preferred way to test when possible:  it
        makes best use of limited data, and interpreting results is
        straightforward.

timtest.py
    A concrete test driver like mboxtest.py, but working with "a standard"
        test data setup (see below).  This runs an NxN test grid, skipping
        the diagonal.
    N classifiers are built.
    N-1 runs are done with each classifier.
    Each classifier is trained on 1 set, and predicts against each of
        the N-1 remaining sets (those not used to train the classifier).
    This is a much harder test than timcv, because it trains on N-1 times
        less data, and makes each classifier predict against N-1 times
        more data than it's been taught about.
    It's harder to interpret the results of timtest (than timcv) correctly,
        because each msg is predicted against N-1 times overall.  So, e.g.,
        one terribly difficult spam or ham can count against you N-1 times.


Test Utilities
==============
rates.py
    Scans the output (so far) produced by TestDriver.Drive(), and captures
    summary statistics.

cmp.py
    Given two summary files produced by rates.py, displays an account
    of all the f-p and f-n rates side-by-side, along with who won which
    (etc), the change in total # of unique false positives and negatives,
    and the change in average f-p and f-n rates.

table.py
    Summarizes the high-order bits from any number of summary files,
    in a compact table.

fpfn.py
    Given one or more TestDriver output files, prints list of false
    positive and false negative filenames, one per line.


Test Data Utilities
===================
cleanarch
    A script to repair mbox archives by finding "Unix From" lines that
    should have been escaped, and escaping them.

unheader.py
    A script to remove unwanted headers from an mbox file.  This is mostly
    useful to delete headers which incorrectly might bias the results.
    In default mode, this is similar to 'spamassassin -d', but much, much
    faster.

loosecksum.py
    A script to calculate a "loose" checksum for a message.  See the text of
    the script for an operational definition of "loose".

rebal.py
    Evens out the number of messages in "standard" test data folders (see
    below).  Needs generalization (e.g., Ham and 4000 are hardcoded now).

mboxcount.py
    Count the number of messages (both parseable and unparseable) in
    mbox archives.

split.py
splitn.py
    Split an mbox into random pieces in various ways.  Tim recommends
    using "the standard" test data set up instead (see below).

splitndirs.py
    Like splitn.py (above), but splits an mbox into one message per file in
    "the standard" directory structure (see below).  This does an
    approximate split; rebal.py (above) can be used afterwards to even out
    the number of messages per folder.

runtest.sh
    A bourne shell script (for Unix) which will run some test or other.
    I (Neale) will try to keep this updated to test whatever Tim is
    currently asking for.  The idea is, if you have a standard directory
    structure (below), you can run this thing, go have some tea while it
    works, then paste the output to the spambayes list for good karma.


Standard Test Data Setup
========================
Barry gave me mboxes, but the spam corpus I got off the web had one spam
per file, and it only took two days of extreme pain to realize that one msg
per file is enormously easier to work with when testing:  you want to split
these at random into random collections, you may need to replace some at
random when testing reveals spam mistakenly called ham (and vice versa),
etc -- even pasting examples into email is much easier when it's one msg
per file (and the test drivers make it easy to print a msg's file path).

The directory structure under my spambayes directory looks like so:

Data/
    Spam/
        Set1/ (contains 1375 spam .txt files)
        Set2/            ""
        Set3/            ""
        Set4/            ""
        Set5/            ""
        Set6/            ""
        Set7/            ""
        Set9/            ""
        Set9/            ""
        Set10/           ""
	reservoir/ (contains "backup spam")
    Ham/
        Set1/ (contains 2000 ham .txt files)
        Set2/            ""
        Set3/            ""
        Set4/            ""
        Set5/            ""
        Set6/            ""
        Set7/            ""
        Set8/            ""
        Set9/            ""
        Set10/           ""
        reservoir/ (contains "backup ham")

Every file at the deepest level is used (not just files with .txt
extensions).  The files don't need to have a "Unix From"
header before the RFC-822 message (i.e. a line of the form "From
<address> <date>").

If you use the same names and structure, huge mounds of the tedious testing
code will work as-is.  The more Set directories the merrier, although you
want at least a few hundred messages in each one.  The "reservoir"
directories contain a few thousand other random hams and spams.  When a ham
is found that's really spam, move it into a spam directory, then use the
rebal.py utility to rebalance the Set directories moving random message(s)
into and/or out of the reservoir directories.  The reverse works as well
(finding ham in your spam directories).

The hams are 20,000 msgs selected at random from a python-list archive.
The spams are essentially all of Bruce Guenter's 2002 spam archive:

    <http://www.em.ca/~bruceg/spam/>

The sets are grouped into pairs in the obvious way:  Spam/Set1 with
Ham/Set1, and so on.  For each such pair, timtest trains a classifier on
that pair, then runs predictions on each of the other pairs.  In effect,
it's a NxN test grid, skipping the diagonal.  There's no particular reason
to avoid predicting against the same set trained on, except that it
takes more time and seems the least interesting thing to try.

Later, support for N-fold cross validation testing was added, which allows
more accurate measurement of error rates with smaller amounts of training
data.  That's recommended now.  timcv.py is to cross-validation testing
as the older timtest.py is to grid testing.  timcv.py has grown additional
arguments to allow using only a random subset of messages in each Set.

CAUTION:  The parititioning of your corpora across directories should
be random.  If it isn't, bias creeps in to the test results.  This is
usually screamingly obvious under the NxN grid method (rates vary by a
factor of 10 or more across training sets, and even within runs against
a single training set), but harder to spot using N-fold c-v.
