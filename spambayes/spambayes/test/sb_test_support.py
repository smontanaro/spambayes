# General utilities for the SpamBayes test suite
#
#
import sys, os
import unittest

def fix_sys_path():
    # XXX - MarkH had the bright idea *after* writing this that we should
    # ensure the CVS version of SpamBayes is *not* used to resolve SB imports.
    # This would allow us to effectively test the distutils setup script, so
    # any modules or files missing from the installed version raise errors.
    """Fix sys.path so that the core SpamBayes package,
    *and* the SpamBayes scripts can be imported.
    """
    this_dir = os.path.dirname(__file__)
    try:
        import spambayes.Version
    except ImportError:
        # Apparently SpamBayes is yet to be "setup.py install"
        # We are in 'spambayes\spambayes\test' - 2 parents up should
        # do it.
        sb_dir = os.path.abspath(
                     os.path.join(this_dir, "..", ".."))
        sys.path.insert(0, sb_dir)
        import spambayes.Version

    # Now do the same for the sb_* scripts
    try:
        import sb_server
    except ImportError:
        # Scripts are usually in "spambayes/scripts" (for an
        # installed SpamBayes, they appear to be in
        # os.path.join(sys.prefix(), "scripts"), which we may like to
        # leverage - however, these test scripts are not currently
        # installed).
        script_dir = os.path.abspath(
                     os.path.join(this_dir, "..", "..", "scripts"))
        sys.path.insert(0, script_dir)
        import sb_server

# Entry point for all our 'simple' based test programs
def unittest_main(*args, **kwargs):
    # I bet one day this will be more than this <wink>
    unittest.main(*args, **kwargs)
