from sets import Set

# Descriptions of options.
# Empty lines, and lines starting with a blank, are ignored.
# A line starting with a non-blank character is of the form:
#     option_name  "default"  default_value
# option_name must not contain whitespace
# default_value must be eval'able.

option_descriptions = """
retain_pure_html_tags   default False
    By default, tokenizer.Tokenizer.tokenize_headers() strips HTML tags
    stripped from pure text/html messages.  Set to True to retain HTML tags
    in this case.

safe_headers  default Set("abuse-reports-to date errors-to from importance in-reply-to message-id mime-version organization received reply-to return-path subject to user-agent x-abuse-info x-complaints-to x-face".split())
    tokenizer.Tokenizer.tokenize_headers() generates tokens just counting
    the number of instances of the headers in this set, in a case-sensitive
    way.  Depending on data collection, some headers aren't safe to count.
    For example, if ham is collected from a mailing list but spam from your
    regular inbox traffic, the presence of a header like List-Info will be a
    very strong ham clue, but a bogus one.
"""

class OptionsClass(dict):
    def __init__(self):
        self.optnames = Set()
        evaldict = {'Set': Set}
        for line in option_descriptions.split('\n'):
            if not line or line.startswith(' '):
                continue
            i = line.index(' ')
            name = line[:i]
            self.optnames.add(name)
            i = line.index(' default ', i)
            self.setopt(name, eval(line[i+9:], evaldict))

    def _checkname(self, name):
        if name not in self.optnames:
            raise KeyError("there's no option named %r" % name)

    def setopt(self, name, value):
        self._checkname(name)
        self[name] = value

    def display(self):
        """Return a string showing current option values."""
        result = ['Option values:\n']
        width = max([len(name) for name in self.keys()])
        items = self.items()
        items.sort()
        for name, value in items:
            result.append('    %-*s: %r\n' % (width, name, value))
        return ''.join(result)

options = OptionsClass()
