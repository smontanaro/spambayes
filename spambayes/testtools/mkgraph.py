import sys

set = ""
nham_tested = []
nham_trained = []
nham_right = []
nham_wrong = []
nham_unsure = []
nspam_tested = []
nspam_trained = []
nspam_right = []
nspam_wrong = []
nspam_unsure = []

def outputset():
    global set
    global nham_tested
    global nham_trained
    global nham_right
    global nham_wrong
    global nham_unsure
    global nspam_tested
    global nspam_trained
    global nspam_right
    global nspam_wrong
    global nspam_unsure

    if set == "":
        return

    print '$ Data=Curve2d name="Set %s Cumulative"' % set
    print '% linetype=1 linelabel="ham_tested" markertype=0 linecolor=0'
    for k in range(0, len(nham_tested)):
        print '%d %d' % (k, nham_tested[k])
    print
    print '% linetype=1 linelabel="ham_trained" markertype=0 linecolor=1'
    for k in range(0, len(nham_trained)):
        print '%d %d' % (k, nham_trained[k])
    print
    print '% linetype=1 linelabel="ham_right" markertype=0 linecolor=2'
    for k in range(0, len(nham_right)):
        print '%d %d' % (k, nham_right[k])
    print
    print '% linetype=1 linelabel="ham_wrong" markertype=0 linecolor=3'
    for k in range(0, len(nham_wrong)):
        print '%d %d' % (k, nham_wrong[k])
    print
    print '% linetype=1 linelabel="ham_unsure" markertype=0 linecolor=4'
    for k in range(0, len(nham_unsure)):
        print '%d %d' % (k, nham_unsure[k])
    print
    print '% linetype=1 linelabel="spam_tested" markertype=0 linecolor=5'
    for k in range(0, len(nspam_tested)):
        print '%d %d' % (k, nspam_tested[k])
    print
    print '% linetype=1 linelabel="spam_trained" markertype=0 linecolor=6'
    for k in range(0, len(nspam_trained)):
        print '%d %d' % (k, nspam_trained[k])
    print
    print '% linetype=1 linelabel="spam_right" markertype=0 linecolor=7'
    for k in range(0, len(nspam_right)):
        print '%d %d' % (k, nspam_right[k])
    print
    print '% linetype=1 linelabel="spam_wrong" markertype=0 linecolor=8'
    for k in range(0, len(nspam_wrong)):
        print '%d %d' % (k, nspam_wrong[k])
    print
    print '% linetype=1 linelabel="spam_unsure" markertype=0 linecolor=9'
    for k in range(0, len(nspam_unsure)):
        print '%d %d' % (k, nspam_unsure[k])
    print
    
    print '$ Data=Curve2d name="Set %s Cumulative Error Rates"' % set
    print '% linetype=1 linelabel="fp" markertype=0 linecolor=0'
    for k in range(0, len(nham_wrong)):
        print '%d %f' % (k, (nham_wrong[k] * 1.0 / (nham_tested[k] or 1)))
    print
    print '% linetype=1 linelabel="fn" markertype=0 linecolor=1'
    for k in range(0, len(nspam_wrong)):
        print '%d %f' % (k, (nspam_wrong[k] * 1.0 / (nspam_tested[k] or 1)))
    print
    print '% linetype=1 linelabel="fn" markertype=0 linecolor=2'
    for k in range(0, len(nspam_unsure)):
        print '%d %f' % (k, ((nspam_unsure[k] + nham_unsure[k]) * 1.0 /
                             ((nspam_tested[k] + nham_tested[k]) or 1)))
    print

    set = ""
    nham_tested = []
    nham_trained = []
    nham_right = []
    nham_wrong = []
    nham_unsure = []
    nspam_tested = []
    nspam_trained = []
    nspam_right = []
    nspam_wrong = []
    nspam_unsure = []

def main():
    global set
    global nham_tested
    global nham_trained
    global nham_right
    global nham_wrong
    global nham_unsure
    global nspam_tested
    global nspam_trained
    global nspam_right
    global nspam_wrong
    global nspam_unsure

    while 1:
        line = sys.stdin.readline()
        if line == "":
            break
        if line.endswith("\n"):
            line = line[:-1]
        print "# " + line
        if line.startswith("Set "):
            outputset()
            set = line[4:]
        if len(line) > 0 and (line[0] in ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9')):
            vals = line.split(" ")
            nham_tested.append(int(vals[0]))
            nham_trained.append(int(vals[1]))
            nham_right.append(int(vals[2]))
            nham_wrong.append(int(vals[3]))
            nham_unsure.append(int(vals[4]))
            nspam_tested.append(int(vals[5]))
            nspam_trained.append(int(vals[6]))
            nspam_right.append(int(vals[7]))
            nspam_wrong.append(int(vals[8]))
            nspam_unsure.append(int(vals[9]))

    outputset()

if __name__ == "__main__":
    main()

