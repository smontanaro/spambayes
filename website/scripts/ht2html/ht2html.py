#! /usr/bin/env python

"""Generate a .html file from a .ht template.

Usage: %(program)s [options] file1 [file2 [...]]

Where options are:

    --rootdir <directory>
    -r <directory>
        Specify the root of the Web page hierarchy.  Otherwise the current
        directory is used.

    --style <classmod>
    -s <classmod>
        specifies the generator `style'.  classmod is both a module name and a
        class name.  The module is imported (so it must be findable on your
        sys.path) and the class is dug out of that module (so they must have
        the same name).  This class is instantiated by passing the following
        arguments:

            file     -- the .ht file to be parsed
            rootdir  -- as specified above
            relthis  -- the directory path to get from rootdir to the current
                        directory.  Note that rootdir must be a direct parent
                        of the current directory.

        file should be passed to HTParser to create an instance of the file
        parser.  Your class should also create a LinkFixer using (the .html
        version of) file, rootdir, and relthis.

    --backup
    -b
        Make a backup of any existing .html if it would get overwritten.

    --backupext <ext>
    -x <ext>
        Specify the extension for backup files.  Otherwise .bak is used

    --force
    -f
        Force overwritting of .html file even if the generated file is the
        same.  Otherwise only overwrite .html file if the new one is
        different.

    --version
    -v
        Print the version number of this tool and exit.

    --quiet
    -q
        Be quiet.

    --help
    -h
        print this message and exit.
"""

__version__ = '2.0'

import sys
import os
import getopt
import errno


program = sys.argv[0]
sys.path.insert(0, os.getcwd())



def usage(code, msg=''):
    print __doc__ % globals()
    if msg:
        print msg
    sys.exit(code)



def main():
    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            'hr:s:bx:fqv',
            ['help', 'rootdir=', 'style=', 'backup', 'backupext=',
             'force', 'quiet', 'version'])

    except getopt.error, msg:
        usage(1, msg)

    rootdir = '.'
    classmod = 'StandardGenerator'
    backup = 0
    backupext = '.bak'
    force = 0
    quiet = 0

    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage(0)
        elif opt in ('-v', '--version'):
            print 'ht2html version', __version__
            sys.exit(0)
        elif opt in ('-r', '--rootdir'):
##            rootdir = os.path.expanduser(arg)
##            if rootdir[0] <> '/':
##                rootdir = os.path.join(os.getcwd(), rootdir)
##            rootdir = os.path.normpath(rootdir)
            rootdir = arg
        elif opt in ('-s', '--style'):
            classmod = arg
        elif opt in ('-b', '--backup'):
            backup = 1
        elif opt in ('-x', '--backupext'):
            backupext = arg
        elif opt in ('-f', '--force'):
            force = 1
        elif opt in ('-q', '--quiet'):
            quiet = 1

    # find current dir relative to rootdir
    absroot = os.path.abspath(rootdir)
    curdir = os.path.abspath('.')
    prefix = os.path.commonprefix([absroot, curdir])
    if prefix <> absroot:
        usage(1, 'Root directory must be relative to current directory')
    relthis = curdir[len(prefix)+1:]
    if not relthis:
        relthis = '.'

    # get the generator class
    m = __import__(classmod)
    GenClass = getattr(m, classmod)

    # process all the files on the command line
    for file in args:
        if not quiet:
            print 'Processing %s...' % file
        # get the target filename
        root, ext = os.path.splitext(file)
        htmlfile = root + '.html'
        try:
            g = GenClass(file, rootdir, relthis)
        except IOError, msg:
            print 'The source file is unreadable, skipping:', file
            print msg
            continue
        # deal with backups, first load the original file
        try:
            fp = open(htmlfile)
            data = fp.read()
            fp.close()
            origfound = 1
        except IOError:
            origfound = 0
        newtext = g.makepage()
        if origfound and newtext == data:
            # the file hasn't changed.  only write it if forced to
            if not force:
                continue
        try:
            omask = os.umask(002)
            if origfound and backup:
                fp = open(htmlfile + '.generated', 'w')
                fp.write(newtext)
                fp.close()
                os.rename(htmlfile, htmlfile + backupext)
                os.rename(htmlfile + '.generated', htmlfile)
            else:
                fp = open(htmlfile, 'w')
                fp.write(newtext)
                fp.close()
        except IOError, e:
            if e.errno == errno.EACCES:
                print e
            else:
                raise

if __name__ == '__main__':
    main()
