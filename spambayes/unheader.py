#!/usr/bin/env python

import re
import sys
import os
import glob
import mailbox
import email.Parser
import email.Message
import email.Generator
import getopt

def unheader(msg, pat):
    pat = re.compile(pat)
    for hdr in msg.keys():
        if pat.match(hdr):
            del msg[hdr]

class Message(email.Message.Message):
    def replace_header(self, hdr, newval):
        """replace first value for hdr with newval"""
        hdr = hdr.lower()
        for i in range(len(self._headers)):
            k, v = self._headers[i]
            if k.lower() == hdr:
                self._headers[i] = (k, newval)

class Parser(email.Parser.HeaderParser):
    def __init__(self):
        email.Parser.Parser.__init__(self, Message)

def deSA(msg):
    if msg['X-Spam-Status']:
        if msg['X-Spam-Status'].startswith('Yes'):
            pct = msg['X-Spam-Prev-Content-Type']
            if pct:
                msg['Content-Type'] = pct

            pcte = msg['X-Spam-Prev-Content-Transfer-Encoding']
            if pcte:
                msg['Content-Transfer-Encoding'] = pcte

            subj = re.sub(r'\*\*\*\*\*SPAM\*\*\*\*\* ', '',
                          msg['Subject'] or "")
            if subj != msg["Subject"]:
                msg.replace_header("Subject", subj)

            body = msg.get_payload()
            newbody = []
            at_start = 1
            for line in body.splitlines():
                if at_start and line.startswith('SPAM: '):
                    continue
                elif at_start:
                    at_start = 0
                newbody.append(line)
            msg.set_payload("\n".join(newbody))
    unheader(msg, "X-Spam-")

def process_message(msg, dosa, pats):
    if pats is not None:
        unheader(msg, pats)
    if dosa:
        deSA(msg)

def process_mailbox(f, dosa=1, pats=None):
    gen = email.Generator.Generator(sys.stdout, maxheaderlen=0)
    for msg in mailbox.PortableUnixMailbox(f, Parser().parse):
        process_message(msg, dosa, pats)
        gen(msg, unixfrom=1)

def process_maildir(d, dosa=1, pats=None):
    parser = Parser()
    for fn in glob.glob(os.path.join(d, "cur", "*")):
        print ("reading from %s..." % fn),
        file = open(fn)
        msg = parser.parse(file)
        process_message(msg, dosa, pats)

        tmpfn = os.path.join(d, "tmp", os.path.basename(fn))
        tmpfile = open(tmpfn, "w")
        print "writing to %s" % tmpfn
        email.Generator.Generator(tmpfile, maxheaderlen=0)(msg, unixfrom=0)

        os.rename(tmpfn, fn)

def usage():
    print >> sys.stderr, "usage: unheader.py [ -p pat ... ] [ -s ] folder"
    print >> sys.stderr, "-p pat gives a regex pattern used to eliminate unwanted headers"
    print >> sys.stderr, "'-p pat' may be given multiple times"
    print >> sys.stderr, "-s tells not to remove SpamAssassin headers"
    print >> sys.stderr, "-d means treat folder as a Maildir"

def main(args):
    headerpats = []
    dosa = 1
    ismbox = 1
    try:
        opts, args = getopt.getopt(args, "p:shd")
    except getopt.GetoptError:
        usage()
        sys.exit(1)
    else:
        for opt, arg in opts:
            if opt == "-h":
                usage()
                sys.exit(0)
            elif opt == "-p":
                headerpats.append(arg)
            elif opt == "-s":
                dosa = 0
            elif opt == "-d":
                ismbox = 0
        pats = headerpats and "|".join(headerpats) or None

        if len(args) != 1:
            usage()
            sys.exit(1)

        if ismbox:
            f = file(args[0])
            process_mailbox(f, dosa, pats)
        else:
            process_maildir(args[0], dosa, pats)

if __name__ == "__main__":
    main(sys.argv[1:])
