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
    A flexible higher layer of test helpers, building on Tester above.
    For example, it's usable for building simple test drivers, NxN test
    grids, and N-fold cross validation drivers.  See also rates.py and
    cmp.py below.


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
    mboxtest setup.  This runs an NxN test grid, skipping the diagonal.

timcv.py
    A first stab at an N-fold cross-validating test driver.  Assumes
    "a standard" data directory setup (see below).
    Subject to arbitrary change.


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

If you use the same names and structure, huge mounds of the tedious testing
code will work as-is.  The more Set directories the merrier, although you
want at least a few hundred messages in each one.  The "reservoir" directory
contains a few thousand other random hams.  When a ham is found that's
really spam, move into a spam directory, and then the rebal.py utility
moves in a random message from the reservoir to replace it.

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
