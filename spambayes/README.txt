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
negative rate is still over 1%.

The code here depends in various ways on the latest Python from CVS
(a.k.a. Python 2.3a0 :-).


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

classifier.py
    An implementation of a Graham-like classifier.

tokenizer.py
    An implementation of tokenize() that Tim can't seem to help but keep
    working on <wink>.

Tester.py
    A test-driver class that feeds streams of msgs to a classifier
    instance, and keeps track of right/wrong percentages, and lists
    of false positives and false negatives.

TestDriver.py
    A higher layer of test helpers, building on Tester above.  It's
    quite usable as-is for building simple test drivers, and more
    complicated ones up to NxN test grids.  It's in the process of being
    extended to allow easy building of N-way cross validation drivers
    (the trick to that is doing so efficiently).  See also rates.py
    and cmp.py below.


Apps
====
hammie.py
    A spamassassin-like filter which uses tokenizer and classifier (above).
    Needs to be made faster, especially for writes.


Concrete Test Drivers
=====================
mboxtest.py
    A concrete test driver like timtest.py, but working with a pair of
    mailbox files rather than the specialized timtest setup.

timtest.py
    A concrete test driver like mboxtest.py, but working with "a
    standard" test data setup (see below) rather than the specialized
    mboxtest setup.

timcv.py
    A first stab at an N-fold cross-validating test driver.  Assumes
    "a standard" data directory setup (see below).
    Subject to arbitrary change.


Test Utilities
==============
rates.py
    Scans the output (so far) from timtest.py, and captures summary
    statistics.

cmp.py
    Given two summary files produced by rates.py, displays an account
    of all the f-p and f-n rates side-by-side, along with who won which
    (etc), and the change in total # of f-ps and f-n.


Test Data Utilities
===================
cleanarch
    A script to repair mbox archives by finding "From" lines that
    should have been escaped, and escaping them.

unheader.py
    A script to remove unwanted headers from an mbox file.  This is mostly
    useful to delete headers which incorrectly might bias the results.

loosecksum.py
    A script to calculate a "loose" checksum for a message.  See the text of
    the script for an operational definition of "loose".

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
    approximate split; rebal.by (below) can be used afterwards to even out
    the number of messages per folder.

rebal.py
    Evens out the number of messages in "standard" test data folders (see
    below).  Needs generalization (e.g., Ham and 4000 are hardcoded now).


Standard Test Data Setup
========================
[Caution:  I'm going to switch this to support N-way cross validation,
 instead of an NxN test grid.  The only effect on the directory structure
 here is that you'll want more directories with fewer msgs in each
 (splitting the data at random into 10 pairs should work very well).
]

Barry gave me mboxes, but the spam corpus I got off the web had one spam
per file, and it only took two days of extreme pain to realize that one msg
per file is enormously easier to work with when testing:  you want to split
these at random into random collections, you may need to replace some at
random when testing reveals spam mistakenly called ham (and vice versa),
etc -- even pasting examples into email is much easier when it's one msg
per file (and the test driver makes it easy to print a msg's file path).

The directory structure under my spambayes directory looks like so:

Data/
    Spam/
        Set1/ (contains 2750 spam .txt files)
        Set2/            ""
        Set3/            ""
        Set4/            ""
        Set5/            ""
    Ham/
        Set1/ (contains 4000 ham .txt files)
        Set2/            ""
        Set3/            ""
        Set4/            ""
        Set5/            ""
        reservoir/ (contains "backup ham")

If you use the same names and structure, huge mounds of the tedious testing
code will work as-is.  The more Set directories the merrier, although
you'll hit a point of diminishing returns if you exceed 10.  The "reservoir"
directory contains a few thousand other random hams.  When a ham is found
that's really spam, I delete it, and then the rebal.py utility moves in a
message at random from the reservoir to replace it.  If I had it to do over
again, I think I'd move such spam into a Spam set (chosen at random),
instead of deleting it.

The hams are 20,000 msgs selected at random from a python-list archive.
The spams are essentially all of Bruce Guenter's 2002 spam archive:

    <http://www.em.ca/~bruceg/spam/>

The sets are grouped into 5 pairs in the obvious way:  Spam/Set1 with
Ham/Set1, and so on.  For each such pair, timtest trains a classifier on
that pair, then runs predictions on each of the other 4 pairs.  In effect,
it's a 5x5 test grid, skipping the diagonal.  There's no particular reason
to avoid predicting against the same set trained on, except that it
takes more time and seems the least interesting thing to try.
