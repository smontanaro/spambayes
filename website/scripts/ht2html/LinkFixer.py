"""LinkFixer class.

Does two things.  Takes as input entry lists as expected by the Sidebar and
Banner classes, and returns a massaged list where any current links are
boldified and turned into non-links.  Also supports global string
interpolation over the links using a dictionary.

"""

import sys
from types import StringType

SLASH = '/'



class LinkFixer:
    def __init__(self, myurl, rootdir='.', relthis='.', verbose=0):
        self.__rootdir = rootdir
        self.__relthis = relthis
        self.__verbose = verbose
        self.msg('rootdir=%s, relthis=%s', rootdir, relthis)
        self.__myurl = self.normalize(myurl)

    def msg(self, fmt, *args):
        if self.__verbose:
            msg = fmt % args
            if msg[-1] <> '\n':
                msg = msg + '\n'
            sys.stdout.write(msg)

    def normalize(self, url):
        self.msg('url= %s', url)
        if url is None:
            return
        if url == './':
            url = 'index.html'
        elif url[-1] == '/':
            url = url + 'index.html'
        absurl = SLASH.join([self.__rootdir, self.__relthis, url])
        # normalize the path, kind of the way os.path.normpath() does.
        # urlparse ought to have something like this...
        parts = []
        for p in absurl.split('/'):
            if p == '.':
                continue
            if p == '..' and len(parts) > 0:
                del parts[-1]
            parts.append(p)
        absurl = SLASH.join(parts)
        self.msg('absurl= %s', absurl)
        return absurl

    def massage(self, links, dict=None, aboves=0):
        """Substitute in situ before massaging.

        With dict, do a dictionary substitution on only the URLs first.  With
        aboves=1, boldify links if they are above myurl.
        """
        for i in range(len(links)):
            item = links[i]
            if type(item) == StringType:
                continue
            if len(item) == 3:
                url, text, extra = item
            else:
                url, text = item
                extra = ''
            try:
                url = url % dict
            except TypeError:
                pass
            if url:
                absurl = self.normalize(url)
            else:
                absurl = None
            self.msg('%s is %s ==? %s', url, absurl, self.__myurl)
            if url is None:
                links[i] = (url, text, extra)
            elif absurl is None:
                links[i] = (absurl, text, extra)
            elif absurl == self.__myurl:
                links[i] = (None, '<b>' + text + '</b>', extra)
            elif aboves and self.above(absurl, self.__myurl):
                links[i] = (url, '<b>' + text + '</b>', extra)
            else:
                links[i] = (url, text, extra)

    def above(self, absurl, myurl):
        """Return true if absurl is above myurl."""
        # Only do one level of checking, and don't match on the root, since
        # that's always going to be above everything else.
        myurl = self.normalize(myurl)
        i = myurl.rfind('/')
        j = absurl.rfind('/')
        if i > 0 and j > 0 and \
           absurl[:j] == myurl[:i] and \
           myurl[i+1:] <> 'index.html':
            return 1
        return 0

    def rootdir(self):
        return self.__rootdir

    def relthis(self):
        return self.__relthis

    def myurl(self):
        return self.__myurl
