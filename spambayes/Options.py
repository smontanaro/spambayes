# Options.options is a globally shared options object.

# XXX As this code is, option names must be unique across ini sections,
# XXX and must not conflict with OptionsClass method names.

import sys
import StringIO
import ConfigParser
from sets import Set

__all__ = ['buildoptions', 'options']

all_options = {
    'Tokenizer': {'retain_pure_html_tags': ('getboolean', lambda i: bool(i)),
                  'safe_headers': ('get', lambda s: Set(s.split())),
                 },
}

def _warn(msg):
    print >> sys.stderr, msg

class OptionsClass(object):
    def __init__(self):
        self._config = ConfigParser.ConfigParser()

    def mergefiles(self, fnamelist):
        c = self._config
        c.read(fnamelist)

        for section in c.sections():
            if section not in all_options:
                _warn("config file has unknown section %r" % section)
                continue
            goodopts = all_options[section]
            for option in c.options(section):
                if option not in goodopts:
                    _warn("config file has unknown option %r in "
                         "section %r" % (option, section))
                    continue
                fetcher, converter = goodopts[option]
                rawvalue = getattr(c, fetcher)(section, option)
                value = converter(rawvalue)
                setattr(options, option, value)

    def display(self):
        output = StringIO.StringIO()
        self._config.write(output)
        return output.getvalue()


options = OptionsClass()
options.mergefiles(['bayes.ini'])
