# Run the sb_server as a WinNT service.  Should work on Windows 2000
# and Windows XP.
#
# * Install as a service using "pop3proxy_service.py install"
# * Start the service (Use Control Panel etc, or
#   "pop3proxy_service.py start".  Check the event
#   log should anything go wrong.
# * To debug the service: "pop3proxy_service.py debug"
#   Service then runs in the command prompt, showing all
#   print statements.
# * To remove the service: "pop3proxy_service.py remove"

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

# Originally written by Mark Hammond.

import sys, os

# Messages from pop3proxy will go nowhere when executed as a service
# Try and detect that print will go nowhere and redirect.
# redirect output somewhere useful when running as a service.
import win32api
try:
    win32api.GetConsoleTitle()
except win32api.error:
    # No console - if we are running from Python sources,
    # redirect to win32traceutil, but if running from a binary
    # install, redirect to a log file.
    # Want to move to logging module later, so for now, we
    # hack together a simple logging strategy.
    if hasattr(sys, "frozen"):
        temp_dir = win32api.GetTempPath()
        for i in range(3,0,-1):
            try: os.unlink(os.path.join(temp_dir, "SpamBayesService%d.log" % (i+1)))
            except os.error: pass
            try:
                os.rename(
                    os.path.join(temp_dir, "SpamBayesService%d.log" % i),
                    os.path.join(temp_dir, "SpamBayesService%d.log" % (i+1))
                    )
            except os.error: pass
        # Open this log, as unbuffered so crashes still get written.
        sys.stdout = open(os.path.join(temp_dir,"SpamBayesService1.log"), "wt", 0)
        sys.stderr = sys.stdout
    else:
        import win32traceutil

# If running from sources, patch up sys.path
if not hasattr(sys, "frozen"):
    # We are in the 'spambayes\win32' directory.  We
    # need the parent on sys.path, so 'spambayes.spambayes' is a package,
    # and 'pop3proxy' is a module
    try:
        # module imported by service manager, or 2.3 (in which __main__
        # exists, *and* sys.argv[0] is always already absolute)
        this_filename=__file__
    except NameError:
        this_filename = sys.argv[0]
    if not os.path.isabs(sys.argv[0]):
        # Python 2.3 __main__
        # patch up sys.argv, as our cwd will confuse service registration code
        sys.argv[0] = os.path.abspath(sys.argv[0])
        this_filename = sys.argv[0]

    sb_dir = os.path.dirname(os.path.dirname(this_filename))
    sb_scripts_dir = os.path.join(sb_dir,"scripts")
    
    sys.path.insert(0, sb_dir)
    sys.path.insert(-1, sb_scripts_dir)
    # and change directory here, so pop3proxy uses the default
    # config file etc
    os.chdir(sb_dir)

# Rest of the standard Python modules we use.
import traceback
import threading
import cStringIO

# The spambayes imports we need.
import sb_server

# The win32 specific modules.
import win32serviceutil, win32service
import pywintypes, win32con, winerror
from ntsecuritycon import *

class Service(win32serviceutil.ServiceFramework):
    # The script name was changed to "sb_server" but I'll leave this as pop3proxy
    # overwise people might accidently run two proxies.
    _svc_name_ = "pop3proxy"
    _svc_display_name_ = "SpamBayes Service"
    _svc_deps_ =  ['tcpip'] # We depend on the tcpip service.
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.event_stopped = threading.Event()
        self.event_stopping = threading.Event()
        self.thread = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.event_stopping.set()
        sb_server.stop(sb_server.state)        

    def SvcDoRun(self):
        # Setup our state etc
        sb_server.prepare(state=sb_server.state)
        assert not sb_server.state.launchUI, "Service can't launch a UI"

        # Start the thread running the server.
        thread = threading.Thread(target=self.ServerThread)
        thread.start()

        # Write an event log record - in debug mode we will also 
        # see this message printed.
        from spambayes.Options import optionsPathname
        extra = " as user '%s', using config file '%s'" \
                % (win32api.GetUserNameEx(2).encode("mbcs"),
                   optionsPathname)
        import servicemanager
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, extra)
            )

        try:
            # Thread running - wait for the stopping event.
            self.event_stopping.wait()
            # Either user requested stop, or thread done - wait for it
            # to actually stop, but reporting we are still alive.
            # Wait up to 60 seconds for shutdown before giving up and
            # exiting uncleanly - we wait for current proxy connections
            # to close, but you have to draw the line somewhere.
            for i in range(60):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                self.event_stopped.wait(1)
                if self.event_stopped.isSet():
                    break
                print "The service is still shutting down..."
            else:
                # eeek - we timed out - give up in disgust.
                print "The worker failed to stop - aborting it anyway"
        except KeyboardInterrupt:
            pass
        
        # Write another event log record.
        s = sb_server.state
        status = " after %d sessions (%d ham, %d spam, %d unsure)" % \
                (s.totalSessions, s.numHams, s.numSpams, s.numUnsure)

        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, status)
            )

    def ServerThread(self):
        try:
            try:
                sb_server.start(sb_server.state)
            except SystemExit:
                # user requested shutdown
                print "pop3proxy service shutting down due to user request"
            except:
                # Otherwise an error we should log.
                ob = cStringIO.StringIO()
                traceback.print_exc(file=ob)

                message = "The pop3proxy service failed with an " \
                          "unexpected error\r\n\r\n" + ob.getvalue()

                # print it too, so any other log we have gets it.
                print message
                # Log an error event to the event log.
                import servicemanager
                servicemanager.LogErrorMsg(message)
        finally:
            self.event_stopping.set()
            self.event_stopped.set()

if __name__=='__main__':
    win32serviceutil.HandleCommandLine(Service)
