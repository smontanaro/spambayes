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

py2exe_options = dict(
    packages = "spambayes.resources,encodings",
    excludes = "pywin,pywin.debugger", # pywin is a package, and still seems to be included.
    includes = "dialogs.resources.dialogs", # Outlook dynamic dialogs
    dll_excludes = "dapi.dll,mapi32.dll",
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
outlook_addin = dict(
    modules = ["addin"],
    dest_base = "bin/outlook_addin",
    bitmap_resources = outlook_bmp_resources,
    create_exe = False,
)
#outlook_manager = Options(
#    script = os.path.join(sb_top_dir, r"Outlook2000\manager.py"),
#    bitmap_resources = outlook_bmp_resources,
#)
outlook_dump_props = dict(
    script = os.path.join(sb_top_dir, r"Outlook2000\sandbox\dump_props.py"),
    dest_base = "bin/outlook_dump_props",
    icon_resources = [(100,  os.path.join(sb_top_dir,
                                          r"windows\resources\sbicon.ico")),
                     ],
)

# A "register" utility for Outlook.  This should not be necessary, as
# 'regsvr32 dllname' does exactly the same thing.  However, Inno Setup
# version 4 appears to, upon uninstall, do something that prevents the
# files used by the unregister process to be deleted.  Unregistering via
# this EXE solves the problem.
outlook_addin_register = dict(
    script = os.path.join(sb_top_dir, r"Outlook2000\addin.py"),
    dest_base = "bin/outlook_addin_register",
    icon_resources = [(100,  os.path.join(sb_top_dir,
                                          r"windows\resources\sbicon.ico")),
                     ],
)

service = dict(
    dest_base = "bin/sb_service",
    modules = ["pop3proxy_service"],
    icon_resources = [(100,  os.path.join(sb_top_dir,
                                          r"windows\resources\sbicon.ico")),
                     ],
)
sb_server = dict(
    dest_base = "bin/sb_server",
    script = os.path.join(sb_top_dir, "scripts", "sb_server.py")
)
sb_upload = dict(
    dest_base = "bin/sb_upload",
    script = os.path.join(sb_top_dir, "scripts", "sb_upload.py")
)
pop3proxy_tray = dict(
    dest_base = "bin/sb_tray",
    script = os.path.join(sb_top_dir, "windows", "pop3proxy_tray.py"),
    icon_resources = [(100,  os.path.join(sb_top_dir, r"windows\resources\sbicon.ico")),
                      (1000, os.path.join(sb_top_dir, r"windows\resources\sb-started.ico")),
                      (1010, os.path.join(sb_top_dir, r"windows\resources\sb-stopped.ico"))],
)
autoconfigure = dict(
    dest_base = "bin/setup_server",
    script = os.path.join(sb_top_dir, "windows", "autoconfigure.py"),
)

outlook_data_files = [
    ["docs/outlook", [os.path.join(sb_top_dir, r"Outlook2000\about.html")]],
    ["docs/outlook/docs", glob.glob(os.path.join(sb_top_dir, r"Outlook2000\docs\*.html"))],
    ["docs/outlook/docs/images", glob.glob(os.path.join(sb_top_dir, r"Outlook2000\docs\images\*.jpg"))],
    ["bin", [os.path.join(sb_top_dir, r"Outlook2000\default_bayes_customize.ini")]],
]
proxy_data_files = [
    ["docs/sb_server", [os.path.join(sb_top_dir, r"windows\readme_proxy.html")]],
    # note that this includes images that are already in the outlook/docs/images
    # directory - we need to consolidate the documentation (in terms of
    # sharing images, if nothing else)
    ["docs/sb_server/docs/images", glob.glob(os.path.join(sb_top_dir, r"windows\docs\images\*.jpg"))],
]

common_data_files = [
    ["", [os.path.join(sb_top_dir, r"windows\resources\sbicon.ico")]],
]

# Default and only distutils command is "py2exe" - save adding it to the
# command line every single time.
if len(sys.argv)==1 or \
   (len(sys.argv)==2 and sys.argv[1] in ['-q', '-n']):
    sys.argv.append("py2exe")

setup(name="SpamBayes",
      packages = ["spambayes.resources"],
      # We implement a COM object.
      com_server=[outlook_addin],
      # A service
      service=[service],
      # console exes for debugging
      console=[sb_server, sb_upload, outlook_dump_props],
      # The taskbar
      windows=[pop3proxy_tray, outlook_addin_register, autoconfigure],
      # and the misc data files
      data_files = outlook_data_files + proxy_data_files + common_data_files,
      options = {"py2exe" : py2exe_options},
      zipfile = "lib/spambayes.zip",
)
