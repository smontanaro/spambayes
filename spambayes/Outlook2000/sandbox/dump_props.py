from __future__ import generators
# Dump every property we can find for a MAPI item

import pythoncom
import os, sys

from win32com.mapi import mapi, mapiutil
from win32com.mapi.mapitags import *

import mapi_driver

# Also in new versions of mapituil
def GetAllProperties(obj, make_pretty = True):
    tags = obj.GetPropList(0)
    hr, data = obj.GetProps(tags)
    ret = []
    for tag, val in data:
        if make_pretty:
            hr, tags, array = obj.GetNamesFromIDs( (tag,) )
            if type(array[0][1])==type(u''):
                name = array[0][1]
            else:
                name = mapiutil.GetPropTagName(tag)
            # pretty value transformations
            if PROP_TYPE(tag)==PT_ERROR:
                val = mapiutil.GetScodeString(val)
        else:
            name = tag
        ret.append((name, val))
    return ret

def DumpItemProps(item, shorten):
    for prop_name, prop_val in GetAllProperties(item):
        prop_repr = repr(prop_val)
        if shorten:
            prop_repr = prop_repr[:50]
        print "%-20s: %s" % (prop_name, prop_repr)

def DumpProps(driver, mapi_folder, subject, include_attach, shorten):
    hr, data = mapi_folder.GetProps( (PR_DISPLAY_NAME_A,), 0)
    name = data[0][1]
    for item in driver.GetItemsWithValue(mapi_folder, PR_SUBJECT_A, subject):
        DumpItemProps(item, shorten)
        if include_attach:
            print
            table = item.GetAttachmentTable(0)
            rows = mapi.HrQueryAllRows(table, (PR_ATTACH_NUM,), None, None, 0)
            for row in rows:
                attach_num = row[0][1]
                print "Dumping attachment (PR_ATTACH_NUM=%d)" % (attach_num,)
                attach = item.OpenAttach(attach_num, None, mapi.MAPI_DEFERRED_ERRORS)
                DumpItemProps(attach, shorten)

def usage(driver):
    folder_doc = driver.GetFolderNameDoc()
    msg = """\
Usage: %s [-f foldername] subject of the message
-f - Search for the message in the specified folder (default = Inbox)
-s - Shorten long property values.
-a - Include attachments
-n - Show top-level folder names and exit

Dumps all properties for all messages that match the subject.  Subject
matching is substring and ignore-case.

%s
Use the -n option to see all top-level folder names from all stores.""" \
    % (os.path.basename(sys.argv[0]),folder_doc)
    print msg

def main():
    driver = mapi_driver.MAPIDriver()

    import getopt
    try:
        opts, args = getopt.getopt(sys.argv[1:], "af:sn")
    except getopt.error, e:
        print e
        print
        usage(driver)
        sys.exit(1)
    folder_name = ""

    shorten = False
    include_attach = False
    for opt, opt_val in opts:
        if opt == "-f":
            folder_name = opt_val
        elif opt == "-s":
            shorten = True
        elif opt == "-a":
            include_attach = True
        elif opt == "-n":
            driver.DumpTopLevelFolders()
            sys.exit(1)
        else:
            print "Invalid arg"
            return

    if not folder_name:
        folder_name = "Inbox" # Assume this exists!

    subject = " ".join(args)
    if not subject:
        print "You must specify a subject"
        print
        usage(driver)
        sys.exit(1)

    try:
        folder = driver.FindFolder(folder_name)
    except ValueError, details:
        print details
        sys.exit(1)

    DumpProps(driver, folder, subject, include_attach, shorten)

if __name__=='__main__':
    main()
