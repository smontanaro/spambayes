# setup_all.py
# A distutils setup script for SpamBayes binaries

import sys, os
sb_top_dir = os.path.abspath(os.path.dirname(os.path.join(__file__, "../../../..")))
sys.path.append(sb_top_dir)
sys.path.append(os.path.join(sb_top_dir, "windows"))
sys.path.append(os.path.join(sb_top_dir, "scripts"))
sys.path.append(os.path.join(sb_top_dir, "Outlook2000"))

# ModuleFinder can't handle runtime changes to __path__, but win32com uses them,
# particularly for people who build from sources.  Hook this in.
try:
    import modulefinder
    import win32com
    for p in win32com.__path__[1:]:
        modulefinder.AddPackagePath("win32com", p)
    # Not sure why this works for "win32com.mapi" for not "win32com.shell"!
    for extra in ["win32com.shell","win32com.mapi"]:
        __import__(extra)
        m = sys.modules[extra]
        for p in m.__path__[1:]:
            modulefinder.AddPackagePath(extra, p)
except ImportError:
    # no build path setup, no worries.
    pass

from distutils.core import setup
import py2exe

class Options:
    def __init__(self, **kw):
        self.__dict__.update(kw)

# py2exe_options is a global name found by py2exe
py2exe_options = Options(
    packages = "spambayes.resources,encodings",
    excludes = "win32ui,pywin,pywin.debugger" # pywin is a package, and still seems to be included.
)

# These are just objects passed to py2exe
com_server = Options(
    modules = ["addin"],
    dest_base = "SpamBayes_Outlook_Addin",
    bitmap_resources = [(1000, os.path.join(sb_top_dir, r"Outlook2000\dialogs\resources\sblogo.bmp"))],
    create_exe = False,
)

service = Options(
    modules = ["pop3proxy_service"]
)
sb_server = Options(
    script = os.path.join(sb_top_dir, "scripts", "sb_server.py")
)
pop3proxy_tray = Options(
    script = os.path.join(sb_top_dir, "windows", "pop3proxy_tray.py"),
    icon_resources = [(1000, os.path.join(sb_top_dir, r"windows\resources\sb-started.ico")),
                      (1010, os.path.join(sb_top_dir, r"windows\resources\sb-stopped.ico"))],
)
# Default and only distutils command is "py2exe" - save adding it to the
# command line every single time.
if len(sys.argv)==1:
    sys.argv = [sys.argv[0], "py2exe"]

setup(name="SpamBayes",
      packages = ["spambayes.resources"],
      # We implement a COM object.
      com_server=[com_server],
      # A service
      service=[service],
      # A console exe for debugging
      console=[sb_server],
      # The taskbar
      windows=[pop3proxy_tray],
)
