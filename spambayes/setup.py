#!/usr/bin/env python

import os

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

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

from spambayes import __version__

import distutils.command.install_scripts
parent = distutils.command.install_scripts.install_scripts
class install_scripts(parent):
    old_scripts=[
        'unheader',
        'hammie',
        'hammiecli',
        'hammiesrv',
        'hammiefilter',
        'pop3proxy',
        'smtpproxy',
        'sb_smtpproxy',
        'proxytee',
        'dbExpImp',
        'mboxtrain',
        'imapfilter',
        'notesfilter',
        ]

    def run(self):
        err = False
        for s in self.old_scripts:
            s = os.path.join(self.install_dir, s)
            for e in (".py", ".pyc", ".pyo"):
                if os.path.exists(s+e):
                    print >> sys.stderr, "Error: old script", s+e,
                    print >> sys.stderr, "still exists."
                    err = True
        if err:
            print >>sys.stderr, "Do you want to delete these scripts? (y/n)"
            answer = raw_input("")
            if answer == "y":
                for s in self.old_scripts:
                    s = os.path.join(self.install_dir, s)
                    for e in (".py", ".pyc", ".pyo"):
                        try:
                            os.remove(s+e)
                            print "Removed", s+e
                        except OSError:
                            pass
        return parent.run(self)

scripts=['scripts/sb_client.py',
         'scripts/sb_dbexpimp.py',
         'scripts/sb_evoscore.py',
         'scripts/sb_filter.py',
         'scripts/sb_bnfilter.py',
         'scripts/sb_bnserver.py',
         'scripts/sb_imapfilter.py',
         'scripts/sb_mailsort.py',
         'scripts/sb_mboxtrain.py',
         'scripts/sb_notesfilter.py',
         'scripts/sb_pop3dnd.py',
         'scripts/sb_server.py',
         'scripts/sb_unheader.py',
         'scripts/sb_upload.py',
         'scripts/sb_xmlrpcserver.py',
         'scripts/sb_chkopts.py',
        ]

if sys.platform == 'win32':
    # Also install the pop3proxy_service and pop3proxy_tray scripts.
    # pop3proxy_service is only needed for installation and removal,
    # but pop3proxy_tray needs to be used all the time.  Neither is
    # any use on a non-win32 platform.
    scripts.append('windows/pop3proxy_service.py')
    scripts.append('windows/pop3proxy_tray.py')

setup(
    name='spambayes',
    version = __version__,
    description = "Spam classification system",
    author = "the spambayes project",
    author_email = "spambayes@python.org",
    url = "http://spambayes.sourceforge.net",
    cmdclass = {'install_scripts': install_scripts},
    scripts=scripts,
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
        ],
    )
