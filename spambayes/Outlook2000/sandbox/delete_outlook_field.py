# Do the best we can to completely obliterate a field from Outlook!

from win32com.client import Dispatch, constants
import pythoncom
import os, sys

from win32com.mapi import mapi
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

def _FindFolderEID(name):
    from win32com.mapi import exchange
    if not name.startswith("\\"):
        name = "\\Top Of Personal Folders\\" + name
    store = _FindDefaultMessageStore()
    folder_eid = exchange.HrMAPIFindFolderEx(store, "\\", name)
    return mapi.HexFromBin(folder_eid)

def DeleteField(folder, name):
    name = name.lower()
    entries = folder.Items
    num_outlook = num_mapi = 0
    entry = entries.GetFirst()
    while entry is not None:
        up = entry.UserProperties
        num_props = up.Count
        for i in range(num_props):
            if up[i+1].Name.lower()==name:
                num_outlook += 1
                entry.UserProperties.Remove(i+1)
                entry.Save()
                break
        entry = entries.GetNext()
    # OK - now try and wipe the field using MAPI.
    mapi_msgstore = _FindDefaultMessageStore()
    mapi_folder = mapi_msgstore.OpenEntry(mapi.BinFromHex(folder.EntryID),
                                          None,
                                          mapi.MAPI_MODIFY | mapi.MAPI_DEFERRED_ERRORS)

    table = mapi_folder.GetContentsTable(0)
    prop_ids = PR_ENTRYID,
    table.SetColumns(prop_ids, 0)
    propIds = mapi_folder.GetIDsFromNames(((mapi.PS_PUBLIC_STRINGS,name),), 0)
    del_from_folder = False
    if PROP_TYPE(propIds[0])!=PT_ERROR:
        assert propIds[0] == PROP_TAG( PT_UNSPECIFIED, PROP_ID(propIds[0]))
        while 1:
            # Getting 70 at a time was the random number that gave best
            # perf for me ;)
            rows = table.QueryRows(70, 0)
            if len(rows) == 0:
                break
            for row in rows:
                eid = row[0][1]
                item = mapi_msgstore.OpenEntry(eid, None, mapi.MAPI_MODIFY | mapi.MAPI_DEFERRED_ERRORS)
                # DeleteProps always says"success" - so check to see if it
                # actually exists just so we can count it.
                hr, vals = item.GetProps(propIds)
                if hr==0: # We actually have it
                    hr, probs = item.DeleteProps(propIds)
                    if  hr == 0:
                        item.SaveChanges(mapi.MAPI_DEFERRED_ERRORS)
                        num_mapi += 1
        hr, vals = mapi_folder.GetProps(propIds)
        if hr==0: # We actually have it
            hr, probs = mapi_folder.DeleteProps(propIds)
            if  hr == 0:
                mapi_folder.SaveChanges(mapi.MAPI_DEFERRED_ERRORS)
                del_from_folder = True
    return num_outlook, num_mapi, del_from_folder

def CountFields(folder):
    fields = {}
    entries = folder.Items

    entry = entries.GetFirst()
    while entry is not None:
        ups = entry.UserProperties
        num_props = ups.Count
        for i in range(num_props):
            name = ups.Item(i+1).Name
            fields[name] = fields.get(name, 0)+1
        entry = entries.GetNext()
    for name, num in fields.items():
        print name, num

def ShowFields(folder, field_name):
    field_name = field_name.lower()
    entries = folder.Items
    entry = entries.GetFirst()
    while entry is not None:
        ups = entry.UserProperties
        num_props = ups.Count
        for i in range(num_props):
            up = ups[i+1]
            name = up.Name
            if name.lower()==field_name:
                subject = entry.Subject.encode("mbcs", "replace")
                print "%s: %s (%d)" % (subject, up.Value, up.Type)
        entry = entries.GetNext()

def usage():
    msg = """\
Usage: %s [-f foldername] [-f foldername] [-d] [-s] [FieldName ...]
-f - Run over the specified folders (default = Inbox)
-d - Delete the named fields
-s - Show message subject and field value for all messages with field
If no options given, prints a summary of field names in the folders

Folder name must be a hierarchical 'path' name, using '\\'
as the path seperator.  If the folder name begins with a
\\, it must be a fully-qualified name, including the message
store name (eg, "Top of Public Folders").  If the path does not
begin with a \\, it is assumed to be fully-qualifed from the root
of the default message store

Eg, 'python\\python-dev' will locate a python-dev subfolder in a python
subfolder in your default store.
""" % os.path.basename(sys.argv[0])
    print msg


def main():
    import getopt
    try:
        opts, args = getopt.getopt(sys.argv[1:], "dsf:")
    except getopt.error, e:
        print e
        print
        usage()
        sys.exit(1)
    delete = show = False
    folder_names = []
    for opt, opt_val in opts:
        if opt == "-d":
            delete = True
        elif opt == "-s":
            show = True
        elif opt == "-f":
            folder_names.append(opt_val)
        else:
            print "Invalid arg"
            return

    if not folder_names:
        folder_names = ["Inbox"] # Assume this exists!
    app = Dispatch("Outlook.Application")
    if not args:
        print "No args specified - dumping all unique UserProperty names,"
        print "and the count of messages they appear in"
    for folder_name in folder_names:
        eid = _FindFolderEID(folder_name)
        if eid is None:
            print "*** Cant find folder", folder_name
            continue
        folder = app.Session.GetFolderFromID(eid)
        print "Processing folder", folder.Name.encode("mbcs", "replace")
        if not args:
            CountFields(folder)
            continue
        for field_name in args:
            if show:
                ShowFields(folder, field_name)
            if delete:
                print "Deleting field", field_name
                num_ol, num_mapi, did_folder = DeleteField(folder, field_name)
                print "Deleted", num_ol, "field instances from Outlook"
                print "Deleted", num_mapi, "field instances via MAPI"
                if did_folder:
                    print "Deleted property from folder"
                else:
                    print "Could not find property to delete in the folder"

##        item = folder.Items.Add()
##        props = item.UserProperties
##        prop=props.Add("TestInt",3 , True, 1)
##        prop.Value=66
##        item.Save()

if __name__=='__main__':
    main()
