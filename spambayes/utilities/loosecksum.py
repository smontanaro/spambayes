#!/usr/local/bin/python

"""
Compute a 'loose' checksum on the msg (file on cmdline or via stdin).

Attempts are made to eliminate content which tends to obscure the 'sameness'
of messages.  This is aimed particularly at spam, which tends to contains
lots of small differences across messages to try and thwart spam filters, in
hopes that at least one copy reaches its desitination.

Before calculating the checksum, this script does the following:

    * delete the message header

    * delete HTML tags which generally contain URLs

    * delete anything which looks like an email address or URL

    * finally, discard everything other than ascii letters and digits (note
      that this will almost certainly be ineffectual for spam written in
      eastern languages such as Korean)

An MD5 checksum is then computed for the resulting text and written to stdout.

"""

import getopt
import sys
import email.Parser
import md5
import re
import time
import binascii

def zaptags(data, *tags):
    """delete all tags (and /tags) from input data given as arguments"""
    for pat in tags:
        pat = pat.split(":")
        sub = ""
        if len(pat) >= 2:
            sub = pat[-1]
            pat = ":".join(pat[:-1])
        else:
            pat = pat[0]
            sub = ""
        if '\\' in sub:
            sub = _zap_esc_map(sub)
        try:
            data = re.sub(r'(?i)</?(%s)(?:\s[^>]*)?>'%pat, sub, data)
        except TypeError:
            print (pat, sub, data)
            raise
    return data

def clean(data):
    """Clean the obviously variable stuff from a chunk of data.

    The first (and perhaps only) use of this is to try and eliminate bits
    of data that keep multiple spam email messages from looking the same.
    """
    # Get rid of any HTML tags that hold URLs - tend to have varying content
    # I suppose i could just get rid of all HTML tags
    data = zaptags(data, 'a', 'img', 'base', 'frame')
    # delete anything that looks like an email address
    data = re.sub(r"(?i)[-a-z0-9_.+]+@[-a-z0-9_.]+\.([a-z]+)", "", data)
    # delete anything that looks like a url (catch bare urls)
    data = re.sub(r"(?i)(ftp|http|gopher)://[-a-z0-9_/?&%@=+:;#!~|.,$*]+", "", data)
    # delete pmguid: stuff (turns up frequently)
    data = re.sub(r"pmguid:[^.\s]+(\.[^.\s]+)*", "", data)
    # throw away everything other than alpha & digits
    return re.sub(r"[^A-Za-z0-9]+", "", data)

def flatten(obj):
    # I do not know how to use the email package very well - all I want here
    # is the body of obj expressed as a string - there is probably a better
    # way to accomplish this which I haven't discovered.
    # three types are possible: string, Message (hasattr(get_payload)), list
    if isinstance(obj, str):
        return obj
    if hasattr(obj, "get_payload"):
        return flatten(obj.get_payload())
    if isinstance(obj, list):
        return "\n".join([flatten(b) for b in obj])
    raise TypeError, ("unrecognized body type: %s" % type(obj))

def generate_checksum(f):
    body = flatten(email.Parser.Parser().parse(f))
    return binascii.b2a_hex(md5.new(clean(body)).digest())

def main(args):
    opts, args = getopt.getopt(args, "")
    for opt, arg in opts:
        pass
    if not args:
        inf = sys.stdin
    else:
        inf = file(args[0])

    print generate_checksum(inf)

if __name__ == "__main__":
    main(sys.argv[1:])
