import math as _math

def chi2Q(x2, v, exp=_math.exp):
    """Return prob(chisq >= x2, with v degrees of freedom).

    v must be even.
    """
    assert v & 1 == 0
    m = x2 / 2.0
    sum = term = exp(-m)
    for i in range(1, v//2):
        term *= m / i
        sum += term
    return sum

def main():
    from Histogram import Hist
    import sys

    class WrappedRandom:
        # There's no way W-H is equidistributed in 50 dimensions, so use
        # Marsaglia-wrapping to shuffle it more.

        def __init__(self, baserandom=random.random, tabsize=513):
            self.baserandom = baserandom
            self.n = tabsize
            self.tab = [baserandom() for i in range(tabsize)]
            self.next = baserandom()

        def random(self):
            result = self.next
            i = int(result * self.n)
            self.next = self.tab[i]
            self.tab[i] = self.baserandom()
            return result

    random = WrappedRandom().random
    #from uni import uni as random
    #print random

    def judge(ps, ln=_math.log):
        H = S = 0.0
        for p in ps:
            S += ln(1.0 - p)
            H += ln(p)
        n = len(ps)
        S = 1.0 - chi2Q(-2.0 * S, 2*n)
        H = 1.0 - chi2Q(-2.0 * H, 2*n)
        return S/(S+H)

    warp = 0
    bias = 0.99
    if len(sys.argv) > 1:
        warp = int(sys.argv[1])
    if len(sys.argv) > 2:
        bias = float(sys.argv[2])

    h = Hist(20, lo=0.0, hi=1.0)

    for i in range(50000):
        ps = [random() for j in range(50)]
        p = judge(ps + [bias] * warp)
        h.add(p)

    print "Result for random vectors of 50 probs, +", warp, "forced to", bias
    print
    h.display()

def showscore(ps, ln=_math.log):
    H = S = 0.0
    for p in ps:
        S += ln(1.0 - p)
        H += ln(p)

    n = len(ps)
    probS = chi2Q(-2*S, 2*n)
    probH = chi2Q(-2*H, 2*n)
    print "P(chisq >= %10g | v=%3d) = %10g" % (-2*S, 2*n, probS)
    print "P(chisq >= %10g | v=%3d) = %10g" % (-2*H, 2*n, probH)

    S = 1.0 - probS
    H = 1.0 - probH
    score = S/(S+H)
    print "spam prob", S
    print " ham prob", H
    print "  S/(S+H)", score

if __name__ == '__main__':
    import random
    main()
