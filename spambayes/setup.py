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


from spambayes import __version__

import distutils.command.install_scripts
parent = distutils.command.install_scripts.install_scripts
class install_scripts(parent):
    old_scripts=[
        'unheader.py',
        'hammie.py',
        'hammiecli.py',
        'hammiesrv.py',
        'hammiefilter.py',
        'pop3proxy.py',
        'smtpproxy.py',
        'proxytee.py',
        'dbExpImp.py',
        'mboxtrain.py',
        'imapfilter.py',
        'notesfilter.py',
        ]

    def run(self):
        err = False
        for s in self.old_scripts:
            s = os.path.join(self.install_dir, s)
            if os.path.exists(s):
                print >> sys.stderr, "Error: old script", s, "still exists."
                err = True
        if err:
            print >>sys.stderr, "Do you want to delete these scripts? (y/n)"
            answer = raw_input("")
            if answer == "y":
                for s in self.old_scripts:
                    s = os.path.join(self.install_dir, s)
                    try:
                        os.remove(s)
                        print "Removed", s
                    except OSError:
                        pass
        return parent.run(self)

setup(
    name='spambayes',
    version = __version__,
    description = "Spam classification system",
    author = "the spambayes project",
    author_email = "spambayes@python.org",
    url = "http://spambayes.sourceforge.net",
    cmdclass = {'build_py': install_scripts},
    scripts=['scripts/sb_client.py',
             'scripts/sb_dbexpimp.py',
             'scripts/sb_filter.py',
             'scripts/sb_imapfilter.py',
             'scripts/sb_mailsort.py',
             'scripts/sb_mboxtrain.py',
             'scripts/sb_notesfilter.py',
             'scripts/sb_pop3dnd.py',
             'scripts/sb_server.py',
             'scripts/sb_smtpproxy.py',
             'scripts/sb_unheader.py',
             'scripts/sb_upload.py',
             'scripts/sb_xmlrpcserver.py',
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
        ],
    )
