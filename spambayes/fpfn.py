#! /usr/bin/env python
"""Extract false positive and false negative filenames from timcv.py output."""

import sys
import re

def cmpf(a, b):
    # Sort function that sorts by numerical value
    ma = re.search(r'(\d+)/(\d+)$', a)
    mb = re.search(r'(\d+)/(\d+)$', b)
    if ma and mb:
        xa, ya = map(int, ma.groups())
        xb, yb = map(int, mb.groups())
        return cmp((xa, ya), (xb, yb))
    else:
        return cmp(a, b)

def main():
    for name in sys.argv[1:]:
        try:
            f = open(name + ".txt")
        except IOError:
            f = open(name)
        print "===", name, "==="
        fp = []
        fn = []
        for line in f:
            if line.startswith('    new fp: '):
                fp.extend(eval(line[12:]))
            elif line.startswith('    new fn: '):
                fn.extend(eval(line[12:]))
        fp.sort(cmpf)
        fn.sort(cmpf)
        print "--- fp ---"
        for x in fp:
            print x
        print "--- fn ---"
        for x in fn:
            print x

if __name__ == '__main__':
    main()
