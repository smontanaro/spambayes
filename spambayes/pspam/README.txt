pspam: persistent spambayes filtering system
--------------------------------------------

pspam uses a POP proxy to score incoming messages, a set of VM folders
to manage training data, and a ZODB database to manage data used by
the various applications.

The current code only works with a patched version of classifier.py.
Remove the object base class & change the class used to create new
WordInfo objects.

This directory contains:

pspam -- a Python package
pop.py -- a POP proxy based on SocketServer
scoremsg.py -- prints the evidence for a single message read from stdin
update.py -- a script to update training data from folders
vmspam.ini -- a sample configuration file
zeo.sh -- a script to start a ZEO server
zeo.bat -- a script to start a ZEO server on Windows

The code depends on ZODB3, which you can download from
http://www.zope.org/Products/StandaloneZODB.


