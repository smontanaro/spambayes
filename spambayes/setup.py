#!/usr/bin/env python

import sys
if sys.version < '2.2':
    print "Error: Python version too old. You need at least Python 2.2 to use this package."
    print "(you're running version %s)"%sys.version
    sys.exit(0)

# Install
from distutils.core import setup

import email
if email.__version__ < '2.4.3':
    print "Error: email package version < 2.4.3 found - need newer version"
    print "See INTEGRATION.txt for download information for email package"
    sys.exit(0)

# patch distutils if it can't cope with the "classifiers" keyword.
# this just makes it ignore it.
if sys.version < '2.2.3':
    from distutils.dist import DistributionMetadata
    DistributionMetadata.classifiers = None


from spambayes import __version__

setup(
  name='spambayes',
  version = __version__,
  description = "Spam classification system",
  author = "the spambayes project",
  author_email = "spambayes@python.org",
  url = "http://spambayes.sourceforge.net",
  scripts=['unheader.py',
           'hammie.py',
           'hammiecli.py',
           'hammiesrv.py',
           'hammiefilter.py',
           'pop3proxy.py',
           'proxytee.py',
           'dbExpImp.py',
          ],
        packages = [
           'spambayes',
           'spambayes.resources',
          ],
        classifiers = [
            'Development Status :: 4 - Beta',
            'Environment :: Console',
            'License :: OSI Approved :: Python Software Foundation License',
            'Operating System :: POSIX',
            'Operating System :: MacOS :: MacOS X',
            'Operating System :: Microsoft :: Windows :: Windows 95/98/2000',
            'Operating System :: Microsoft :: Windows :: Windows NT/2000',
            'Programming Language :: Python',
            'Intended Audience :: End Users/Desktop',
            'Topic :: Communications :: Email :: Filters',
            'Topic :: Communications :: Email :: Post-Office :: POP3',
        ]
  )
