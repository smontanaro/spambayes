# setup_all.py
# A distutils setup script for SpamBayes binaries

import sys, os, glob
sb_top_dir = os.path.abspath(os.path.dirname(os.path.join(__file__, "../../../..")))
sys.path.append(sb_top_dir)
sys.path.append(os.path.join(sb_top_dir, "windows"))
sys.path.append(os.path.join(sb_top_dir, "scripts"))
sys.path.append(os.path.join(sb_top_dir, "Outlook2000"))
sys.path.append(os.path.join(sb_top_dir, "Outlook2000", "sandbox"))

import spambayes.resources

# Generate the dialogs.py file.
import dialogs
dialogs.LoadDialogs()

# ModuleFinder can't handle runtime changes to __path__, but win32com uses them,
# particularly for people who build from sources.  Hook this in.
try:
    # py2exe 0.6.4 introduced a replacement modulefinder.
    # This means we have to add package paths there, not to the built-in
    # one.  If this new modulefinder gets integrated into Python, then
    # we might be able to revert this some day.
    try:
        import py2exe.mf as modulefinder
    except ImportError:
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
    packages = "spambayes.resources,encodings,spambayes.languages," \
               "spambayes.languages.es,spambayes.languages.es_AR," \
               "spambayes.languages.fr,spambayes.languages.es.DIALOGS," \
               "spambayes.languages.es_AR.DIALOGS," \
               "spambayes.languages.fr.DIALOGS," \
               "PIL,email",
    excludes = "Tkinter," # side-effect of PIL and markh doesn't have it :)
                "win32ui,pywin,pywin.debugger," # *sob* - these still appear
                # Keep zope out else outlook users lose training.
               "ZODB,ZEO,zope,persistent,BTrees",
    includes = "dialogs.resources.dialogs,weakref," # Outlook dynamic dialogs
               "BmpImagePlugin,JpegImagePlugin", # PIL modules not auto found
    dll_excludes = "dapi.dll,mapi32.dll,powrprof.dll,"
                   "tk84.dll,tcl84.dll", # No Tkinter == no tk/tcl dlls
    typelibs = [
        ('{00062FFF-0000-0000-C000-000000000046}', 0, 9, 0, 'gen_py/outlook-9.py'),
        ('{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}', 0, 2, 1, 'gen_py/office-9.py'),
        ('{AC0714F2-3D04-11D1-AE7D-00A0C90F26F4}', 0, 1, 0, 'gen_py/addin-designer.py'),
    ],
    optimize = 1,
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
# registers "in process", and as Python doesn't completely clean up as its
# DLL is unloaded, we end up with the situation files remain in use.
# Unregistering via this EXE solves the problem.
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
sb_pop3dnd = dict(
    dest_base = "bin/sb_pop3dnd",
    script = os.path.join(sb_top_dir, "scripts", "sb_pop3dnd.py")
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
sb_imapfilter = dict(
    dest_base = "bin/sb_imapfilter",
    script = os.path.join(sb_top_dir, "scripts", "sb_imapfilter.py"),
)
autoconfigure = dict(
    dest_base = "bin/setup_server",
    script = os.path.join(sb_top_dir, "windows", "autoconfigure.py"),
)
convert = dict(
    dest_base = "bin/convert_database",
    script = os.path.join(sb_top_dir, "utilities", "convert_db.py"),
)

outlook_data_files = [
    ["docs/outlook", [os.path.join(sb_top_dir, r"Outlook2000\about.html")]],
    ["docs/outlook/docs", glob.glob(os.path.join(sb_top_dir, r"Outlook2000\docs\*.html"))],
    ["docs/outlook/docs/images", glob.glob(os.path.join(sb_top_dir, r"Outlook2000\docs\images\*.jpg"))],
    ["bin", [os.path.join(sb_top_dir, r"Outlook2000\default_bayes_customize.ini")]],
]
proxy_data_files = [
    ["docs/sb_server", [os.path.join(sb_top_dir, r"windows\readme_proxy.html")]],
    ["docs/sb_server", [os.path.join(sb_top_dir, r"windows\docs\troubleshooting.html")]],
    # note that this includes images that are already in the outlook/docs/images
    # directory - we need to consolidate the documentation (in terms of
    # sharing images, if nothing else)
    ["docs/sb_server/docs/images", glob.glob(os.path.join(sb_top_dir, r"windows\docs\images\*.jpg"))],
]

language_files = []
languages_root = os.path.join(sb_top_dir, "spambayes", "languages")
def add_language_files(current_dir):
    files = os.listdir(current_dir)
    for fn in files:
        full_fn = os.path.join(current_dir, fn)
        if os.path.isdir(full_fn):
            add_language_files(full_fn)
            continue
        if os.path.splitext(fn)[1] == ".mo":
            dest_name = os.path.join("languages", "%s" %
                                     (full_fn[len(languages_root)+1:],))
            language_files.append([os.path.dirname(dest_name), [full_fn]])
add_language_files(languages_root)

common_data_files = [
    ["", [os.path.join(sb_top_dir, r"windows\resources\sbicon.ico")]],
    ["", [os.path.join(sb_top_dir, r"LICENSE.txt")]],
    # We insist gocr.exe is in the 'spambayes' package dir (we can make
    # this smarter as necessary)
    ["bin", [os.path.join(sb_top_dir, "gocr.exe")]],
    # Our .txt file with info on gocr itself.
    ["bin", [os.path.join(sb_top_dir, "windows", "py2exe", "gocr.txt")]],
]

# Default and only distutils command is "py2exe" - save adding it to the
# command line every single time.
if len(sys.argv)==1 or \
   (len(sys.argv)==2 and sys.argv[1] in ['-q', '-n']):
    sys.argv.append("py2exe")

setup(name="SpamBayes",
      packages = ["spambayes.resources"],
      package_dir = {"spambayes.resources" : spambayes.resources.__path__[0]},
      # We implement a COM object.
      com_server=[outlook_addin],
      # A service
      service=[service],
      # console exes
      console=[sb_server, sb_upload, outlook_dump_props, sb_pop3dnd,
               sb_imapfilter, convert],
      # The taskbar
      windows=[pop3proxy_tray, outlook_addin_register, autoconfigure],
      # and the misc data files
      data_files = outlook_data_files + proxy_data_files + \
                   common_data_files + language_files,
      options = {"py2exe" : py2exe_options},
      zipfile = "lib/spambayes.modules",
)
