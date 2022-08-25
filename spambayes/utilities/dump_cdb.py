#! /usr/bin/env python


RC_DIR = "~/.spambayes"
DB_FILE = RC_DIR + "/wordprobs.cdb"

import sys
from spambayes.cdb import Cdb


def main():
    db_file = sys.argv[1]
    db = Cdb(open(db_file, 'rb'))
    items = []
    for k, v in db.items():
        items.append((float(v), k))

    items.sort()
    for v, k in items:
        print(repr(k), '%.4f' % v)


if __name__ == "__main__":
    main()
