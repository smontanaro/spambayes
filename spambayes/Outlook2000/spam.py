# Dump Outlook Mail folders into the timcv testing reservoirs
# Author: Sean D. True, WebReply.Com
# October, 2002
# Copyright PSF, license under the PSF license

import os.path, sys, getopt
import re, string
import win32com.client

def findFolder(f,findName, name=""):
    folders = f.Folders
    folder = folders.GetFirst()
    while folder:
        nm = "%s/%s" % (name, folder.Name)
        nm = nm.encode('ascii', 'replace')
        if nm == findName:
            return folder
        try:
            f = findFolder(folder, findName, nm)
            if f:
                return f
        except:
            pass
        folder = folders.GetNext()
    return None

def dumpFolder(rootDir, rootFolder,folderName, isspam):
    if isspam:
        outputDirectory = "Data\\Spam\\reservoir"
    else:
        outputDirectory = "Data\\Ham\\reservoir"
    outputDirectory = "%s\\%s" % (rootDir, outputDirectory)
    f = findFolder(rootFolder, folderName)
    if f == None:
        print "Can't find folder", folderName
        return
    print "dumping folder %s [%s]" % (folderName, f.ID)
    messages = f.Messages
    message = messages.GetFirst()
    n = 0
    while message:
        outfName = os.path.join(outputDirectory, f.Name)
        outfName = "%s_%d.txt" % (outfName, n)
        outfName = string.replace(outfName, " ", "")
        try:
            s = "%s" % message.fields[0x7D001E]
            s = s.encode('ascii', 'replace')
        except:
            message = messages.GetNext()
            continue
        outf = open(outfName, "w")
        outf.write(s)
        outf.write(message.Text.encode('ascii', 'replace'))
        outf.close()
        message = messages.GetNext()
        n=n+1

def usage():
    print "Usage: spam.py --spam=folder,folder,folder --ham=folder,folder,folder"
    print """Example: python spam.py --spam=/JunkMail,/Personal/Hotmail,/Personal/Spam  --ham="/Dragon People,/WebReply,/House,/Tenberry,/Receipts and coupons,/Rational and MIT,/Lists/List-mod_python,/Lists/List-other,/List-Webware,/Microsoft,/Fishing,/Ebusiness,/Colo,/Amazon" """



def main():
    spam = []
    ham = []
    options = ["ham=", "spam="]
    opts,args = getopt.getopt(sys.argv[1:], None, options)
    if args:
        usage()
        sys.exit(1)
    for opt, arg in opts:
        if opt == "--spam": spam = string.split(arg, ',')
        elif opt == "--ham":  ham = string.split(arg,',')
    if not spam and not ham:
        usage()
        sys.exit(1)
    cwd =  os.getcwd()
    session = win32com.client.Dispatch("MAPI.Session")
    session.Logon()
    personalFolders = findFolder(session.GetFolder(''),
                                 '/Top of Personal Folders')
    for folder in spam:
        dumpFolder(cwd, personalFolders, folder, 1)
    for folder in ham:
        dumpFolder(cwd, personalFolders, folder, 0)
    session.Logoff()
    session = None

if __name__ == "__main__":
    main()
