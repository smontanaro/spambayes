import sys
import getopt

report = "error"
span = None

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

def line(vals):
    global span
    for k in range(0, len(vals)):
        n = vals[k]
        if span and k - span >= 0:
            n -= vals[k - span]
        print '%d %d' % (k, n)
    print


def outputset():
    global report
    global span
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

    if span:
        title = "%d-Day Average" % span
    else:
        title = "Cumulative"

    if report == "counts":
        print '$ Data=Curve2d name="%s Counts"' % (title)
        print '% linetype=1 linelabel="ham_tested" markertype=0 linecolor=0'
        line(nham_tested)
        print '% linetype=1 linelabel="ham_trained" markertype=0 linecolor=1'
        line(nham_trained)
        print '% linetype=1 linelabel="ham_right" markertype=0 linecolor=2'
        line(nham_right)
        print '% linetype=1 linelabel="ham_wrong" markertype=0 linecolor=3'
        line(nham_wrong)
        print '% linetype=1 linelabel="ham_unsure" markertype=0 linecolor=4'
        line(nham_unsure)
        print '% linetype=1 linelabel="spam_tested" markertype=0 linecolor=5'
        line(nspam_tested)
        print '% linetype=1 linelabel="spam_trained" markertype=0 linecolor=6'
        line(nspam_trained)
        print '% linetype=1 linelabel="spam_right" markertype=0 linecolor=7'
        line(nspam_right)
        print '% linetype=1 linelabel="spam_wrong" markertype=0 linecolor=8'
        line(nspam_wrong)
        print '% linetype=1 linelabel="spam_unsure" markertype=0 linecolor=9'
        line(nspam_unsure)

    if report == "error":
        print '$ Data=Curve2d'
        print '% toplabel="%s Error Rates"' % (title)
        print '% ymax=5'
        print '% xlabel="Days"'
        print '% ylabel="Percent"'
        print '% linetype=1 linelabel="fp" markertype=0 linecolor=0'
        for k in range(0, len(nham_wrong)):
            n = nham_wrong[k]
            d = nham_tested[k]
            if span and k - span >= 0:
                n -= nham_wrong[k - span]
                d -= nham_tested[k - span]
            print '%d %f' % (k, (n * 100.0 / (d or 1)))
        print
        print '% linetype=1 linelabel="fn" markertype=0 linecolor=1'
        for k in range(0, len(nspam_wrong)):
            n = nspam_wrong[k]
            d = nspam_tested[k]
            if span and k - span >= 0:
                n -= nspam_wrong[k - span]
                d -= nspam_tested[k - span]
            print '%d %f' % (k, (n * 100.0 / (d or 1)))
        print
        print '% linetype=1 linelabel="unsure" markertype=0 linecolor=2'
        for k in range(0, len(nspam_unsure)):
            n = nham_unsure[k] + nspam_unsure[k]
            d = nham_tested[k] + nspam_tested[k]
            if span and k - span >= 0:
                n -= nham_unsure[k - span] + nspam_unsure[k - span]
                d -= nham_tested[k - span] + nspam_tested[k - span]
            print '%d %f' % (k, (n * 100.0 / (d or 1)))
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
    global report
    global span
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

    opts, args = getopt.getopt(sys.argv[1:], 's:r:')
    for opt, arg in opts:
        if opt == '-s':
            span = int(arg)
        if opt == '-r':
            report = arg

    if report not in ("error", "counts"):
        print >> sys.stderr, "Unrecognized report type"
        sys.exit(1)

    while 1:
        line = sys.stdin.readline()
        if line == "":
            break
        if line.endswith("\n"):
            line = line[:-1]
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
