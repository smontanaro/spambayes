# setup_all.py
# A distutils setup script for SpamBayes binaries

import sys, os
sb_top_dir = os.path.abspath(os.path.dirname(os.path.join(__file__, "../../../..")))
try:
    import classifier
except ImportError:
    sys.path.append(sb_top_dir)

try:
    import pop3proxy_service
except ImportError:
    sys.path.append(os.path.join(sb_top_dir, "windows"))
    
try:
    import addin
except ImportError:
    sys.path.append(os.path.join(sb_top_dir, "Outlook2000"))

# ModuleFinder can't handle runtime changes to __path__, but win32com uses them,
# particularly for people who build from sources.  Hook this in.
try:
    import modulefinder
    import win32com
    for p in win32com.__path__[1:]:
        modulefinder.AddPackagePath("win32com", p)
    # Not sure why this works for "win32com.mapi" for not "win32com.shell"!
    for extra in ["win32com.shell"]:
        __import__(extra)
        m = sys.modules[extra]
        for p in m.__path__[1:]:
            modulefinder.AddPackagePath(extra, p)
except ImportError:
    # no build path setup, no worries.
    pass

from distutils.core import setup
import py2exe

class py2exe_options:
    bitmap_resources = [(1000, os.path.join(sb_top_dir, r"Outlook2000\dialogs\resources\sblogo.bmp"))]
    packages = "spambayes.resources"
    excludes = "win32ui,pywin" # pywin is a package, and still seems to be included.

# Default and only distutils command is "py2exe" - save adding it to the
# command line every single time.
if len(sys.argv)==1:
    sys.argv = [sys.argv[0], "py2exe"]
   
setup(name="SpamBayes",
      packages = ["spambayes.resources"],
      # We implement a COM object.
      com_server=["addin"],
      # A service
      service=["pop3proxy_service"],
      # A console exe for debugging
      console=[os.path.join(sb_top_dir, "pop3proxy.py")],
)
