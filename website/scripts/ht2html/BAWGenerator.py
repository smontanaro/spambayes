"""Generates Barry Warsaw's style.
"""

import os
import time

from Skeleton import Skeleton
from Sidebar import Sidebar, BLANKCELL
from Banner import Banner
from HTParser import HTParser
from LinkFixer import LinkFixer



sitelinks = [
    ('%(rootdir)s/index.html',          'Home'),
    ('%(rootdir)s/software/index.html', 'My Software'),
    ('%(rootdir)s/papers.html',         'My Papers'),
    ('%(rootdir)s/bass/index.html',     'My Basses'),
    ('%(rootdir)s/poems/index.html',    'My Poems'),
    ('%(rootdir)s/max.html',            'Max'),
    ]


class BAWGenerator(Skeleton, Sidebar, Banner):
    def __init__(self, file, rootdir, relthis):
        self.__body = None
        root, ext = os.path.splitext(file)
        html = root + '.html'
        p = self.__parser = HTParser(file, 'Barry A. Warsaw', 'barry@wooz.org')
        f = self.__linkfixer = LinkFixer(html, rootdir, relthis)
        p.process_sidebar()
        p.sidebar.append(BLANKCELL)
        # massage our links
        self.__d = {'rootdir': rootdir}
        self.__linkfixer.massage(p.sidebar, self.__d)
        # tweak
        p.sidebar.append(('http://www.python.org/', '''
<center>
    <img border="0"
         src="%(rootdir)s/images/PythonPoweredSmall.gif"></center>'''
                           % self.__d))
        p.sidebar.append(BLANKCELL)
        copyright = self.__parser.get('copyright', '1996-%d' %
                                      time.localtime()[0])
        p.sidebar.append((None, '&copy; ' + copyright))
        p.sidebar.append((None, 'Barry A. Warsaw'))
        Sidebar.__init__(self, p.sidebar)
        #
        # fix up our site links, no relthis because the site links are
        # relative to the root of my web pages
        #
        sitelink_fixer = LinkFixer(f.myurl(), rootdir)
        sitelink_fixer.massage(sitelinks, self.__d, aboves=1)
        Banner.__init__(self, sitelinks, cols=2)
        # kludge!
        for i in range(len(p.sidebar)-1, -1, -1):
            if p.sidebar[i] == 'Email Us':
                p.sidebar[i] = 'Email me'
                break

    def get_corner(self):
        rootdir = self.__linkfixer.rootdir()
        return '''
<center>
    <a href="%(rootdir)s/index.html">
    <img border="0" src="%(rootdir)s/images/baw.jpg"></a></center>''' \
    % self.__d

    def get_corner_bgcolor(self):
        return 'black'

    def get_banner(self):
        return Banner.get_banner(self)

    def get_title(self):
        return self.__parser.get('title')

    def get_sidebar(self):
        return Sidebar.get_sidebar(self)

    def get_banner_attributes(self):
        return 'CELLSPACING="0" CELLPADDING="0"'

    def get_body(self):
        if self.__body is None:
            self.__body = self.__parser.fp.read()
        return self.__body
