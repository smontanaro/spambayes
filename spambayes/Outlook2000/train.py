# Train a classifier from Outlook Mail folders
# Author: Sean D. True, WebReply.Com
# October, 2002
# Copyright PSF, license under the PSF license

import sys, os, os.path, getopt, cPickle, string
import win32com.client
import classifier
from tokenizer import tokenize

def findFolder(f,findName, name=""):
    folders = f.Folders
    folder = folders.GetFirst()
    while folder:
        nm = "%s/%s" % (name, folder.Name)
        nm = nm.encode('ascii','replace')
        if nm == findName:
            return folder
        try:
            f = findFolder(folder, findName, nm)
            if f: return f
        except:
            pass
        folder = folders.GetNext()
    return None

def train( bayes, rootFolder,folderName, isspam):
    f = findFolder(rootFolder, folderName)
    if not f:
        print "Can't find folder", folderName
        return
    messages = f.Messages
    if not messages:
        print "Can't find messages in folder", folderName
        return
    message = messages.GetFirst()
    while message:
        try:
            headers = "%s" % message.fields[0x7D001E]
            headers = headers.encode('ascii', 'replace')
            body = message.Text.encode('ascii', 'replace')
            text = headers + body
            bayes.learn(tokenize(text), isspam, False)
        except:
            pass
        message = messages.GetNext()

def usage():
    print "Usage: train.py --bayes=bayes.pck --spam=folder,folder,folder --ham=folder,folder,folder"
    print """Example: python train.py --bayes=bayes.pck --spam=/JunkMail,/Personal/Hotmail,/Personal/Spam  --ham="/Dragon People,/WebReply,/House,/Tenberry,/Receipts and coupons,/Rational and MIT,/Lists/List-mod_python,/Lists/List-other,/List-Webware,/Microsoft,/Fishing,/Ebusiness,/Amazon" """



def main():
    db_name = 'bayes.pck'
    spam = []
    ham = []
    options = ["ham=", "spam=", "bayes="]
    opts,args = getopt.getopt(sys.argv[1:], None, options)
    if args:
        usage()
        sys.exit(1)
    for opt,arg in opts:
        if opt == "--spam": spam = string.split(arg, ',')
        elif opt == "--ham":  ham = string.split(arg,',')
        elif opt == "--bayes":  db_name = arg
    if not spam and not ham:
        usage()
        sys.exit(1)
    cwd =  os.getcwd()
    session = win32com.client.Dispatch("MAPI.Session")
    session.Logon()
    personalFolders = findFolder(session.GetFolder(''),
                                 '/Top of Personal Folders')
    bayes = classifier.Bayes()
    for folder in spam:
        print "Training with %s as spam" % folder
        train(bayes, personalFolders,folder, 1)
    for folder in ham:
        print "Training with %s as ham" % folder
        train(bayes, personalFolders,folder, 0)
    session.Logoff()
    session = None
    print 'Updating probabilities...'
    bayes.update_probabilities()
    print ("Done with training %s, built with %d examples and %d counter "
           "examples" % (db_name, bayes.nspam, bayes.nham))
    db_name = os.path.join(cwd, db_name)
    print 'Writing DB...'
    cPickle.dump(bayes, open(db_name,"wb"), 1)

if __name__ == "__main__":
    main()
