from Options import options

class CostCounter:
    name = "Superclass Cost"

    def __init__(self):
        self.total = 0

    def spam(self, scr):
        pass

    def ham(self, scr):
        pass

    def __str__(self):
        return "%s: $%.2f" % (self.name, self.total)

class CompositeCostCounter:
    def __init__(self,cclist):
        self.clients = cclist

    def spam(self, scr):
        for c in self.clients:
             c.spam(scr)

    def ham(self, scr):
        for c in self.clients:
            c.ham(scr)

    def __str__(self):
        s = []
        for c in self.clients:
            s.append(str(c))
        return '\n'.join(s)

class StdCostCounter(CostCounter):
    name = "Standard Cost"
    def spam(self, scr):
        if scr < options.ham_cutoff:
            self.total += options.best_cutoff_fn_weight
        elif scr < options.spam_cutoff:
            self.total += options.best_cutoff_unsure_weight

    def ham(self, scr):
        if scr > options.spam_cutoff:
            self.total += options.best_cutoff_fp_weight
        elif scr > options.ham_cutoff:
            self.total += options.best_cutoff_unsure_weight

class FlexCostCounter(CostCounter):
    name = "Flex Cost"
    def _lambda(self, scr):
        if scr < options.ham_cutoff:
	    return 0
        elif scr > options.spam_cutoff:
            return 1
        else:
            return (scr - options.ham_cutoff) / (
                      options.spam_cutoff - options.ham_cutoff)

    def spam(self, scr):
        self.total += self._lambda(scr) * options.best_cutoff_fn_weight

    def ham(self, scr):
        self.total += (1 - self._lambda(scr)) * options.best_cutoff_fp_weight

def default():
     return CompositeCostCounter([
                                  StdCostCounter(),
                                  FlexCostCounter(),
                                 ])

