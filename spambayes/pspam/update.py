import getopt
import os
import sys

import ZODB
from ZEO.ClientStorage import ClientStorage

import pspam.database
from pspam.profile import Profile
from pspam.options import options

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


def folder_exists(L, p):
    """Return true folder with path p exists in list L."""
    for f in L:
        if f.path == p:
            return True
    return False

def main(rebuild=False):
    db = pspam.database.open()
    r = db.open().root()

    profile = r.get("profile")
    if profile is None or rebuild:
        # if there is no profile, create it
        profile = r["profile"] = Profile(options.folder_dir)
        get_transaction().commit()

    # check for new folders of training data
    for ham in options.ham_folders:
        p = os.path.join(options.folder_dir, ham)
        if not folder_exists(profile.hams, p):
            profile.add_ham(p)

    for spam in options.spam_folders:
        p = os.path.join(options.folder_dir, spam)
        if not folder_exists(profile.spams, p):
            profile.add_spam(p)
    get_transaction().commit()

    # read new messages from folders
    profile.update()
    get_transaction().commit()

    db.close()

if __name__ == "__main__":
    FORCE_REBUILD = False
    opts, args = getopt.getopt(sys.argv[1:], 'F')
    for k, v in opts:
        if k == '-F':
            FORCE_REBUILD = True

    main(FORCE_REBUILD)
