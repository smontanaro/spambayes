#! /usr/bin/env python

### Train spambayes on all previously-untrained messages in a mailbox.
###
### This keeps track of messages it's already trained by adding an
### X-Spambayes-Trained: header to each one.  Then, if you move one to
### another folder, it will retrain that message.  You would want to run
### this from a cron job on your server.

"""Usage: %(program)s [OPTIONS] ...

Where OPTIONS is one or more of:
    -h
        show usage and exit
    -d DBNAME
        use the DBM store.  A DBM file is larger than the pickle and
        creating it is slower, but loading it is much faster,
        especially for large word databases.  Recommended for use with
        hammiefilter or any procmail-based filter.
    -D DBNAME
        use the pickle store.  A pickle is smaller and faster to create,
        but much slower to load.  Recommended for use with pop3proxy and
        hammiesrv.
    -g PATH
        mbox or directory of known good messages (non-spam) to train on.
        Can be specified more than once.
    -s PATH
        mbox or directory of known spam messages to train on.
        Can be specified more than once.
    -f
        force training, ignoring the trained header.  Use this if you
        need to rebuild your database from scratch.
    -q
        quiet mode; no output
        
    -n  train mail residing in "new" directory, in addition to "cur"
        directory, which is always trained (Maildir only)

    -r  remove mail which was trained on (Maildir only)
"""

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

import sys, os, getopt
from spambayes import hammie, mboxutils
from spambayes.Options import options

program = sys.argv[0]
loud = True

def msg_train(h, msg, is_spam, force):
    """Train bayes with a single message."""

    # XXX: big hack -- why is email.Message unable to represent
    # multipart/alternative?
    try:
        msg.as_string()
    except TypeError:
        # We'll be unable to represent this as text :(
        return False

    if is_spam:
        spamtxt = options["Headers", "header_spam_string"]
    else:
        spamtxt = options["Headers", "header_ham_string"]
    oldtxt = msg.get(options["Headers", "trained_header_name"])
    if force:
        # Train no matter what.
        if oldtxt != None:
            del msg[options["Headers", "trained_header_name"]]
    elif oldtxt == spamtxt:
        # Skip this one, we've already trained with it.
        return False
    elif oldtxt != None:
        # It's been trained, but as something else.  Untrain.
        del msg[options["Headers", "trained_header_name"]]
        h.untrain(msg, not is_spam)
    h.train(msg, is_spam)
    msg.add_header(options["Headers", "trained_header_name"], spamtxt)

    return True

def maildir_train(h, path, is_spam, force, removetrained):
    """Train bayes with all messages from a maildir."""

    if loud: print "  Reading %s as Maildir" % (path,)

    import time
    import socket

    pid = os.getpid()
    host = socket.gethostname()
    counter = 0
    trained = 0

    for fn in os.listdir(path):
        cfn = os.path.join(path, fn)
        tfn = os.path.normpath(os.path.join(path, "..", "tmp",
                           "%d.%d_%d.%s" % (time.time(), pid,
                                            counter, host)))
        if (os.path.isdir(cfn)):
            continue
        counter += 1
        if loud and counter % 10 == 0:
            sys.stdout.write("\r%6d" % counter)
            sys.stdout.flush()
        f = file(cfn, "rb")
        msg = mboxutils.get_message(f)
        f.close()
        if not msg_train(h, msg, is_spam, force):
            continue
        trained += 1
        if not options["Headers", "include_trained"]:
            continue
        f = file(tfn, "wb")
        f.write(msg.as_string())
        f.close()
        # XXX: This will raise an exception on Windows.  Do any Windows
        # people actually use Maildirs?
        os.rename(tfn, cfn)
        if (removetrained):
            os.unlink(cfn)

    if loud:
        sys.stdout.write("\r%6d" % counter)
        sys.stdout.write("\r  Trained %d out of %d messages\n" %
                         (trained, counter))

