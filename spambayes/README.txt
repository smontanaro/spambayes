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


Primary Files
=============
classifier.py
    An implementation of a Graham-like classifier.

Tester.py
    A test-driver class that feeds streams of msgs to a classifier
    instance, and keeps track of right/wrong percentages, and lists
    of false positives and false negatives.

timtest.py
    A concrete test driver and tokenizer that uses Tester and
    classifier (above).  This assumes "a standard" test data setup
    (see below).  Could stand massive refactoring.

GBayes.py
    A number of tokenizers and a partial test driver.  This assumes
    an mbox format.  Could stand massive refactoring.  I don't think
    it's been kept up to date.


Test Utilities
==============
rates.py
    Scans the output (so far) from timtest.py, and captures summary
    statistics.


Test Data Utilities
===================
rebal.py
    Evens out the number of messages in "standard" test data folders (see
    below).

cleanarch
    A script to repair mbox archives by finding "From" lines that
    should have been escaped, and escaping them.

mboxcount.py
    Count the number of messages (both parseable and unparseable) in
    mbox archives.

split.py
splitn.py
    Split an mbox into random pieces in various ways.  Tim recommends
    using "the standard" test data set up instead (see below).


Standard Test Data Setup
========================
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
