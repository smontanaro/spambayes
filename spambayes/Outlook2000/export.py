# Exports your ham and spam folders to a standard SpamBayes test directory

import sys, os, shutil
from manager import GetManager

files_per_directory = 400
default_directory = "..\\testtools\\Data"

def BuildBuckets(manager):
    store = manager.message_store
    config = manager.config
    num_ham = num_spam = 0
    for folder in store.GetFolderGenerator(config.training.spam_folder_ids, config.training.spam_include_sub):
        for msg in folder.GetMessageGenerator():
            num_spam += 1
    for folder in store.GetFolderGenerator(config.training.ham_folder_ids, config.training.ham_include_sub):
        for msg in folder.GetMessageGenerator():
            num_ham += 1
    num_buckets = min(num_ham, num_spam)/ files_per_directory
    dirs = []
    for i in range(num_buckets):
        dirs.append("Set%d" % (i+1,))
    return num_spam, num_ham, dirs

def ChooseBucket(buckets):
    import random
    return random.choice(buckets)

def _export_folders(manager, dir, buckets, folder_ids, include_sub):
    num = 0
    store = manager.message_store
    for folder in store.GetFolderGenerator(folder_ids, include_sub):
        print "", folder.name
        for message in folder.GetMessageGenerator():
            sub = ChooseBucket(buckets)
            this_dir = os.path.join(dir, sub)
            # filename is the EID.txt
            try:
                msg_text = str(message.GetEmailPackageObject())
            except KeyboardInterrupt:
                raise
            except:
                print "Failed to get message text for '%s': %s" \
                      % (message.GetSubject(), sys.exc_info()[1])
                continue

            fname = os.path.join(this_dir, message.GetID()[1]) + ".txt"
            f = open(fname, "w")
            f.write(msg_text)
            f.close()
            num += 1
    return num

def export(directory):
    print "Loading bayes manager..."
    manager = GetManager()
    config = manager.config

    num_spam, num_ham, buckets = BuildBuckets(manager)
    print "Have %d spam, and %d ham to export, spread over %d directories." \
          % (num_spam, num_ham, len(buckets))

    for sub in ["Spam", "Ham"]:
        if os.path.exists(os.path.join(directory, sub)):
            shutil.rmtree(os.path.join(directory, sub))
        for b in buckets:
            d = os.path.join(directory, sub, b)
            os.makedirs(d)

    print "Exporting spam..."
    num = _export_folders(manager, os.path.join(directory, "Spam"), buckets,
                          config.training.spam_folder_ids, config.training.spam_include_sub)
    print "Exported", num, "spam messages."

    print "Exporting ham..."
    num = _export_folders(manager, os.path.join(directory, "Ham"), buckets,
                          config.training.ham_folder_ids, config.training.ham_include_sub)
    print "Exported", num, "ham messages."

def main():
    import getopt
    try:
        opts, args = getopt.getopt(sys.argv[1:], "qn:")
    except getopt.error, d:
        print d
        print
        usage()
    quiet = 0
    for opt, val in opts:
        if opt=='-q':
            quiet = 1
        elif opt=='-n':
            global files_per_directory
            files_per_directory = int(val)

    if len(args) > 1:
        print "Only one directory name can be specified"
        print
        usage()

    if len(args)==0:
        directory = os.path.join(os.path.dirname(sys.argv[0]), default_directory)
    else:
        directory = args[0]

    directory = os.path.abspath(directory)
    print "This program will export your Outlook Ham and Spam folders"
    print "to the directory '%s'" % (directory,)
    if os.path.exists(directory):
        print "*******"
        print "WARNING: all existing files in '%s' will be deleted" % (directory,)
        print "*******"
    if not quiet:
        raw_input("Press enter to continue, or Ctrl+C to abort.")
    export(directory)

def usage():
    print """ \
Usage: %s [-q] [-n min] [directory]

-q : quiet - don't prompt for confirmation.
-n : Minimum number of files to aim for in each directory, default=%d

Export Spam and Ham training folders defined in the Outlook Plugin to a
test directory.  The directory structure is as defined in the parent
README.txt file, in the "Standard Test Data Setup" section.

If 'directory' is not specified, '%s' is assumed.

If 'directory' exists, it will be recursively deleted before
the export (but you will be asked to confirm unless -q is given).""" \
            % (os.path.basename(sys.argv[0]), files_per_directory, default_directory)
    sys.exit(1)

if __name__=='__main__':
    main()
