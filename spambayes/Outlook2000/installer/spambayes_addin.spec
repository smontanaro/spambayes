#
# Specification file for Installer to construct an installable version of
# the Spambayes Outlook Addin
#
from os.path import basename, abspath, join

debug = 0

INSTALLER_ROOT = HOMEPATH
PROJECT_ROOT=".."

# Extra files we need - docs, images, etc.
extras = []
# All files in the image directory.
import glob
for fname in glob.glob(PROJECT_ROOT + "/images/*"):
    if os.path.isfile(fname):
        extras.append( ("images/"+basename(fname), abspath(fname), 'DATA') )
# docs
extras.append( ("about.html", join(PROJECT_ROOT, "about.html"), 'DATA') )
# config
extras.append( ("default_bayes_customize.ini", join(PROJECT_ROOT, "default_bayes_customize.ini"), 'DATA') )

excludes = ['timer', 'dde', 'win32help']

a = Analysis([INSTALLER_ROOT+'/support/_mountzlib.py',
              INSTALLER_ROOT+'/support/useUnicode.py',
              'spambayes_addin.py'],
             excludes = excludes, 
             pathex=[PROJECT_ROOT,os.path.join(PROJECT_ROOT, '..')])
pyz = PYZ(a.pure)
#exe = EXE(pyz,
#          a.scripts,
#          exclude_binaries=1,
#          name='buildspambayes_addin/spambayes_addin.exe',
#          debug=0,
#          strip=0,
#          console=0 )

dll = DLL(pyz,
          a.scripts,
          exclude_binaries=1,
          name='buildspambayes_addin/spambayes_addin.dll',
          debug=debug)
coll = COLLECT(dll,
               a.binaries + extras - [('MAPI32.dll','','')],
               strip=0,
               debug=debug,
               name='dist')
