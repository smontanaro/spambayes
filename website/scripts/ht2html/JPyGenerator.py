"""Generates the www.jpython.org website style
"""

import os
from Skeleton import Skeleton
from Sidebar import Sidebar, BLANKCELL
from Banner import Banner
from HTParser import HTParser
from LinkFixer import LinkFixer


sitelinks = [
    ('%(rootdir)s/',              'Home'),
    ('http://www.python.org/',    'www.python.org'),
#    ('%(rootdir)s/download/',     'Download'),
    ('%(rootdir)s/download.html', 'Download'),
    ('%(rootdir)s/docs/',         'Documentation'),
#    ('%(rootdir)s/applets/',      'Applet Demos'),
#    (None,                        '&nbsp;&nbsp;'),
    ]


class JPyGenerator(Skeleton, Sidebar, Banner):
    def __init__(self, file, rootdir, relthis):
        root, ext = os.path.splitext(file)
        html = root + '.html'
        p = self.__parser = HTParser(file, 'jpython@python.org')
        f = self.__linkfixer = LinkFixer(html, rootdir, relthis)
        self.__body = None
        self.__cont = None
        # calculate the sidebar links, adding a few of our own
        self._d = {'rootdir': rootdir}
        p.process_sidebar()
        p.sidebar.append(BLANKCELL)
        # it is important not to have newlines between the img tag and the end
        # end center tags, otherwise layout gets messed up
        p.sidebar.append(('http://www.python.org/', '''
<center>
    <img border="0" src="%(rootdir)s/images/PythonPoweredSmall.gif"></center>
''' % self._d))
        self.__linkfixer.massage(p.sidebar, self._d)
        Sidebar.__init__(self, p.sidebar)
        #
        # fix up our site links, no relthis because the site links are
        # relative to the root of our web pages
        #
        sitelink_fixer = LinkFixer(f.myurl(), rootdir)
        sitelink_fixer.massage(sitelinks, self._d, aboves=1)
        Banner.__init__(self, sitelinks, cols=2)

    def get_title(self):
        return self.__parser.get('title')

    def get_sidebar(self):
        if self.__parser.get('wide-page', 'no').lower() == 'yes':
            return None
        return Sidebar.get_sidebar(self)

    def get_banner(self):
        return Banner.get_banner(self)

    def get_corner(self):
        # it is important not to have newlines between the img tag and the end
        # anchor and end center tags, otherwise layout gets messed up
        return '''
<center>
    <a href="%(rootdir)s/">
    <img border="0" src="%(rootdir)s/images/jpython-new-small.gif"></a></center>''' % \
    self._d

    def get_body(self):
        self.__grokbody()
        return self.__body

    def get_cont(self):
        self.__grokbody()
        return self.__cont

    def __grokbody(self):
        if self.__body is None:
            text = self.__parser.fp.read()
            i = text.find('<!--table-stop-->')
            if i >= 0:
                self.__body = text[:i]
                self.__cont = text[i+17:]
            else:
                # there is no wide body
                self.__body = text

    # python.org color scheme overrides
    def get_lightshade(self):
        return '#cdb7b5'

    def get_mediumshade(self):
        return '#9862cb'

    def get_darkshade(self):
        return '#660099'

##    def get_corner_bgcolor(self):
##        return 'white'
