This directory contains tools for using the classifier with Microsoft
Outlook 2000, courtesy of Sean True.  Note that you need Python's win32com
extensions.

train.py
    Train a classifier from Outlook Mail folders.

filter.py
    Moves msgs among Outlook Mail folders, based on classifier score.

spam.py
    Dump Outlook Mail folders into the spam reservoir.



Comments from Sean:

This code is extremely rudimentary.

I am getting bad output saving very large classifiers in training.py.
Somewhere over 4MB, they seem to stop working.

Outlook will occasionally complain that folders are corrupted after running
filter.  Closing and reopening Outlook always seems to restore things,
with no fuss.  Your mileage may vary.  Buyer beware.  Worth what you paid.

Brad Morgan comments that in an environment with multiple InfoStores
(message stores?), my simple folder finder does not work.  He uses this
work around:

===============
# This didn't work:
# personalFolders = findFolder(folder, 'Personal Folders')
#
# The following was required:
# (Note: I have two infostores and I've hard-coded the index of
# 'Personal Folders')

infostores = session.InfoStores
print "There are %d infostores" % infostores.Count
infostore = infostores[1]
print "Infostore = ", infostore.Name
personalFolders = infostore.RootFolder
=================

It deserves an option to select the infostore wanted by name.

Enjoy.

Copyright transferred to PSF from Sean D. True and WebReply.com.
Licensed under PSF, see Tim Peters for IANAL interpretation.

Ask me technical questions, and if your mail doesn't get eaten by a broken
spam filter, I'll try to help.


-- Sean
seant@iname.com
