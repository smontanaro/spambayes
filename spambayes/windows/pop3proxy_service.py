# Run the pop3proxy as a WinNT service.  Should work on Windows 2000
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
# We are in the 'spambayes\win32' directory.  We
# need the parent on sys.path, so 'spambayes.spambayes' is a package,
# and 'pop3proxy' is a module
try:
    # module imported by service manager, or 2.3 (in which __main__
    # exists, *and* sys.argv[0] is always already absolute)
    this_filename=__file__
except NameError:
    # Python 2.3 __main__
    # patch up sys.argv, as our cwd will confuse service registration code
    sys.argv[0] = os.path.abspath(sys.argv[0])
    this_filename = sys.argv[0]

sb_dir = os.path.dirname(os.path.dirname(this_filename))

sys.path.insert(0, sb_dir)
# and change directory here, so pop3proxy uses the default
# config file etc
os.chdir(sb_dir)

# Rest of the standard Python modules we use.
import traceback
import threading
import cStringIO

# The spambayes imports we need.
import pop3proxy

# The win32 specific modules.
import win32serviceutil, win32service
import pywintypes, win32con, winerror

from ntsecuritycon import *

# Messages from pop3proxy will go nowhere when executed as a service
# Try and detect that print will go nowhere and redirect.
try:
    # redirect output somewhere useful when running as a service.
    import win32api
    try:
        win32api.GetConsoleTitle()
    except win32api.error:
        # no console - import win32traceutil
        import win32traceutil
        print "popproxy service module loading (as user %s)..." \
                % win32api.GetUserName()
except ImportError:
    pass

class Service(win32serviceutil.ServiceFramework):
    _svc_name_ = "pop3proxy"
    _svc_display_name_ = "SpamBayes pop3proxy Service"
    _svc_deps_ =  ['tcpip'] # We depend on the tcpip service.
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.event_stop = threading.Event()
        self.thread = None

    def SvcStop(self):
        pop3proxy.stop(pop3proxy.state)

    def SvcDoRun(self):
        # Setup our state etc
        pop3proxy.prepare(state=pop3proxy.state)
        assert not pop3proxy.state.launchUI, "Service can't launch a UI"

        # Start the thread running the server.
        thread = threading.Thread(target=self.ServerThread)
        thread.start()

        # Write an event log record - in debug mode we will also 
        # see this message printed.
        import servicemanager
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
            )

        # Wait for the stop event.
        try:
            self.event_stop.wait()
        except KeyboardInterrupt:
            pass
        # How do we cleanly shutdown the server?
        
        # Write another event log record.
        s = pop3proxy.state
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
                pop3proxy.start(pop3proxy.state)
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
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.event_stop.set()

if __name__=='__main__':
    win32serviceutil.HandleCommandLine(Service)
