# turn the crank
import os, sys, shutil
from compileall import compile_dir

def main():
    installer_dir=os.environ.get("installer")
    if installer_dir is None:
        print "Please set INSTALLER to point to the McMillan installer path"
        return 1

    this_dir = os.path.dirname(__file__)
    if os.path.exists(os.path.join(this_dir, "buildspambayes_addin")):
        shutil.rmtree(os.path.join(this_dir, "buildspambayes_addin"))
    if os.path.exists(os.path.join(this_dir, "dist")):
        shutil.rmtree(os.path.join(this_dir, "dist"))
    rc = os.system("%s %s/Build.py %s/spambayes_addin.spec" % (sys.executable, installer_dir, this_dir))
    if rc:
        print "Installer build FAILED"
        return 1
    genpy = os.path.join(this_dir, "dist", "support", "gen_py")
    # compile_all the gen_path
    if not compile_dir(genpy, ddir="win32com/gen_py", quiet=1):
        print "FAILED to build the gencache directory"
        return 1
    # remove the .py files
    def _remover(arg, dirname, filenames):
        for name in filenames:
            if os.path.splitext(name)[1]=='.py':
                os.remove(os.path.join(dirname, name))
    os.path.walk(genpy, _remover, None)
    if not os.path.isfile(os.path.join(genpy, "dicts.dat")):
        print "EEEK - no gencache .dat file!"
        return 1
    # crank out the installer.
    import win32api
    iss_file = os.path.join(this_dir, "spambayes_addin.iss")
    handle, compiler = win32api.FindExecutable(iss_file)
    rc = os.system('"%s" /cc %s' % (compiler, iss_file))
    if rc:
        print "FAILED to build the final executable"
        return 1
    return 0
    
if __name__=='__main__':
    main()