def mbox_train(h, path, is_spam, force):
    """Train bayes with a Unix mbox"""

    if loud: print "  Reading as Unix mbox"

    import mailbox
    import fcntl

    # Open and lock the mailbox.  Some systems require it be opened for
    # writes in order to assert an exclusive lock.
    f = file(path, "r+b")
    fcntl.flock(f, fcntl.LOCK_EX)
    mbox = mailbox.PortableUnixMailbox(f, mboxutils.get_message)

    outf = os.tmpfile()
    counter = 0
    trained = 0

    for msg in mbox:
        counter += 1
        if loud and counter % 10 == 0:
            sys.stdout.write("\r%6d" % counter)
            sys.stdout.flush()
        if msg_train(h, msg, is_spam, force):
            trained += 1
        if not options["Headers", "include_trained"]:
            # Write it out with the Unix "From " line
            outf.write(msg.as_string(True))

    if not options["Headers", "include_trained"]:
        outf.seek(0)
        try:
            os.ftruncate(f.fileno(), 0)
            f.seek(0)
        except:
            # If anything goes wrong, don't try to write
            print "Problem truncating mbox--nothing written"
            raise
        try:
            for line in outf.xreadlines():
                f.write(line)
        except:
            print >> sys.stderr ("Problem writing mbox!  Sorry, "
                                 "I tried my best, but your mail "
                                 "may be corrupted.")
            raise

    fcntl.lockf(f, fcntl.LOCK_UN)
    f.close()
    if loud:
        sys.stdout.write("\r%6d" % counter)
        sys.stdout.write("\r  Trained %d out of %d messages\n" %
                         (trained, counter))

def mhdir_train(h, path, is_spam, force):
    """Train bayes with an mh directory"""

    if loud: print "  Reading as MH mailbox"

    import glob

    counter = 0
    trained = 0

    for fn in glob.glob(os.path.join(path, "[0-9]*")):
        counter += 1

        cfn = fn
        tfn = os.path.join(path, "spambayes.tmp")
        if loud and counter % 10 == 0:
            sys.stdout.write("\r%6d" % counter)
            sys.stdout.flush()
        f = file(fn, "rb")
        msg = mboxutils.get_message(f)
        f.close()
        msg_train(h, msg, is_spam, force)
        trained += 1
        if not options["Headers", "include_trained"]:
            continue
        f = file(tfn, "wb")
        f.write(msg.as_string())
        f.close()

        # XXX: This will raise an exception on Windows.  Do any Windows
        # people actually use MH directories?
        os.rename(tfn, cfn)

    if loud:
        sys.stdout.write("\r%6d" % counter)
        sys.stdout.write("\r  Trained %d out of %d messages\n" %
                         (trained, counter))

def train(h, path, is_spam, force, trainnew, removetrained):
    if not os.path.exists(path):
        raise ValueError("Nonexistent path: %s" % path)
    elif os.path.isfile(path):
        mbox_train(h, path, is_spam, force)
    elif os.path.isdir(os.path.join(path, "cur")):
        maildir_train(h, os.path.join(path, "cur"), is_spam, force,
                      removetrained)
        if trainnew:
            maildir_train(h, os.path.join(path, "new"), is_spam, force,
                          removetrained)
    elif os.path.isdir(path):
        mhdir_train(h, path, is_spam, force)
    else:
        raise ValueError("Unable to determine mailbox type: " + path)


def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def main():
    """Main program; parse options and go."""

    global loud

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hfqnrd:D:g:s:')
    except getopt.error, msg:
        usage(2, msg)

    if not opts:
        usage(2, "No options given")

    pck = None
    usedb = None
    force = False
    trainnew = False
    removetrained = False
    good = []
    spam = []
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == "-f":
            force = True
        elif opt == "-n":
            trainnew = True
        elif opt == "-q":
            loud = False
        elif opt == '-g':
            good.append(arg)
        elif opt == '-s':
            spam.append(arg)
        elif opt == "-r":
            removetrained = True
        elif opt == "-d":
            usedb = True
            pck = arg
        elif opt == "-D":
            usedb = False
            pck = arg
    if args:
        usage(2, "Positional arguments not allowed")

    if usedb == None:
        usage(2, "Must specify one of -d or -D")

    h = hammie.open(pck, usedb, "c")

    for g in good:
        if loud: print "Training ham (%s):" % g
        train(h, g, False, force, trainnew, removetrained)
        sys.stdout.flush()
        save = True

    for s in spam:
        if loud: print "Training spam (%s):" % s
        train(h, s, True, force, trainnew, removetrained)
        sys.stdout.flush()
        save = True

    if save:
        h.store()


if __name__ == "__main__":
    main()
