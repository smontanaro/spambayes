# Dump every property we can find for a MAPI item

from win32com.client import Dispatch, constants
import pythoncom
import os, sys

from win32com.mapi import mapi, mapiutil
from win32com.mapi.mapitags import *

mapi.MAPIInitialize(None)
logonFlags = (mapi.MAPI_NO_MAIL |
              mapi.MAPI_EXTENDED |
              mapi.MAPI_USE_DEFAULT)
session = mapi.MAPILogonEx(0, None, None, logonFlags)

def _FindDefaultMessageStore():
    tab = session.GetMsgStoresTable(0)
    # Restriction for the table:  get rows where PR_DEFAULT_STORE is true.
    # There should be only one.
    restriction = (mapi.RES_PROPERTY,   # a property restriction
                   (mapi.RELOP_EQ,      # check for equality
                    PR_DEFAULT_STORE,   # of the PR_DEFAULT_STORE prop
                    (PR_DEFAULT_STORE, True))) # with True
    rows = mapi.HrQueryAllRows(tab,
                               (PR_ENTRYID,),   # columns to retrieve
                               restriction,     # only these rows
                               None,            # any sort order is fine
                               0)               # any # of results is fine
    # get first entry, a (property_tag, value) pair, for PR_ENTRYID
    row = rows[0]
    eid_tag, eid = row[0]
    # Open the store.
    return session.OpenMsgStore(
                            0,      # no parent window
                            eid,    # msg store to open
                            None,   # IID; accept default IMsgStore
                            # need write access to add score fields
                            mapi.MDB_WRITE |
                                # we won't send or receive email
                                mapi.MDB_NO_MAIL |
                                mapi.MAPI_DEFERRED_ERRORS)

def _FindItemsWithValue(folder, prop_tag, prop_val):
    tab = folder.GetContentsTable(0)
    # Restriction for the table:  get rows where our prop values match
    restriction = (mapi.RES_CONTENT,   # a property restriction
                   (mapi.FL_SUBSTRING | mapi.FL_IGNORECASE | mapi.FL_LOOSE, # fuzz level
                    prop_tag,   # of the given prop
                    (prop_tag, prop_val))) # with given val
    rows = mapi.HrQueryAllRows(tab,
                               (PR_ENTRYID,),   # columns to retrieve
                               restriction,     # only these rows
                               None,            # any sort order is fine
                               0)               # any # of results is fine
    # get entry IDs
    return [row[0][1] for row in rows]
    
def _FindFolderEID(name):
    assert name
    from win32com.mapi import exchange
    if not name.startswith("\\"):
        name = "\\Top Of Personal Folders\\" + name
    store = _FindDefaultMessageStore()
    folder_eid = exchange.HrMAPIFindFolderEx(store, "\\", name)
    return folder_eid

# Also in new versions of mapituil
def GetAllProperties(obj, make_tag_names = True):
	tags = obj.GetPropList(0)
	hr, data = obj.GetProps(tags)
	ret = []
	for tag, val in data:
		if make_tag_names:
			hr, tags, array = obj.GetNamesFromIDs( (tag,) )
			if type(array[0][1])==type(u''):
				name = array[0][1]
			else:
				name = mapiutil.GetPropTagName(tag)
		else:
			name = tag
		ret.append((name, val))
	return ret

def DumpProps(folder_eid, subject, shorten):
    mapi_msgstore = _FindDefaultMessageStore()
    mapi_folder = mapi_msgstore.OpenEntry(folder_eid,
                                          None,
                                          mapi.MAPI_DEFERRED_ERRORS)
    hr, data = mapi_folder.GetProps( (PR_DISPLAY_NAME_A,), 0)
    name = data[0][1]
    print name
    eids = _FindItemsWithValue(mapi_folder, PR_SUBJECT_A, subject)
    print "Folder '%s' has %d items matching '%s'" % (name, len(eids), subject)
    for eid in eids:
        print "Dumping item with ID", mapi.HexFromBin(eid)
        item = mapi_msgstore.OpenEntry(eid,
                                       None,
                                       mapi.MAPI_DEFERRED_ERRORS)
        for prop_name, prop_val in GetAllProperties(item):
            prop_repr = repr(prop_val)
            if shorten:
                prop_repr = prop_repr[:50]
            print "%-20s: %s" % (prop_name, prop_repr)

def usage():
    msg = """\
Usage: %s [-f foldername] subject of the message
-f - Search for the message in the specified folder (default = Inbox)
-s - Shorten long property values.

Dumps all properties for all messages that match the subject.  Subject
matching is substring and ignore-case.

Folder name must be a hierarchical 'path' name, using '\\'
as the path seperator.  If the folder name begins with a
\\, it must be a fully-qualified name, including the message
store name (eg, "Top of Public Folders").  If the path does not
begin with a \\, it is assumed to be fully-qualifed from the root
of the default message store

Eg, python\\python-dev' will locate a python-dev subfolder in a python
subfolder in your default store.
""" % os.path.basename(sys.argv[0])
    print msg


def main():
    import getopt
    try:
        opts, args = getopt.getopt(sys.argv[1:], "f:s")
    except getopt.error, e:
        print e
        print
        usage()
        sys.exit(1)
    folder_name = ""
    subject = " ".join(args)
    if not subject:
        usage()
        sys.exit(1)

    shorten = False
    for opt, opt_val in opts:
        if opt == "-f":
            folder_name = opt_val
        elif opt == "-s":
            shorten = True
        else:
            print "Invalid arg"
            return

    if not folder_name:
        folder_name = "Inbox" # Assume this exists!
        
    eid = _FindFolderEID(folder_name)
    if eid is None:
        print "*** Cant find folder", folder_name
        return
    DumpProps(eid, subject, shorten)

if __name__=='__main__':
    main()
