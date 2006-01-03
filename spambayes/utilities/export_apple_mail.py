#!/usr/bin/env python

"""export_apple_mail.py

Converts Apple Mail's emlx files to plain text files usable
by SpamBayes's testtools.

Adding some way to display help would be good.  For now, read
this file and run the script with the path to the user's
~/Library/Mail directory.

(Tested on Windows XP remotely accessing the Mac filesystem.
I don't know if the bundling of the files in the Mail directory
would effect this script or not, and can't be bothered finding
out right now).
"""

import os
import sys

from spambayes.Options import options

def emlx_to_rfc2822(in_fn, out_fn):
    """Convert an individual file in Apple Mail's emlx format
    to a file with just the RFC2822 message.

    The emlx format is simply the length of the message (as a
    string) on the first line, then the raw message text, then
    the contents of a plist (XML) file that contains data that
    Mail uses (subject, flags, sender, and so forth).  We ignore
    this plist data).
    """
    fin = file(in_fn)
    fout = file(out_fn, "w")
    length = int(fin.readline().rstrip())
    fout.write(fin.read(length))
    plist = fin.read()

def export(mail_dir):
    """Scans through the specified directory, which should be
    the Apple Mail user's ~\Library\Mail folder, converting
    all found emlx files to simple RFC2822 messages suitable
    for use with the SpamBayes testtools.

    Messages are copied (the originals are left untouched) into
    the standard SpamBayes testtools setup (all files are put in the
    reservoir; use rebal.py to distribute).

    The script assumes that all messages outside of Mail's
    Junk folder are ham, and all messages inside the Junk folder
    are spam.

    Any messages in the "Sent Messages" folders are skipped.

    A simple extension of this function would allow only certain
    accounts/mailboxes to be exported.
    """
    for dirname in os.listdir(mail_dir):
        # There is no mail at the top level.
        dirname = os.path.join(mail_dir, dirname)
        if os.path.isdir(dirname):
            export_directory(mail_dir, dirname)
    print

def export_directory(parent, dirname):
    if parent == "Junk.mbox":
        # All of these should be spam.  Make sure that you
        # check for false positives first!
        dest_dir = os.path.join(\
            os.path.dirname(options["TestDriver", "spam_directories"]),
            "reservoir")
    elif parent == "Sent Messages.mbox" or parent == "Drafts.mbox":
        # We don't do anything with outgoing mail.
        return
    else:
        # Everything else is ham.
        dest_dir = os.path.join(\
            os.path.dirname(options["TestDriver", "ham_directories"]),
            "reservoir")
    dest_dir = os.path.normpath(dest_dir)
    for path in os.listdir(dirname):
        path = os.path.join(dirname, path)
        if os.path.isdir(path):
            export_directory(dirname, path)
        else:
            fn, ext = os.path.splitext(path)
            if ext == ".emlx":
                in_fn = os.path.join(dirname, path)
                out_fn = os.path.join(dest_dir,
                                      os.path.basename(fn) + ".txt")
                emlx_to_rfc2822(in_fn, out_fn)
                sys.stdout.write('.')

if __name__ == "__main__":
    export(sys.argv[1])
