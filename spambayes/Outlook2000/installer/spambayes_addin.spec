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
extras.append( ("LICENSE.TXT", join(PROJECT_ROOT, "..", "LICENSE.TXT"), 'DATA') )
for fname in glob.glob(PROJECT_ROOT + "/docs/*"):
    if os.path.isfile(fname):
        extras.append( ("docs/"+basename(fname), abspath(fname), 'DATA') )
for fname in glob.glob(PROJECT_ROOT + "/docs/images/*"):
    if os.path.isfile(fname):
        extras.append( ("docs/images/"+basename(fname), abspath(fname), 'DATA') )
# config
extras.append( ("default_bayes_customize.ini", join(PROJECT_ROOT, "default_bayes_customize.ini"), 'DATA') )

excludes = ['dde', 'win32help']

mods = []
mods += [INSTALLER_ROOT+'/support/_mountzlib.py']
mods += [INSTALLER_ROOT+'/support/useUnicode.py']
mods.append('spambayes_addin.py')

a = Analysis(mods,
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

typelibs = [
    ('{00062FFF-0000-0000-C000-000000000046}', 0, 9, 0),
    ('{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}', 0, 2, 1),
    ('{AC0714F2-3D04-11D1-AE7D-00A0C90F26F4}', 0, 1, 0),
]
dll = DLL(pyz,
          a.scripts,
          exclude_binaries=1,
          name='buildspambayes_addin/spambayes_addin.dll',
          debug=debug)
coll = COLLECT(dll,
               a.binaries + extras - [('MAPI32.dll','','')],
               strip=0,
               debug=debug,
               name='dist',
               typelibs=typelibs)
