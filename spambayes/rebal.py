import os
import sys
import random

'''
dead = """
Data/Ham/Set2/22467.txt
Data/Ham/Set5/31389.txt
Data/Ham/Set1/19642.txt
"""

for f in dead.split():
    os.unlink(f)

sys.exit(0)
'''

NPERDIR = 4000
RESDIR = 'Data/Ham/reservoir'
res = os.listdir(RESDIR)

stuff = []
for i in range(1, 6):
    dir = 'Data/Ham/Set%d' % i
    fs = os.listdir(dir)
    stuff.append((dir, fs))

while stuff:
    dir, fs = stuff.pop()
    if len(fs) == NPERDIR:
        continue

    if len(fs) > NPERDIR:
        f = random.choice(fs)
        fs.remove(f)
        print "deleting", f, "from", dir
        os.unlink(dir + "/" + f)

    elif len(fs) < NPERDIR:
        print "need a new one for", dir
        f = random.choice(res)
        print "How about", f
        res.remove(f)

        fp = file(RESDIR + "/" + f, 'rb')
        guts = fp.read()
        fp.close()
        os.unlink(RESDIR + "/" + f)

        print guts
        ok = raw_input('good enough? ')
        if ok.startswith('y'):
            fp = file(dir + "/" + f, 'wb')
            fp.write(guts)
            fp.close()
            fs.append(f)

    stuff.append((dir, fs))
