# configuration stuff we persist via a pickle
# Can't be defined in any module that may be used as "__main__"
# or as a module.
import pprint

class _ConfigurationContainer:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    # Crap state-loading code so when we load an early version of the pickle
    # any attributes in the new version are considered defaults.
    # XXX - I really really want a better scheme than pickles etc here :(
    def _update_from(self, dict):
        for name, val in dict.items():
            updater = getattr(val, "_update_from", None)
            if updater is not None and self.__dict__.has_key(name):
                self.__dict__[name]._update_from(val.__dict__)
            else:
                self.__dict__[name] = val

    def __setstate__(self, state):
        self.__init__() # ensure any new/default values setup
        self._update_from(state)

    def _dump(self, thisname="<root>", level=0):
        import pprint
        prefix = "  " * level
        print "%s%s:" % (prefix, thisname)
        for name, ob in self.__dict__.items():
            d = getattr(ob, "_dump", None)
            if d is None:
                print "%s %s: %s" % (prefix, name, pprint.pformat(ob))
            else:
                d(name, level+1)

class ConfigurationRoot(_ConfigurationContainer):
    def __init__(self):
        self.training = _ConfigurationContainer(
            ham_folder_ids = [],
            ham_include_sub = False,
            spam_folder_ids = [],
            spam_include_sub = False,
            )
        self.classify = _ConfigurationContainer(
            folder_ids = [],
            include_sub = False,
            field_name = "SpamProb",
            )
        self.filter = _ConfigurationContainer(
            folder_ids = [],
            include_sub = False,
            enabled = False,
            )
        self.filter_now = _ConfigurationContainer(
            folder_ids = [],
            include_sub = False,
            only_unread = False,
            )
        self.rules = []

if __name__=='__main__':
    print "Please run 'manager.py'"
