import math

from Options import options

class Hist:
    """Simple histograms of float values."""

    # Pass None for lo and hi and it will automatically adjust to the min
    # and max values seen.
    # Note:  nbuckets can be passed for backward compatibility.  The
    # display() method can be passed a different nbuckets value.
    def __init__(self, nbuckets=options.nbuckets,  lo=0.0, hi=100.0):
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
    #     var       variance
    #     sdev      population standard deviation (sqrt(variance))
    # self.data is also sorted.
    def compute_stats(self):
        if self.stats_uptodate:
            return
        stats_uptodate = True
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

    # Merge other into self.
    def __iadd__(self, other):
        self.data.extend(other.data)
        self.stats_uptodate = False
        return self

    # Print a histogram to stdout.
    # Also sets instance var nbuckets to the # of buckets, and
    # buckts to a list of nbuckets counts, but only if at least one
    # data point is in the collection.
    def display(self, nbuckets=None, WIDTH=61):
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
        if nbuckets is None:
            nbuckets = self.nbuckets
        self.nbuckets = nbuckets
        self.buckets = buckets = [0] * nbuckets

        lo, hi = self.lo, self.hi
        if lo is None:
            lo = self.min
        if hi is None:
            hi = self.max
        if lo > hi:
            return

        # Compute bucket counts.
        span = float(hi - lo)
        bucketwidth = span / nbuckets
        for x in self.data:
            i = int((x - lo) / bucketwidth)
            if i >= nbuckets:
                i = nbuckets - 1
            elif i < 0:
                i = 0
            buckets[i] += 1

        # hunit is how many items a * represents.  A * is printed for
        # each hunit items, plus any non-zero fraction thereof.
        biggest = max(self.buckets)
        hunit, r = divmod(biggest, WIDTH)
        if r:
            hunit += 1
        print "* =", hunit, "items"

        # We need ndigits decimal digits to display the largest bucket count.
        ndigits = len(str(biggest))

        # Displaying the bucket boundaries is more troublesome.  For now,
        # just print one digit after the decimal point, regardless of what
        # the boundaries look like.
        boundary_digits = max(len(str(int(lo))), len(str(int(hi))))
        format = "%" + str(boundary_digits + 2) + '.1f %' + str(ndigits) + "d"

        for i in range(nbuckets):
            n = self.buckets[i]
            print format % (lo + i * bucketwidth, n),
            print '*' * ((n + hunit - 1) // hunit)
