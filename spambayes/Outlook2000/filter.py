# Filter, dump messages to and from Outlook Mail folders
# Author: Sean D. True, WebReply.Com
# October, 2002
# Copyright PSF, license under the PSF license

# Make py2exe happy
import dbhash, anydbm

import sys, os, os.path, cPickle, string, getopt
import win32com.client

import email
import email.Parser
from hammie import createbayes, Hammie
import classifier


def findFolder(f, findName, name=""):
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


from tokenizer import tokenize
def filter(bayes, rootFolder, folderName, targetName=None, over=None,
           under=None, detail=None):
    hammie = Hammie(bayes)
    n = nover = nunder = 0
    f = findFolder(rootFolder, folderName)
    targetf = None
    if targetName:
        targetf = findFolder(rootFolder, targetName)
        if not targetf:
            print "Can't find folder %s to move messages to" % targetName
            return
    messages = f.Messages
    message = messages.GetFirst()
    while message:
        try:
            headers = "%s" % message.fields[0x7D001E]
            headers = headers.encode('ascii', 'replace')
            body = message.Text.encode('ascii', 'replace')
            n = n + 1
        except:
            message = messages.GetNext()
            continue
        text = headers + body
        prob, clues = hammie.score(text, evidence=1)
        if over <> None and prob >= over:
            nover = nover + 1
            if detail:
                print "***Over threshold", prob, over
                for i in range(1, message.recipients.Count+1):
                    print message.Recipients[i].Address,
                print message.Subject.encode('ascii','replace')
                print hammie.formatclues(clues)
            if targetf:
                message.MoveTo(targetf.ID)
        if under <> None and prob <= under:
            nunder = nunder + 1
            if detail:
                print "***Under threshold", prob, under
                for i in range(1, message.recipients.Count+1):
                    print message.Recipients[i].Address,
                print message.Subject.encode('ascii','replace')
                print hammie.formatclues(clues)
            if targetf:
                message.MoveTo(targetf.ID)
        message = messages.GetNext()
    print "Total %d, over %d under %d" % (n, nover, nunder)

def usage():
    print "Usage: filter.py --bayes=bayes.pck --from=folder,folder,folder [--to=folder] [--detail] [--over=float|--under=float]"
    print """Example: python filter.py --from=/Personal/Hotmail,/Personal/ExJunk
--over=.35 --detail --to=/SpamMaybe"""

def main():
    from hammie import createbayes
    db_name = 'bayes.pck'
    folders = []
    options = ["over=", "under=", "bayes=", "to=", "from=", "detail"]
    dodetail=targetName=to=over=under= None
    opts,args = getopt.getopt(sys.argv[1:], None, options)
    if args:
        usage()
        sys.exit(1)
    for opt, arg in opts:
        if opt == "--under": under = float(arg)
        elif opt == "--over":  over = float(arg)
        elif opt == "--bayes":  db_name = arg
        elif opt == "--to": targetName = arg
        elif opt == "--from": folders = string.split(arg, ",")
        elif opt == "--detail": dodetail = 1
    if not (over or under) or not folders:
        usage()
        sys.exit(1)
    bayes = cPickle.load(open(db_name,'rb'))
    cwd =  os.getcwd()
    session = win32com.client.Dispatch("MAPI.Session")
    session.Logon()
    personalFolders = findFolder(session.GetFolder(''),
                                 '/Top of Personal Folders')
    for folder in folders:
        print "Filtering %s, over: %s under %s" % (arg, over, under)
        filter(bayes, personalFolders, folder, targetName, over=over,
               under=under, detail=dodetail)
    session.Logoff()
    session = None
    print 'Done'

if __name__ == "__main__":
    main()
