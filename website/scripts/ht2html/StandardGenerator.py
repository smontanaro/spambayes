"""Standard .ht to .html file generator
"""
import os

from Skeleton import Skeleton
from Sidebar import Sidebar
from HTParser import HTParser
from LinkFixer import LinkFixer


class StandardGenerator(Skeleton, Sidebar):
    def __init__(self, file, rootdir, relthis):
        root, ext = os.path.splitext(file)
        html = root + '.html'
        p = self._parser = HTParser(file)
        self._linkfixer = LinkFixer(html, rootdir, relthis)
        self.__body = None
        p.process_sidebar()
        self._linkfixer.massage(p.sidebar)
        Sidebar.__init__(self, p.sidebar)

    def get_title(self):
        return self._parser.get('title')

    def get_sidebar(self):
        return Sidebar.get_sidebar(self)

    def get_banner(self):
        return None

    def get_corner(self):
        return None

    def get_body(self):
        if self.__body is None:
            self.__body = self._parser.fp.read()
        return self.__body
