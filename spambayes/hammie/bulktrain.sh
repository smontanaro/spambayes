#!/bin/bash
cd $HOME/spambayes/active/spambayes
rm -f tmpdb 2>/dev/null
time /usr/bin/python2.2 bulkgraph.py \
 -d tmpdb \
 -e $HOME/Mail/everything/ \
 -s $HOME/Mail/spam \
 -s $HOME/Mail/newspam \
&& mv -f tmpdb hammiedb
ls -l hammiedb
