This directory contains tools for using the classifier with Microsoft
Outlook 2000, courtesy of Sean True and Mark Hammond.  Note that you need 
Python's win32com extensions (http://starship.python.net/crew/mhammond) and
to run the Outlook Addin you *must* have win32all-149 or later.

CDO is no longer needed :)

Outlook Addin
==========
If you execute "addin.py", the Microsoft Outlook plugin will be installed.
Next time outlook is started, you should see a "Anti-Spam" drop-down
on the toolbar.  Clicking it will allow you to maintain your bayes database
and filters.

All functionality in this package can be accessed from this plugin. This
directory contains a number of other files (see below) which can be
used to access features of the bayes database and filters from outside
of the Outlook environment.  Either way, the functionality is the same (except
filtering of new mail obviously only works in the Outlook environment)

To see any output from the addin (eg, Python print statements) you can either
select "Tools->Trace Collector Debugging Tool" from inside Pythonwin, or just
execute win32traceutil.py (from the win32all extensions) from a Command 
Prompt.

NOTE: If the addin fails to load, Outlook will automatically disable it
for the next time Outlook starts.  Re-executing 'addin.py' will ensure
the addin is enabled (you can also locate and enable the addin via the 
labyrinth of Outlook preference dialogs.)  If this happens and you have
the Python exception that caused the failure (via the tracing mentioned 
above) please send it to Mark.

Filtering
--------
When running from Outlook, you can enable filtering for all mail that arrives 
in your Inbox (or any other folder).  Note that Outlook's builtin rules will 
fire before this notification, and if these rules move the message it will
never appear in the inbox (and thus will not get spam-filtered by a simple
Inbox filter).  You can watch as many folders for Spam as you like.

Command Line Tools
-------------------
There are a number of scripts that invoke the same GUI as the
Outlook plugin.

manager.py
    Display the main dialog, which provides access to all other features.

train.py
    Train a classifier from Outlook Mail folders.

filter.py
    Define filters, and allow a bulk-filter to be applied.  (The outlook 
    plugin must be running for filtering of new mail to occur)

Misc Comments
===========
Sean reports bad output saving very large classifiers in training.py.
Somewhere over 4MB, they seem to stop working.  Mark's hasn't got
that big yet - just over 2MB and going strong.

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
