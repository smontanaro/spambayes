This directory contains tools for using the classifier with Microsoft
Outlook 2000, courtesy of Sean True and Mark Hammond.  Note that you need 
Python's win32com extensions (http://starship.python.net/crew/mhammond)

** NOTE ** - You also need CDO installed.  This comes with Outlook 2k, but is
not installed by default.  You may need to find your Office 2000 CD, select
Add/Remove components, and find CDO under Outlook.  If you see a COM error
compaining about "MAPI.Session", this is your problem.

train.py
    Train a classifier from Outlook Mail folders.

filter.py
    Moves and modifies msgs among Outlook Mail folders, based on classifier 
    score.

classify.py
    Creates a field in each message with the classifier score.  Once run, 
    the Outlook Field Chooser can be used to display, sort etc the field,
    or used to change formatting of these messages.  The field will appear
    in "user defined fields"
    
Comments from Sean:

This code is extremely rudimentary.

I am getting bad output saving very large classifiers in training.py.
Somewhere over 4MB, they seem to stop working.

Outlook will occasionally complain that folders are corrupted after running
filter.  Closing and reopening Outlook always seems to restore things,
with no fuss.  Your mileage may vary.  Buyer beware.  Worth what you paid.
(Mark hasn't seen this)

Copyright transferred to PSF from Sean D. True and WebReply.com.
Licensed under PSF, see Tim Peters for IANAL interpretation.

Copyright transferred to PSF from Mark Hammond.
Licensed under PSF, see Tim Peters for IANAL interpretation.

Ask me technical questions, and if your mail doesn't get eaten by a broken
spam filter, I'll try to help.
-- Sean
seant@iname.com

Ask Sean all the technical questions <wink>
-- Mark
mhammond@skippinet.com.au
