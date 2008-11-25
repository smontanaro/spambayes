#! /usr/bin/env python

# This script has a similar interface and purpose to sb_filter, but avoids
# re-initialising spambayes for consecutive requests using a short-lived
# server process. This is intended to give the performance advantages of
# sb_xmlrpcserver, without the administrative complications.
#
# The strategy is:
#
# * while we cant connect to a unix domain socket
#     * fork a separate process that runs in the background
#     * in the child process:
#         * exec sb_bnserver. it listens on that same unix domain socket.
#     * in the parent process:
#         * sleep a little, to give the child chance to start up
# * write the filtering/training command line options to the socket
# * copy the content of stdin to the socket
# * meanwhile..... sb_bnserver gets to work on that data in the same manner
#   as sb_filter. it writes its response back through that socket
# * read a line from the socket containing a success/failure code
# * read a line from the socket containing a byte count
# * copy the remainder of the content of the socket to stdout or stderr,
#   depending on whether it reported success or failure.
# * if the number of bytes read from the socket is different to the byte
#   count, exit with an error
# * if the reported exit code is non-zero, exit with an error
#
# sb_bnfilter will only terminate with a zero exit code if everything
# is ok. If it terminates with a non-zero exit code then its stdout should
# be ignored.
#
# sb_bnserver will close itself and remove its socket after a period of
# inactivity to ensure it does not use up resources indefinitely.
#
# Author: Toby Dickenson
#

"""Usage: %(program)s [options]

Where:
    -h
        show usage and exit
   
*   -f
        filter (default if no processing options are given)
*   -g
        [EXPERIMENTAL] (re)train as a good (ham) message
*   -s
        [EXPERIMENTAL] (re)train as a bad (spam) message
*   -t
        [EXPERIMENTAL] filter and train based on the result -- you must
        make sure to untrain all mistakes later.  Not recommended.
*   -G
        [EXPERIMENTAL] untrain ham (only use if you've already trained
        this message)
*   -S
        [EXPERIMENTAL] untrain spam (only use if you've already trained
        this message)
        
    -k FILE
        Unix domain socket used to communicate with a short-lived server
        process. Default is ~/.sbbnsock-<hostname>

    These options will not take effect when connecting to a preloaded server:

    -p FILE
        use pickle FILE as the persistent store.  loads data from this file
        if it exists, and saves data to this file at the end.
    -d FILE
        use DBM store FILE as the persistent store.
    -o section:option:value
        set [section, option] in the options database to value
    -a seconds
        timeout in seconds between requests before this server terminates
    -A number
        terminate this server after this many requests

"""

import sys, getopt, socket, errno, os, time

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__
    sys.exit(code)
        
def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hfgstGSd:p:o:a:A:k:')
    except getopt.error, msg:
        usage(2, msg)

    # build the default socket filename from environment variables
    filename = os.path.expanduser('~/.sbbnsock-'+socket.gethostname())
    
    action_options = []
    server_options = []
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt in ('-f', '-g', '-s', '-t', '-G', '-S'):
            action_options.append(opt)
        elif opt in ('-d', '-p', '-o', '-a', '-A'):
            server_options.append(opt)
            server_options.append(arg)
        elif opt == '-k':
            filename = arg

    if args:
        usage(2)
        
    server_options.append(filename)
    s = make_socket(server_options, filename)
        
    # We have a connection to the existing shared server
    w_file = s.makefile('w')
    r_file = s.makefile('r')
    # pass our command line on the first line into the socket
    w_file.write(' '.join(action_options)+'\n')
    # copy entire contents of stdin into the socket
    while 1:
        b = sys.stdin.read(1024*64)
        if not b:
            break
        w_file.write(b)
    w_file.flush()
    w_file.close()
    s.shutdown(1)
    # expect to get back a line containing the size of the rest of the response
    error = int(r_file.readline())
    expected_size = int(r_file.readline())
    if error:
        output = sys.stderr
    else:
        output = sys.stdout
    total_size = 0
    # copy entire contents of socket into stdout or stderr
    while 1:
        b = r_file.read(1024*64)
        if not b:
            break
        output.write(b)
        total_size += len(b)
    output.flush()
    # If we didnt receive the right amount then something has gone wrong.
    # exit now, and procmail will ignore everything we have sent to stdout.
    # Note that this policy is different to the xmlrpc client, which
    # tries to handle errors internally by constructing a stdout that is
    # the same as stdin was.
    if total_size != expected_size:
        print >> sys.stderr, 'size mismatch %d != %d' % (total_size,
                                                         expected_size)
        sys.exit(3)
    if error:
        sys.exit(error)

def make_socket(server_options, filename):
    refused_count = 0
    no_server_count = 0
    while 1:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(filename)
        except socket.error,e:
            if e[0] == errno.EAGAIN:
                # baaah
                pass
            elif e[0] == errno.ENOENT or not os.path.exists(filename):
                # We need to check os.path.exists for use on operating
                # systems that never return ENOENT; linux 2.2.
                #
                # no such file.... no such server. create one.
                no_server_count += 1
                if no_server_count > 4:
                    raise
                # Reset refused count to start the sleep process over.
                # Otherwise we run the risk of waiting a *really* long time
                # and/or hitting the refused_count limit.
                refused_count = 0
                fork_server(server_options)
            elif e[0] == errno.ECONNREFUSED:
                # socket file exists but noone listening.
                refused_count += 1
                if refused_count == 4:
                    # We have been waiting ages and still havent been able
                    # to connect. Maybe that socket file has got
                    # orphaned. remove it, wait, and try again. We need to
                    # allow enough time for sb_bnserver to initialise the
                    # rest of spambayes
                    try:
                        os.unlink(filename)
                    except EnvironmentError:
                        pass
                elif refused_count > 6:
                    raise
            else:
                raise # some other problem
            time.sleep(0.2 * 2.0**no_server_count * 2.0**refused_count)
        else:
            return s
                    
def fork_server(options):
    if os.fork():
        # parent
        return
    os.close(0)
    sys.stdin = sys.__stdin__ = open("/dev/null")
    os.close(1)
    sys.stdout = sys.__stdout__ = open("/dev/null", "w")
    # leave stderr
    # os.close(2)
    # sys.stderr = sys.__stderr__ = open("/dev/null", "w")
    os.setsid()
    # Use exec rather than import here because eventually it may be nice to
    # reimplement this one file in C
    os.execv(sys.executable, [sys.executable,
                              os.path.join(os.path.split(sys.argv[0])[0],
                                           'sb_bnserver.py') ]+options)
    # should never get here
    sys._exit(1)
    

if __name__ == "__main__":
    main()
        
