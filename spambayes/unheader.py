#!/usr/bin/env python

import re
import sys
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

class Parser(email.Parser.Parser):
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

def process_mailbox(f, dosa=1, pats=None):
    gen = email.Generator.Generator(sys.stdout, maxheaderlen=0)
    for msg in mailbox.PortableUnixMailbox(f, Parser().parse):
        if pats is not None:
            unheader(msg, pats)
        if dosa:
            deSA(msg)
        gen(msg, unixfrom=1)

def usage():
    print >> sys.stderr, "usage: unheader.py [ -p pat ... ] [ -s ]"
    print >> sys.stderr, "-p pat gives a regex pattern used to eliminate unwanted headers"
    print >> sys.stderr, "'-p pat' may be given multiple times"
    print >> sys.stderr, "-s tells not to remove SpamAssassin headers"

def main(args):
    headerpats = []
    dosa = 1
    try:
        opts, args = getopt.getopt(args, "p:sh")
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
        pats = headerpats and "|".join(headerpats) or None
        if not args:
            f = sys.stdin
        elif len(args) == 1:
            f = file(args[0])
        else:
            usage()
            sys.exit(1)
        process_mailbox(f, dosa, pats)

if __name__ == "__main__":
    main(sys.argv[1:])
