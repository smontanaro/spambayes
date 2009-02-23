Copyright (C) 2002-2009 Python Software Foundation; All Rights Reserved

The Python Software Foundation (PSF) holds copyright on all material
in this project.  You may use it under the terms of the PSF license;
see LICENSE.txt.


Assorted clues.


What's Here?
============
Lots of mondo cool partially documented code.  What else could there be <wink>?

The focus of this project so far has not been to produce the fastest or
smallest filters, but to set up a flexible pure-Python implementation
for doing algorithm research.  Lots of people are making fast/small
implementations, and it takes an entirely different kind of effort to
make genuine algorithm improvements.  I think we've done quite well at
that so far.  The focus of this codebase may change to small/fast
later -- as is, the false positive rate has gotten too small to measure
reliably across test sets with 4000 hams + 2750 spams, and the f-n rate
has also gotten too small to measure reliably across that much training data.

The code in this project requires Python 2.2 (or later).

You should definitely check out the FAQ:
http://spambayes.org/faq.html

Getting Source Code
===================

The SpamBayes project source code is hosted at SourceForge
(http://spambayes.sourceforge.net/).  Access is via Subversion.

Running Unit Tests
==================

SpamBayes has a currently incomplete set of unit tests, not all of which
pass, due, in part, to bit rot.  We are working on getting the unit tests to
run using the `nose <http://somethingaboutorange.com/mrl/projects/nose/>`_
package.  After downloading and installing nose, you can run the current
unit tests on Unix-like systems like so from the SpamBayes top-level
directory::

    TMPDIR=/tmp BAYESCUSTOMIZE= nosetests -v . 2>&1 \
    | sed -e "s:$(pwd)/::" \
          -e "s:$(python -c 'import sys ; print sys.exec_prefix')/::" \
    | tee failing-unit-tests.txt

The file, failing-unit-tests.txt, is checked into the Subversion repository
at the top level using Python from Subversion (currently 2.7a0).  You can
look at it for any failing unit tests and work to get them passing, or write
new tests.

Primary Core Files
==================
Options.py
    Uses ConfigParser to allow fiddling various aspects of the classifier,
    tokenizer, and test drivers.  Create a file named bayescustomize.ini to
    alter the defaults.  Modules wishing to control aspects of their
    operation merely do

        from Options import options

    near the start, and consult attributes of options.  To see what options
    are available, import Options.py and do

        print Options.options.display_full()

    This will print out a detailed description of each option, the allowed
    values, and so on.  (You can pass in a section or section and option
    name to display_full if you don't want the whole list).

    As an alternative to bayescustomize.ini, you can set the environment
    variable BAYESCUSTOMIZE to a list of one or more .ini files, these will
    be read in, in order, and applied to the options. This allows you to
    tweak individual runs by combining fragments of .ini files.  The
    character used to separate different .ini files is platform-dependent.
    On Unix, Linux and Mac OS X systems it is ':'.  On Windows it is ';'.
    On Mac OS 9 and earlier systems it is a NL character.

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
sb_filter.py
    A simpler hammie front-end that doesn't print anything.  Useful for
    procmail filtering and scoring from your MUA.

sb_mboxtrain.py
    Trainer for Maildir, MH, or mbox mailboxes.  Remembers which
    messages it saw the last time you ran it, and will only train on new
    messages or messages which should be retrained.  

    The idea is to run this automatically every night on your Inbox and
    Spam folders, and then sort misclassified messages by hand.  This
    will work with any IMAP4 mail client, or any client running on the
    server.

sb_server.py
    A spam-classifying POP3 proxy.  It adds a spam-judgment header to
    each mail as it's retrieved, so you can use your email client's
    filters to deal with them without needing to fiddle with your email
    delivery system.

    Also acts as a web server providing a user interface that allows you
    to train the classifier, classify messages interactively, and query
    the token database.  This piece may at some point be split out into
    a separate module.

    If the appropriate options are set, also serves a message training
    SMTP proxy.  It sits between your email client and your SMTP server
    and intercepts mail to set ham and spam addresses.
    All other mail is simply passed through to the SMTP server.

sb_mailsort.py
    A delivery agent that uses a CDB of word probabilities and delivers
    a message to one of two Maildir message folders, depending on the
    classifier score.  Note that both Maildirs must be on the same
    device.

sb_xmlrpcserver.py
    A stab at making hammie into a client/server model, using XML-RPC.

sb_client.py
    A client for sb_xmlrpcserver.py.

sb_imapfilter.py
    A spam-classifying and training application for use with IMAP servers.
    You can specify folders that contain mail to train as ham/spam, and
    folders that contain mail to classify, and the filter will do so.


Test Driver Core
================
Tester.py
    A test-driver class that feeds streams of msgs to a classifier
    instance, and keeps track of right/wrong percentages and lists
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
cleanarch.py
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
    A Bourne shell script (for Unix) which will run some test or other.
    I (Neale) will try to keep this updated to test whatever Tim is
    currently asking for.  The idea is, if you have a standard directory
    structure (below), you can run this thing, go have some tea while it
    works, then paste the output to the SpamBayes list for good karma.


Standard Test Data Setup
========================
Barry gave Tim mboxes, but the spam corpus he got off the web had one spam
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

CAUTION:  The partitioning of your corpora across directories should
be random.  If it isn't, bias creeps in to the test results.  This is
usually screamingly obvious under the NxN grid method (rates vary by a
factor of 10 or more across training sets, and even within runs against
a single training set), but harder to spot using N-fold c-v.

Testing a change and posting the results
========================================

(Adapted from clues Tim posted on the spambayes and spambayes-dev lists)

Firstly, setup your data as above; it's really not worth the hassle to
come up with a different scheme.  If you use the Outlook plug-in, the
export.py script in the Outlook2000 directory will export all the spam
and ham in your 'training' folders for you into this format (or close
enough).

Basically the idea is that you should have 10 sets of data, each with
200 to 500 messages in them.  Obviously if you're testing something to
do with the size of a corpus, you'll want to change that.  You then want
to run
    timcv.py -n 10 > std.txt
(call std.txt whatever you like), and then
    rates.py std.txt
You end up with two files, std.txt, which has the raw results, and stds.txt,
which has more of a summary of the results.

Now make the change to the code or options, and repeat the process,
giving the files different names (note that rates.py will automatically
choose the name for the output file, based on the input one).

You've now got the data you need, but you have to interpret it.  The
simplest way of all is just to post it to spambayes-dev@python.org and let
someone else do it for you <wink>.  The data you should post is the output of
    cmp.py stds.txt alts.txt
along with the output of
    table.py stds.txt alts.txt
(note that these just print to stdout).

Other information you can find in the 'raw' output (std.txt, above) are
histograms of the ham/spam spread, and a copy of the options settings.

Interpreting cmp.py output
--------------------------

(Using an example from Tim on spambayes-dev)

> cv_octs.txt -> cv_oct_subjs.txt
> -> <stat> tested 488 hams & 897 spams against 1824 hams & 3501 spams 
> -> <stat> tested 462 hams & 863 spams against 1850 hams & 3535 spams 
> -> <stat> tested 475 hams & 863 spams against 1837 hams & 3535 spams 
> -> <stat> tested 430 hams & 887 spams against 1882 hams & 3511 spams 
> -> <stat> tested 457 hams & 888 spams against 1855 hams & 3510 spams 
> -> <stat> tested 488 hams & 897 spams against 1824 hams & 3501 spams 
> -> <stat> tested 462 hams & 863 spams against 1850 hams & 3535 spams 
> -> <stat> tested 475 hams & 863 spams against 1837 hams & 3535 spams 
> -> <stat> tested 430 hams & 887 spams against 1882 hams & 3511 spams 
> -> <stat> tested 457 hams & 888 spams against 1855 hams & 3510 spams
>
> false positive percentages
>     0.000  0.000  tied
>     0.000  0.000  tied
>     0.000  0.000  tied
>     0.000  0.000  tied
>     0.219  0.219  tied
>
> won   0 times
> tied  5 times
> lost  0 times

So all 5 runs tied on FP.  That tells us much more than that the *net*
effect across 5 runs was nil on FP:  it tells us that there are no hidden
glitches hiding behind that "net nothing" -- it was no change across the board.

> total unique fp went from 1 to 1 tied
> mean fp % went from 0.0437636761488 to 0.0437636761488 tied
>
> false negative percentages
>     2.007  2.007  tied
>     1.390  1.390  tied
>     1.622  1.622  tied
>     2.029  1.917  won     -5.52%
>     2.703  2.477  won     -8.36%
>
> won   2 times
> tied  3 times
> lost  0 times

When evaluating a small change, I'm heartened to see that in no run did it lose.
At worst it tied, and twice it helped a little.  That's encouraging.

What the histograms would tell us that we can't tell from this is whether you
could have done just as well without the change by raising your ham cutoff a little.
That would also tie on FP, and *may* also get rid of the same number (or even
more) of FN.

> total unique fn went from 86 to 83 won     -3.49%
> mean fn % went from 1.95029003772 to 1.88269707836 won     -3.47%
>
> ham mean                     ham sdev
>    0.57    0.58   +1.75%        4.63    4.77   +3.02%
>    0.08    0.07  -12.50%        1.20    1.01  -15.83%
>    0.36    0.29  -19.44%        3.61    3.23  -10.53%
>    0.08    0.11  +37.50%        0.89    1.18  +32.58%
>    0.72    0.76   +5.56%        6.80    7.06   +3.82%
>
> ham mean and sdev for all runs
>    0.37    0.37   +0.00%        4.10    4.16   +1.46%

That's a good example of grand averages hiding the truth:  the averaged change
in the mean ham score was 0 across all 5 runs, but *within* the 5 runs it slobbered
around wildly, from decreasing 20% to increasing 40%(!).

> spam mean                    spam sdev
>   96.43   96.44   +0.01%       15.89   15.89   +0.00%
>   97.01   97.07   +0.06%       13.79   13.70   -0.65%
>   97.14   97.16   +0.02%       14.05   14.02   -0.21%
>   96.52   96.56   +0.04%       15.65   15.52   -0.83%
>   95.53   95.63   +0.10%       17.47   17.31   -0.92%
>
> spam mean and sdev for all runs
>   96.52   96.57   +0.05%       15.46   15.37   -0.58%

That's good to see:  it's a consistent win for spam scores across runs,
although an almost imperceptible one.  It's good when the mean spam score rises,
and it's good when sdev (for ham or spam) decreases.

> ham/spam mean difference: 96.15 96.20 +0.05

This is a slight win for the chance, although seeing the details gives cause
to worry some about the effect on ham:  the ham sdev increased overall, and
the effects on ham mean and ham sdev varied wildly across runs.  OTOH, the
"before" numbers for ham mean and ham sdev varied wildly across runs already.
That gives cause to worry some about the data <wink>.


Making a source release
=======================

Source releases are built with distutils.  Here's how I (Richie) have been
building them.  I do this on a Windows box, partly so that the zip release
can have Windows line endings without needing to run a conversion script.
I don't think that's actually necessary, because everything would work on
Windows even with Unix line endings, but you couldn't load the files into
Notepad and sometimes it's convenient to do so.  End users might not even
have any other text editor, so it make things like the README unREADable.
8-)

Anthony would rather eat live worms than trying to get a sane environment
on Windows, so his approach to building the zip file is at the end.

 o If any new file types have been added since last time (eg. 1.0a5 went
   out without the Windows .rc and .h files) then add them to MANIFEST.in.
   If there are any new scripts or packages, add them to setup.py.  Test
   these changes (by building source packages according to the instructions
   below) then commit your edits.
 o Checkout the 'spambayes' module twice, once with Windows line endings
   and once with Unix line endings (I use WinCVS for this, using "Admin /
   Preferences / Globals / Checkout text files with the Unix LF".  If you
   use TortoiseCVS, like Tony, then the option is on the Options tab in
   the checkout dialog).
 o Change spambayes/__init__.py to contain the new version number but don't
   commit it yet, just in case something goes wrong.
 o Note that if you cheated above, and used an existing checkout, you need
   to ensure that you don't have extra files in there.  For example, if you
   have a few thousand email messages in testtools/Data, setup.py will take
   a *very* long time.
 o In the Windows checkout, run "python setup.py sdist --formats zip"
 o In the Unix checkout, run "python setup.py sdist --formats gztar"
 o Take the resulting spambayes-1.0a5.zip and spambayes-1.0a5.tar.gz, and
   test the former on Windows (ideally in a freshly-installed Python
   environment; I keep a VMWare snapshot of a clean Windows installation
   for this, but that's probably overkill 8-) and test the latter on Unix
   (a Debian VMWare box in my case).
 o If you can, rename these with "rc" at the end, and make them available
   to the spambayes-dev crowd as release candidates.  If all is OK, then
   fix the names (or redo this) and keep going.
 o Dance the SourceForge release dance:
   http://sourceforge.net/docman/display_doc.php?docid=6445&group_id=1#filereleasesteps
   When it comes to the "what's new" and the ChangeLog, I cut'n'paste the
   relevant pieces of WHAT_IS_NEW.txt and CHANGELOG.txt into the form, and
   check the "Keep my preformatted text" checkbox.
 o Now commit spambayes/__init__.py and tag the whole checkout - see the
   existing tag names for the tag name format.
 o In either checkout, run "python setup.py register" to register the new
   version with PyPI.
 o Update download.ht with checksums, links, and sizes for the files.
   From release 1.1 doing a "setup.py sdist" will generate checksums
   and sizes for you, and print out the results to stdout.
 o Create OpenPGP/PGP signatures for the files.  Using GnuPG:
      % gpg -sab spambayes-1.0.1.zip
      % gpg -sab spambayes-1.0.1.tar.gz
      % gpg -sab spambayes-1.0.1.exe
   Put the created *.asc files in the "sigs" directory of the website.
   (Note that when you update the website, you will need to manually ssh
   to shell1.sourceforge.net and chmod these files so that people can
   access them.)
 o If your public key isn't already linked to on the Download page, put
   it there.
 o Update the website News, Download and Windows sections.
 o Update reply.txt in the website repository as needed (it specifies the
   latest version).  Then let Tim, Barry, Tony, or Skip know that they need
   to update the autoresponder.
 o Run "make install version" in the website directory to push the new
   version file, so that "Check for new version" works.
 o Add '+' to the end of spambayes/__init__.py's __version__, to
   differentiate CVS users, and check this change in.  After a number of
   changes have been checked in, this can be incremented and have "a0"
   added to the end. For example, with a 1.1 release:
       [before the release process] '1.1rc1'
       [during the release process] '1.1'
       [after the release process]  '1.1+'
       [later]                      '1.2a0'
       
Then announce the release on the mailing lists and watch the bug reports
roll in.  8-)

Anthony's Alternate Approach to Building the Zipfile

 o Unpack the tarball somewhere, making a spambayes-1.0a7 directory
   (version number will obviously change in future releases)
 o Run the following two commands:

     find spambayes-1.0a7 -type f -name '*.txt' | xargs zip -l sb107.zip 
     find spambayes-1.0a7 -type f \! -name '*.txt' | xargs zip sb107.zip 

 o This makes a tarball where the .txt files are mangled, but everything
   else is left alone.

Making a binary release
=======================

The binary release includes both sb_server and the Outlook plug-in and
is an installer for Windows (98 and above) systems.  In order to have
COM typelibs that work with Outlook 2000, 2002 and 2003, you need to
build the installer on a system that has Outlook 2000 (not a more recent
version).  You also need to have InnoSetup, pywin32, resourcepackage and
py2exe installed.

 o Get hold of a fresh copy of the source (Windows line endings,
   presumably).
 o Run the setup.py file in the spambayes/Outlook2000/docs directory
   to generate the dynamic documentation.
 o Run sb_server and open the web interface.  This gets resourcepackage
   to generate the needed files.
 o Replace the __init__.py file in spambayes/spambayes/resources with
   a blank file to disable resourcepackage.
 o Ensure that the version numbers in spambayes/spambayes/__init__.py
   and spambayes/spambayes/Version.py are up-to-date.
 o Ensure that you don't have any other copies of spambayes in your
   PYTHONPATH, or py2exe will pick these up!  If in doubt, run
   setup.py install.
 o Run the "setup_all.py" script in the spambayes/windows/py2exe/
   directory. This uses py2exe to create the files that Inno will install.
 o Open (in InnoSetup) the spambayes.iss file in the spambayes/windows/
   directory.  Change the version number in the AppVerName and
   OutputBaseFilename lines to the new number.
 o Compile the spambayes.iss script to get the executable.
 o You can now follow the steps in the source release description above,
   from the testing step.

Making a translation
====================

Note that it is, in general, best to translate against a stable version.
This means you avoid having to repeatedly re-translate text as the
code changes.  This means code that has been released via the sourceforge
system, that does not have a letter code at the end of the version (e.g.
1.0.1, 1.1.2, but not 1.0a1, 1.1b1, or 2.1rc2).  If you do want to
translate a more recent version, be sure to discuss your plans first on
spambayes-dev so that you can be warned about any planned changes.

Translation is only feasible for 1.1 and above.  No translation effort
is planned for the 1.0.x series of releases.

To translate, you will need:

 o A suitable version of Python (2.2 or greater) installed.
   See http://python.org/download

 o A copy of the SpamBayes source that you wish to translate.

 o Resourcepackage installed.
   See http://resourcepackage.sourceforge.net

Optional tools that may make translation easier include:

 o A copy of VC++, Visual Studio, or some other GUI tool that allows
   editing of VC++ dialog resource files.

 o A GUI HTML editor.

 o A GUI gettext editor, such as poEdit.
   http://poedit.sourceforge.net

Setup
-----

You will need to create a directory structure as follows:

spambayes/                                    # spambayes package directory
                                              # containing classifier.py, tokenizer.py, etc
          languages/                          # root languages directory,
                                              # possibly already containing
                                              # other translations
                    {lang_code}/              # directory for the specific
                                              # translation - {lang_code} is
                                              # described below
                                DIALOGS/      # directory for Outlook plug-in
                                              # dialog resources, which should contain an
                                              # empty __init__.py file, so that py2exe can
                                              # include the directory
                                LC_MESSAGES/  # directory for gettext managed
                                              # strings, which should also contain an
                                              # empty __init__.py file
                                __init__.py   # Copy of spambayes/spambayes/resources/__init__.py


Translation Tasks
-----------------

There are four translation tasks:

 o Documentation.  This is the least exciting, but the most important.
   If the documentation is appropriately translated, then even if elements
   of the interface are not translated, users should be able to manage.

   A method of managing translated documents has yet to be created.  If you
   are interested in translating documentation, please contact
   spambayes-dev@python.org.

 o Outlook dialogs.  The majority of the Outlook plug-in interface is
   handled by a VC++/Visual Studio dialog resource file pair (dialogs.h
   and dialogs.rc).  The plug-in code then manipulates this to create the
   actual dialog.

   The easiest method of translating these dialogs is to use a tool like
   VC++ or Visual Studio.  Simply open the
   'Outlook2000\dialogs\resources\dialogs.rc' file, translate the dialog,
   and save the file as
   'spambayes\languages\{lang_code}\DIALOGS\dialogs.rc', where {lang_code}
   is the appropriate language code for the language you have translated
   into (e.g. 'en_UK', 'es', 'de_DE').  If you do not have a GUI tool to
   edit the dialogs, simply open the dialogs.rc file in a text editor,
   manually change the appropriate strings, and save the file as above.

   Once the dialogs are translated, you need to use the rc2py.py utility
   to create the i18n_dialogs.py file.  For example, in the
   'Outlook2000\dialogs\resources' directory:
     > rc2py.py {base}\spambayes\languages\de_DE\DIALOGS\dialogs.rc
       {base}\spambayes\languages\de_DE\DIALOGS\i18n_dialogs.py 1
   Where {base} is the directory that contains the spambayes package directory.
   This should create a 'i18n_dialogs.py' in the same directory as your
   translated dialogs.rc file - this is the file the the Outlook plug-in
   uses.

 o Web interface template file.  The majority of the web interface is
   created by dynamic use of a HTML template file.

   The easiest method of translating this file is to use a GUI HTML editor.
   Simply open the 'spambayes/resources/ui.html' file, translate
   it as described within, and save the file as
   'spambayes/languages/{lang_code}/i18n.ui.html', where {lang_code} is
   the appropriate language code as described above.  If you do not have
   a GUI HTML editor, or are happy editing HTML by hand, simply use your
   favority HTML editor to do this task.

   Once the template file is created, resourcepackage will automatically
   create the required ui_html.py file when SpamBayes is run with that
   language selected.

 o Gettext managed strings.  The remainder of both the Outlook plug-in
   and the web interface are contained within the various Python files
   that make up SpamBayes.  The Python gettext module (very similar to
   the GNU gettext system) is used to manage translation of these strings.

   To translate these strings, use the translation template
   'spambayes/languages/messages.pot'.  You can regenerate that file, if
   necessary, by running this command in the spambayes package directory:
     > {python dir}\tools\i18n\pygettext.py -o languages\messages.pot
       ..\contrib\*.py ..\Outlook2000\*.py ..\scripts\*.py *.py
       ..\testtools\*.py ..\utilities\*.py ..\windows\*.py

   You may wish to use a GUI system to create the required messages.po file, 
   such as poEdit, but you can also do this manually with a text editor.
   If your utility does not do it for you, you will also need to
   compile the .po file to a .mo file.  The utility msgfmt.py will do
   this for you - it should be located '{python dir}\tools\i18n'.

Testing the translation
-----------------------

There are two ways to set the language that SpamBayes will use:

 o If you are using Windows, change the preferred Windows language using
   the Control Panel.

 o Get the '[globals] language' SpamBayes option to a list of the
   preferred language(s).
