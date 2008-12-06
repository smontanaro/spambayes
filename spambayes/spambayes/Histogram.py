#! /usr/bin/env python
import math

from spambayes.Options import options

class Hist:
    """Simple histograms of float values."""

    # Pass None for lo and hi and it will automatically adjust to the min
    # and max values seen.
    # Note:  nbuckets can be passed for backward compatibility.  The
    # display() method can be passed a different nbuckets value.
    def __init__(self, nbuckets=options["TestDriver", "nbuckets"],
                 lo=0.0, hi=100.0):
        self.lo, self.hi = lo, hi
        self.nbuckets = nbuckets
        self.buckets = [0] * nbuckets
        self.data = []  # the raw data points
        self.stats_uptodate = False

    # Add a value to the collection.
    def add(self, x):
        self.data.append(x)
        self.stats_uptodate = False

    # Compute, and set as instance attrs:
    #     n         # of data points
    # The rest are set iff n>0:
    #     min       smallest value in collection
    #     max       largest value in collection
    #     median    midpoint
    #     mean
    #     pct       list of (percentile, score) pairs
    #     var       variance
    #     sdev      population standard deviation (sqrt(variance))
    # self.data is also sorted.
    def compute_stats(self):
        if self.stats_uptodate:
            return
        self.stats_uptodate = True
        data = self.data
        n = self.n = len(data)
        if n == 0:
            return
        data.sort()
        self.min = data[0]
        self.max = data[-1]
        if n & 1:
            self.median = data[n // 2]
        else:
            self.median = (data[n // 2] + data[(n-1) // 2]) / 2.0
        # Compute mean.
        # Add in increasing order of magnitude, to minimize roundoff error.
        if data[0] < 0.0:
            temp = [(abs(x), x) for x in data]
            temp.sort()
            data = [x[1] for x in temp]
            del temp
        sum = 0.0
        for x in data:
            sum += x
        mean = self.mean = sum / n
        # Compute variance.
        var = 0.0
        for x in data:
            d = x - mean
            var += d*d
        self.var = var / n
        self.sdev = math.sqrt(self.var)
        # Compute percentiles.
        self.pct = pct = []
        for p in options["TestDriver", "percentiles"]:
            assert 0.0 <= p <= 100.0
            # In going from data index 0 to index n-1, we move n-1 times.
            # p% of that is (n-1)*p/100.
            i = (n-1)*p/1e2
            if i < 0:
                # Just return the smallest.
                score = data[0]
            else:
                whole = int(i)
                frac = i - whole
                score = data[whole]
                if whole < n-1 and frac:
                    # Move frac of the way from this score to the next.
                    score += frac * (data[whole + 1] - score)
            pct.append((p, score))

    # Merge other into self.
    def __iadd__(self, other):
        self.data.extend(other.data)
        self.stats_uptodate = False
        return self

    def get_lo_hi(self):
        self.compute_stats()
        lo, hi = self.lo, self.hi
        if lo is None:
            lo = self.min
        if hi is None:
            hi = self.max
        return lo, hi

    def get_bucketwidth(self):
        lo, hi = self.get_lo_hi()
        span = float(hi - lo)
        return span / self.nbuckets

    # Set instance var nbuckets to the # of buckets, and buckets to a list
    # of nbuckets counts.
    def fill_buckets(self, nbuckets=None):
        if nbuckets is None:
            nbuckets = self.nbuckets
        if nbuckets <= 0:
            raise ValueError("nbuckets %g > 0 required" % nbuckets)
        self.nbuckets = nbuckets
        self.buckets = buckets = [0] * nbuckets

        # Compute bucket counts.
        lo, hi = self.get_lo_hi()
        bucketwidth = self.get_bucketwidth()
        for x in self.data:
            i = int((x - lo) / bucketwidth)
            if i >= nbuckets:
                i = nbuckets - 1
            elif i < 0:
                i = 0
            buckets[i] += 1

    # Print a histogram to stdout.
    # Also sets instance var nbuckets to the # of buckets, and
    # buckts to a list of nbuckets counts, but only if at least one
    # data point is in the collection.
    def display(self, nbuckets=None, WIDTH=61):
        if nbuckets is None:
            nbuckets = self.nbuckets
        if nbuckets <= 0:
            raise ValueError("nbuckets %g > 0 required" % nbuckets)
        self.compute_stats()
        n = self.n
        if n == 0:
            return
        print "%d items; mean %.2f; sdev %.2f" % (n, self.mean, self.sdev)
        print "-> <stat> min %g; median %g; max %g" % (self.min,
                                                       self.median,
                                                       self.max)
        pcts = ['%g%% %g' % x for x in self.pct]
        print "-> <stat> percentiles:", '; '.join(pcts)

        lo, hi = self.get_lo_hi()
        if lo > hi:
            return

        # hunit is how many items a * represents.  A * is printed for
        # each hunit items, plus any non-zero fraction thereof.
        self.fill_buckets(nbuckets)
        biggest = max(self.buckets)
        hunit, r = divmod(biggest, WIDTH)
        if r:
            hunit += 1
        print "* =", hunit, "items"

        # We need ndigits decimal digits to display the largest bucket count.
        ndigits = len(str(biggest))

        # Displaying the bucket boundaries is more troublesome.
        bucketwidth = self.get_bucketwidth()
        whole_digits = max(len(str(int(lo))),
                           len(str(int(hi - bucketwidth))))
        frac_digits = 0
        while bucketwidth < 1.0:
            # Incrementing by bucketwidth may not change the last displayed
            # digit, so display one more.
            frac_digits += 1
            bucketwidth *= 10.0
        format = ("%" + str(whole_digits + 1 + frac_digits) + '.' +
                  str(frac_digits) + 'f %' + str(ndigits) + "d")

        bucketwidth = self.get_bucketwidth()
        for i in range(nbuckets):
            n = self.buckets[i]
            print format % (lo + i * bucketwidth, n),
            print '*' * ((n + hunit - 1) // hunit)
