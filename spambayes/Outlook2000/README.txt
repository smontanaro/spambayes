This directory contains tools for using the classifier with Microsoft
Outlook 2000, 2002, and 2003, courtesy of Sean True and Mark Hammond.  Note
that you need Python's win32com extensions (http://starship.python.net/crew/mhammond)
and you *must* have win32all-149 or later.

Note that running "setup.py install" will *not* install the contents of this
directory into the Python site-packages directory.  You will need to either
copy this directory there yourself, or run it from some other appropriate
location.  The plug-in will probably not be happy if you change the location
of the source files after it is installed (do an uninstall, then a reinstall).

See below for a list of known problems.

Outlook Addin
==========
If you execute "addin.py", the Microsoft Outlook plugin will be installed.
Next time outlook is started, you should see a "SpamBayes" drop-down
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
above) please send it to spambayes@python.org.

To unregister the addin, execute "addin.py --unregister", then optionally
remove the source files.  Note that as for the binary version, there is a
bug that the toolbar items will remain after an uninstall - see the 
troubleshooting guide for information on how to restore it.

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

Known Problems
---------------
* No field is created in Outlook for the Spam Score field.  To create
  the field, go to the field chooser for the folder you are interested
  in, and create a new User Property called "Spam".  Ensure the type
  of the field is "Integer" (the last option), NOT "Number".  This is only
  necessary for you to *see* the score, not for the scoring to work.

* Sean reports bad output saving very large classifiers in training.py.
  Somewhere over 4MB, they seem to stop working.  Mark's hasn't got
  that big yet - 3.8 MB, then he moved to the bsddb database - all with
  no problems.

Misc Comments
===========
Copyright transferred to PSF from Sean D. True and WebReply.com.
Licensed under PSF, see Tim Peters for IANAL interpretation.

Copyright transferred to PSF from Mark Hammond.
Licensed under PSF, see Tim Peters for IANAL interpretation.

Please send all comments, queries, support questions etc to the SpamBayes
mailing list - see http://mail.python.org/mailman/listinfo/spambayes

-- Sean
seant@iname.com
-- Mark
mhammond@skippinet.com.au
