#! /bin/bash

export STUPID_LOG_FILE=/var/tmp/zeospam.log
export LIBDIR=/usr/local/lib/python2.3/site-packages
python2.3 $LIBDIR/ZEO/start.py -U /var/tmp/zeospam /var/tmp/zeospam.fs
