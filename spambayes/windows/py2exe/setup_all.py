# setup_all.py
# A distutils setup script for SpamBayes binaries

import sys, os, glob
sb_top_dir = os.path.abspath(os.path.dirname(os.path.join(__file__, "../../../..")))
sys.path.append(sb_top_dir)
sys.path.append(os.path.join(sb_top_dir, "windows"))
sys.path.append(os.path.join(sb_top_dir, "scripts"))
sys.path.append(os.path.join(sb_top_dir, "Outlook2000"))
sys.path.append(os.path.join(sb_top_dir, "Outlook2000/sandbox"))

# ModuleFinder can't handle runtime changes to __path__, but win32com uses them,
# particularly for people who build from sources.  Hook this in.
try:
    import modulefinder
    import win32com
    for p in win32com.__path__[1:]:
        modulefinder.AddPackagePath("win32com", p)
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
    excludes = "win32ui,pywin,pywin.debugger", # pywin is a package, and still seems to be included.
    includes = "dialogs.resources.dialogs", # Outlook dynamic dialogs
    dll_excludes = ["dapi.dll", "mapi32.dll"],
    lib_dir = "lib",
    typelibs = [
        ('{00062FFF-0000-0000-C000-000000000046}', 0, 9, 0),
        ('{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}', 0, 2, 1),
        ('{AC0714F2-3D04-11D1-AE7D-00A0C90F26F4}', 0, 1, 0),
    ]
)

# These must be the same IDs as in the dialogs.  We really should just extract
# them from our rc scripts.
outlook_bmp_resources = [
    ( 125, os.path.join(sb_top_dir, r"Outlook2000\dialogs\resources\sbwizlogo.bmp")),
    ( 127, os.path.join(sb_top_dir, r"Outlook2000\dialogs\resources\folders.bmp")),
    (1062, os.path.join(sb_top_dir, r"Outlook2000\dialogs\resources\sblogo.bmp")),
    # and these are currently hard-coded in addin.py
    (6000, os.path.join(sb_top_dir, r"Outlook2000\images\recover_ham.bmp")),
    (6001, os.path.join(sb_top_dir, r"Outlook2000\images\delete_as_spam.bmp")),
]

# These are just objects passed to py2exe
outlook_addin = Options(
    modules = ["addin"],
    dest_base = "outlook/spambayes_addin",
    bitmap_resources = outlook_bmp_resources,
    create_exe = False,
)
#outlook_manager = Options(
#    script = os.path.join(sb_top_dir, r"Outlook2000\manager.py"),
#    bitmap_resources = outlook_bmp_resources,
#)
outlook_dump_props = Options(
    script = os.path.join(sb_top_dir, r"Outlook2000\sandbox\dump_props.py"),
    dest_base = "outlook/outlook_dump_props",
)

service = Options(
    dest_base = "proxy/pop3proxy_service",
    modules = ["pop3proxy_service"]
)
sb_server = Options(
    dest_base = "proxy/sb_server",
    script = os.path.join(sb_top_dir, "scripts", "sb_server.py")
)
pop3proxy_tray = Options(
    dest_base = "proxy/pop3proxy_tray",
    script = os.path.join(sb_top_dir, "windows", "pop3proxy_tray.py"),
    icon_resources = [(1000, os.path.join(sb_top_dir, r"windows\resources\sb-started.ico")),
                      (1010, os.path.join(sb_top_dir, r"windows\resources\sb-stopped.ico"))],
)

outlook_doc_files = [
    ["outlook", [os.path.join(sb_top_dir, r"Outlook2000\about.html")]],
    ["outlook/docs", glob.glob(os.path.join(sb_top_dir, r"Outlook2000\docs\*.html"))],
    ["outlook/docs/images", glob.glob(os.path.join(sb_top_dir, r"Outlook2000\docs\images\*.jpg"))],
]

# Default and only distutils command is "py2exe" - save adding it to the
# command line every single time.
if len(sys.argv)==1:
    sys.argv = [sys.argv[0], "py2exe"]

setup(name="SpamBayes",
      packages = ["spambayes.resources"],
      # We implement a COM object.
      com_server=[outlook_addin],
      # A service
      service=[service],
      # console exes for debugging
      console=[sb_server, outlook_dump_props],
      # The taskbar
      windows=[pop3proxy_tray],
      # and the misc data files
      data_files = outlook_doc_files,
)
