#!/usr/bin/env python

## A hammie front-end to make the simple stuff simple.
##
##
## The intent is to call this from procmail and its ilk like so:
##
##   :0 fw
##   | sb_filter.py
##
## Then, you can set up your MUA to pipe ham and spam to it, one at a
## time, by calling it with either the -g or -s options, respectively.
##
## Author: Neale Pickett <neale@woozle.org>
##

"""Usage: %(program)s [options] [filenames]

Options can one or more of:
    -h
        show usage and exit
    -x
        show some usage examples and exit
    -d DBFILE
        use database in DBFILE
    -D PICKLEFILE
        use pickle (instead of database) in PICKLEFILE
    -n
        create a new database
*   -f
        filter (default if no processing options are given)
*   -g
        [EXPERIMENTAL] (re)train as a good (ham) message
*   -s
        [EXPERIMENTAL] (re)train as a bad (spam) message
*   -t
        [EXPERIMENTAL] filter and train based on the result -- you must
        make sure to untrain all mistakes later.  Not recommended.
*   -G
        [EXPERIMENTAL] untrain ham (only use if you've already trained
        this message)
*   -S
        [EXPERIMENTAL] untrain spam (only use if you've already trained
        this message)

    -o section:option:value
        set [section, option] in the options database to value

All options marked with '*' operate on stdin, and write the resultant
message to stdout.

If no filenames are given on the command line, standard input will be
processed as a single message.  If one or more filenames are given on the
command line, each will be processed according to the following rules:

    * If the filename is '-', standard input will be processed as a single
      message (may only be usefully given once).

    * If the filename starts with '+' it will be processed as an MH folder.

    * If the filename is a directory and it contains a subdirectory named
      'cur', it will be processed as a Maildir.

    * If the filename is a directory and it contains a subdirectory named
      'Mail', it will be processed as an MH Mailbox.

    * If the filename is a directory and not a Maildir nor an MH Mailbox, it
      will be processed as a Mailbox directory consisting of just .txt and
      .lorien files.

    * Otherwise, the filename is treated as a Unix-style mailbox (messages
      begin on a line starting with 'From ').

Output is always to standard output as a Unix-style mailbox.
"""

import os
import sys
import getopt
from spambayes import hammie, Options, mboxutils
from spambayes.Version import get_version_string

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

# See Options.py for explanations of these properties
program = sys.argv[0]

example_doc = """_Examples_

filter a message on disk:
    %(program)s < message

(re)train a message as ham:
    %(program)s -g < message

(re)train a message as spam:
    %(program)s -s < message


procmail recipe to filter and train in one step:
    :0 fw
    | %(program)s -t


mutt configuration:  This binds the 'H' key to retrain the message as
ham, and prompt for a folder to move it to.  The 'S' key retrains as
spam, and moves to a 'spam' folder.  See contrib/muttrc in the spambayes
distribution for other neat mutt tricks.

  macro index S "|sb_filter.py -s | procmail\n"
  macro pager S "|sb_filter.py -s | procmail\n"
  macro index H "|sb_filter.py -g | procmail\n"
  macro pager H "|sb_filter.py -g | procmail\n"
  color index red black "~h 'X-Spambayes-Disposition: spam' ~F"


"""

def examples():
    print example_doc % globals()
    sys.exit(0)

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    # Include version info in usage
    print >> sys.stderr, get_version_string("sb_filter")
    print >> sys.stderr, "    with engine %s" % get_version_string()
    print >> sys.stderr
    
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

class HammieFilter(object):
    def __init__(self):
        options = Options.options
        # This is a bit of a hack to counter the default for
        # persistent_storage_file changing from ~/.hammiedb to hammie.db
        # This will work unless a user:
        #   * had hammie.db as their value for persistent_storage_file, and
        #   * their config file was loaded by Options.py.
        if options["Storage", "persistent_storage_file"] == \
           options.default("Storage", "persistent_storage_file"):
            options["Storage", "persistent_storage_file"] = \
                                    "~/.hammiedb"
        options.merge_files(['/etc/hammierc',
                            os.path.expanduser('~/.hammierc')])
        self.dbname = Options.get_pathname_option("Storage",
                                                  "persistent_storage_file")
        self.usedb = options["Storage", "persistent_use_database"]

    def newdb(self):
        h = hammie.open(self.dbname, self.usedb, 'n')
        h.store()
        print >> sys.stderr, "Created new database in", self.dbname

    def filter(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'r')
        return h.filter(msg)

    def filter_train(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        return h.filter(msg, train=True)

    def train_ham(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        h.train_ham(msg, True)
        h.store()

    def train_spam(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        h.train_spam(msg, True)
        h.store()

    def untrain_ham(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        h.untrain_ham(msg)
        h.store()

    def untrain_spam(self, msg):
        h = hammie.open(self.dbname, self.usedb, 'c')
        h.untrain_spam(msg)
        h.store()

def main():
    h = HammieFilter()
    actions = []
    opts, args = getopt.getopt(sys.argv[1:], 'hxd:D:nfgstGSo:',
                               ['help', 'examples', 'option='])
    create_newdb = False
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage(0)
        elif opt in ('-x', '--examples'):
            examples()
        elif opt in ('-o', '--option'):
            Options.options.set_from_cmdline(arg, sys.stderr)
        elif opt == '-d':
            h.usedb = True
            h.dbname = arg
        elif opt == '-D':
            h.usedb = False
            h.dbname = arg
        elif opt == '-f':
            actions.append(h.filter)
        elif opt == '-g':
            actions.append(h.train_ham)
        elif opt == '-s':
            actions.append(h.train_spam)
        elif opt == '-t':
            actions.append(h.filter_train)
        elif opt == '-G':
            actions.append(h.untrain_ham)
        elif opt == '-S':
            actions.append(h.untrain_spam)
        elif opt == "-n":
            create_newdb = True

    if create_newdb:
        h.newdb()
        sys.exit(0)

    if actions == []:
        actions = [h.filter]

    if not args:
        args = ["-"]
    for fname in args:
        mbox = mboxutils.getmbox(fname)
        for msg in mbox:
            for action in actions:
                action(msg)
                if args == ["-"]:
                    unixfrom = msg.get_unixfrom() is not None
                else:
                    unixfrom = True
            sys.stdout.write(msg.as_string(unixfrom=unixfrom))

if __name__ == "__main__":
    main()
