"""HTParser -- parse a .ht file.
"""

import os
import re
import rfc822
from socket import *
from types import StringType



class HTParser(rfc822.Message):
    def __init__(self, filename, default_author=None, default_email=None):
        self.__filename = filename
        self.__fp = fp = open(filename)
        self.__extraheaders = {}
        rfc822.Message.__init__(self, fp)
        # Massage some standard headers we require.
        #
        # title
        if not self.has_key('title'):
            parts = self.__filename.split(os.sep)
            self.__extraheaders['title'] = parts[-1]
        # author
        if not self.has_key('author'):
            if default_author is not None:
                author = default_author
            else:
                domainname = None
                h, a, ip = gethostbyaddr(gethostbyname(gethostname()))
                for host in [h] + a:
                    i = host.find('.')
                    if i > 0:
                        domainname = host[i+1:]
                        break
                if domainname:
                    author = 'webmaster@' + domainname
                else:
                    author = 'MUST SUPPLY AN AUTHOR'
            self.__extraheaders['author'] = author
        # author email
        if not self.has_key('author-email'):
            if default_email is None:
                default_email = self['author']
            self.__extraheaders['author-email'] = default_email
        # public ivar
        self.sidebar = []

    # override so we can access our own internal dictionary if the message
    # doesn't have it
    def __getitem__(self, item):
        try:
            return rfc822.Message.__getitem__(self, item)
        except KeyError:
            return self.__extraheaders[item]

    # might be using an older rfc822
    def get(self, name, default=None):
        if self.has_key(name):
            return self.getheader(name)
        elif self.__extraheaders.has_key(name):
            return self.__extraheaders[name]
        else:
            return default

    def process_sidebar(self):
        # first process all link files.  Either we hard code the use of
        # ./links.h or we look for a Links: header.  If the header exists, it
        # must explicitly enumerate links.h
        linkfiles = self.get('links', 'links.h')
        for file in linkfiles.split():
            try:
                fp = open(file.strip())
            except IOError:
                continue
            data = fp.read()
            fp.close()
            self.__parse(data)
        # Other-links header specifies more links in-lined
        otherlinks = self.get('other-links')
        if otherlinks:
            self.__parse(otherlinks)
        # always have an email address
        self.sidebar.append('Email Us')
        author = self.get('author')               # guaranteed
        email = self.get('author-email', author)
        self.sidebar.append(('mailto:' + email, author))

    # regular expressions used in massage()
    cre = re.compile(
        r'(<h3>(?P<h3>.*?)</h3>)|'
        r'(<li>(<a href="?(?P<link>[^<>"]*)"?>(?P<contents>[^<>]*)</a>)?)'
        r'(?P<extra>[^\n]*)',
        re.DOTALL | re.IGNORECASE)

    def __parse(self, text):
        """Apply various bits of magic to the links in this list.
        """
        start = 0
        end = len(text)
        while 1:
            mo = self.cre.search(text, start)
            if not mo:
                break
            mstart = mo.start(0)
            h3, link, contents, extra = \
                mo.group('h3', 'link', 'contents', 'extra')
            if link is None:
                link = ''
            if contents is None:
                contents = ''
            if h3:
                self.sidebar.append(h3.strip())
            elif extra:
                L = [s.strip() for s in (link, contents)]
                L.append(extra)
                self.sidebar.append(tuple(L))
            else:
                L = [s.strip() for s in (link, contents)]
                link = tuple(L)
                self.sidebar.append(link)
            start = mo.end(0)
