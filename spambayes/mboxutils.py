"""Utilities for dealing with various types of mailboxes.

This is mostly a wrapper around the various useful classes in the
standard mailbox module, to do some intelligent guessing of the
mailbox type given a mailbox argument.

+foo      -- MH mailbox +foo
+foo,bar  -- MH mailboxes +foo and +bar concatenated
+ALL      -- a shortcut for *all* MH mailboxes
/foo/bar  -- (existing file) a Unix-style mailbox
/foo/bar/ -- (existing directory) a directory full of .txt and .lorien
             files
/foo/Mail/bar/ -- (existing directory with /Mail/ in its path)
             alternative way of spelling an MH mailbox

"""

from __future__ import generators

import os
import glob
import email
import mailbox

class DirOfTxtFileMailbox:

    """Mailbox directory consisting of .txt and .lorien files."""

    def __init__(self, dirname, factory):
        self.names = (glob.glob(os.path.join(dirname, "*.txt")) +
                      glob.glob(os.path.join(dirname, "*.lorien")))
        self.names.sort()
        self.factory = factory

    def __iter__(self):
        for name in self.names:
            try:
                f = open(name)
            except IOError:
                continue
            yield self.factory(f)
            f.close()

def _factory(fp):
    # Helper for getmbox
    try:
        return email.message_from_file(fp)
    except email.Errors.MessageParseError:
        return ''

def _cat(seqs):
    for seq in seqs:
        for item in seq:
            yield item

def getmbox(name):
    """Return an mbox iterator given a file/directory/folder name."""

    if name.startswith("+"):
        # MH folder name: +folder, +f1,f2,f2, or +ALL
        name = name[1:]
        import mhlib
        mh = mhlib.MH()
        if name == "ALL":
            names = mh.listfolders()
        elif ',' in name:
            names = name.split(',')
        else:
            names = [name]
        mboxes = []
        mhpath = mh.getpath()
        for name in names:
            filename = os.path.join(mhpath, name)
            mbox = mailbox.MHMailbox(filename, _factory)
            mboxes.append(mbox)
        if len(mboxes) == 1:
            return iter(mboxes[0])
        else:
            return _cat(mboxes)

    if os.path.isdir(name):
        # XXX Bogus: use an MHMailbox if the pathname contains /Mail/,
        # else a DirOfTxtFileMailbox.
        if name.find("/Mail/") >= 0:
            mbox = mailbox.MHMailbox(name, _factory)
        else:
            mbox = DirOfTxtFileMailbox(name, _factory)
    else:
        fp = open(name)
        mbox = mailbox.PortableUnixMailbox(fp, _factory)
    return iter(mbox)
