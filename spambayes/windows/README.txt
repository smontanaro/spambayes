This directory contains Windows specific functions for the spambayes project.

Currently this contains:
* Windows Service version of the pop3 proxy
* The beginnings of a script to automatically configure SpamBayes and
  the user's mail client.
* A GUI 'tray' application to control SpamBayes (service or proxy).
* Inno setup installer for sb_server, Outlook and a few tools.

If you have the latest version of py2exe, you can build the binary installer
as follows:

1. Run "python setup_all.py" in the py2exe directory in this directory.
2. Run the Inno Setup "spambayes.iss" script in this directory.
