#! /usr/local/bin/python

import os
import sys
import regex
import getopt
import string

eheadsearch = regex.compile('</head[ \t\n\r\f]*>', regex.casefold)
bodysearch = regex.compile('<body\(>\|[ \t\n\r\f][^<>]*>\)', regex.casefold)
ebodyearch = regex.compile('</body[ \t\n\r\f]*>', regex.casefold)
titlesearch = regex.compile('<title>\(.*\)</title>', regex.casefold)
h1search = regex.compile('<h1>\(.*\)</h1>', regex.casefold)

banner = """\(
<HR>
To the.*
To the.*
\)?
<HR>
<A HREF=.*
For comments.*
<A HREF=.*
For questions.*
<A HREF=.*
"""
bannersearch = regex.compile(banner)

def strip(fi, fo):
    data = fi.read()
    if eheadsearch.search(data) >= 0:
        i = eheadsearch.regs[0][1]
        head, data = data[:i], data[i:]
    else:
        head = ""
    bstart = bodysearch.search(data)
    if bstart < 0:
        bstart = 0
    else:
        head = head + data[:bstart]
        bstart = bstart + len(bodysearch.group(0))
    if bannersearch.search(data) >= 0:
        i, j = bannersearch.regs[0]
        print "banner", i, j, `data[i:j]`
        data = data[:i] + data[j:]
    end = ebodyearch.search(data, bstart)
    if end < 0:
        end = len(data)
    body = string.strip(data[bstart:end])
    if titlesearch.search(head) >= 0:
        title = titlesearch.group(1)
    elif h1search.search(body) >= 0:
        title = h1search.group(1)
    else:
        title = ""
    if title:
        title = string.join(string.split(title))
        fo.write("Title: %s\n" % title)
    fo.write("\n")
    fo.write(body)
    fo.write('\n')

def error(msg):
    sys.stderr.write(string.strip(str(msg)) + '\n')

def makedirs(dirname):
    if os.path.exists(dirname):
        return 1
    head, tail = os.path.split(dirname)
    if head:
        if not makedirs(head):
            return 0
    try:
        os.mkdir(dirname, 0777)
        return 1
    except os.error:
        return 0

def main():
    opts, args = getopt.getopt(sys.argv[1:], "p:")
    prefix = ""
    for o, a in opts:
        if o == "-p": prefix = a
    if not args:
        strip(sys.stdin, sys.stdout)
    else:
        for file in args:
            name, ext = os.path.splitext(file)
            if ext == ".htp":
                error("file %s is already an HTML prototype" % name)
                continue
            sys.stderr.write("Processing %s ...\n" % file)
            htpname = prefix + name + ".htp"
            dirname = os.path.dirname(htpname)
            if dirname:
                if not makedirs(dirname):
                    error("can't create directory %s" % dirname)
                    continue
            fi = open(file, "r")
            fo = open(htpname, "w")
            strip(fi, fo)
            fi.close()
            fo.close()

if __name__ == '__main__':
    main()
