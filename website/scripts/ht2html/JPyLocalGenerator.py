"""Generates the documentation for the JPython distribution"""

import JPyGenerator

# this is evil
sitelinks = [
    ('http://www.jpython.org/',               'Home'),
    ('http://www.python.org/',                'www.python.org'),
    ('http://www.jpython.org/download.html',  'Download'),
    ('%(rootdir)s/index.html',                'Documentation'),
    ]

JPyGenerator.sitelinks = sitelinks

class JPyLocalGenerator(JPyGenerator.JPyGenerator):
    def __init__(self, file, rootdir, relthis):
        if rootdir == '..':
            rootdir = '.'
        JPyGenerator.JPyGenerator.__init__(self, file, rootdir, relthis)

    def get_corner(self):
        # it is important not to have newlines between the img tag and the end
        # anchor and end center tags, otherwise layout gets messed up
        return '''
<center>
    <a href="http://www.jpython.org/">
    <img border="0" src="%(rootdir)s/images/jpython-new-small.gif"></a></center>''' % \
    self._d
