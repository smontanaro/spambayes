#! /usr/bin/env python
"""Generates the www.python.org website style
"""

import os
import posixpath
import whrandom

from Skeleton import Skeleton
from Sidebar import Sidebar, BLANKCELL
from Banner import Banner
from HTParser import HTParser
from LinkFixer import LinkFixer



sitelinks = [
    ('http://sourceforge.net/projects/spambayes/',      'SF Project Page'),
    ('http://spambayes.sf.net/faq.html',      'Frequently Asked Questions'),
    ]

class SpamBayesSidebar(Sidebar): pass

class SpamBayesGenerator(Skeleton, SpamBayesSidebar, Banner):
    AUTHOR = 'spambayes@python.org'

    def __init__(self, file, rootdir, relthis):
        root, ext = os.path.splitext(file)
        html = root + '.html'
        p = self.__parser = HTParser(file, self.AUTHOR)
        f = self.__linkfixer = LinkFixer(html, rootdir, relthis)
        self.__body = None
        self.__cont = None
        # calculate the sidebar links, adding a few of our own
        self.__d = {'rootdir': rootdir}
        p.process_sidebar()
        p.sidebar.append(BLANKCELL)
        # it is important not to have newlines between the img tag and the end
        # end center tags, otherwise layout gets messed up
        p.sidebar.append(('http://sourceforge.net', '''
<div align="right">
    <img alt="" border="0"
         src="http://sourceforge.net/sflogo.php?group_id=31674&type=1"></div>
'''))
        self.__linkfixer.massage(p.sidebar, self.__d)
        SpamBayesSidebar.__init__(self, p.sidebar)
        #
        # fix up our site links, no relthis because the site links are
        # relative to the root of our web pages
        #
        sitelink_fixer = LinkFixer(f.myurl(), rootdir)
        sitelink_fixer.massage(sitelinks, self.__d, aboves=1)
        Banner.__init__(self, sitelinks)

    def get_meta(self):
        s1 = Skeleton.get_meta(self)
        s2 = self.__parser.get('meta', '')
        if s1 and s2:
            return s1 + "\n" + s2
        else:
            return s1 or s2

    def get_style(self):
        s1 = Skeleton.get_style(self)
        s2 = self.__parser.get('local-css')
        if s1:
            if s2:
                return s1 + "\n" + s2
            else:
                return s1
        else:
            return s2

    def get_stylesheet(self):
        return posixpath.join(self.__d['rootdir'], 'style.css')

    def get_title(self):
        return self.__parser.get('title')

    def get_sidebar(self):
        if self.__parser.get('wide-page', 'no').lower() == 'yes':
            return None
        return SpamBayesSidebar.get_sidebar(self)

    def get_banner(self):
        return Banner.get_banner(self)

    def get_banner_attributes(self):
        return 'cellspacing="0" cellpadding="0"'

    def get_corner(self):
        # it is important not to have newlines between the img tag and the end
        # anchor and end center tags, otherwise layout gets messed up
        return '''
<center>
    <a href="http://www.student.virginia.edu/~improv/games/findthespam.html">
    <img alt="" border="0" src="%(rootdir)s/images/logo.png"></a></center>''' % \
    self.__d 

    def get_corner_bgcolor(self):
        return "#ffffff"

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

    def getSidebarNormalAttrs(self):
        return 'class="normalSidebar" background="images/gutter.png"'
    def getSidebarHeaderAttrs(self):
        return 'class="headerSidebar" background="images/gutter-hi.png"'

    # python.org color scheme overrides
    def get_lightshade(self):
        "used in sidebar normal items"
        return ''

    def get_mediumshade(self):
        return ''

    def get_darkshade(self):
        "used in sidebar header items"
        return ''

    def get_charset(self):
        return 'iso-8859-1'
