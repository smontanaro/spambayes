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

# This module is part of the spambayes project, which is Copyright 2002-2007
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

# Originally written by Mark Hammond.

import os
import sys
import logging

import servicemanager
try:
    servicemanager.LogInfoMsg(os.getcwd())
    servicemanager.LogInfoMsg(__file__)
    servicemanager.LogInfoMsg(sys.argv[0])
except:
    pass

class ServiceEventLogHandler(logging.Handler):
    """Dispatches logging events to the win32 services event log.

    Requires pywin32.    
    """
    import servicemanager
    def emit(self, record):
        """Emit a record.

        If a formatter is specified, it is used to format the record.
        This record is then written to the win32 services event log,
        with the type set to the appropriate type based on the level.
        """
        try:
            servicemgr = self.servicemanager
            level = record.levelno
            msg = self.format(record)
            if level >= logging.ERROR:
                servicemgr.LogErrorMsg(msg)
            elif level >= logging.WARNING:
                servicemgr.LogWarningMsg(msg)
            elif level >= logging.INFO:
                servicemgr.LogInfoMsg(msg)
            elif level >= logging.DEBUG:
                # What should we do with this?  It's very low-level
                # to be going into the log, but then it only gets
                # added if the logger's level is set low enough.
                # For now, nothing (absorb), and reconsider this
                # when we are actually using the logging module properly.
                pass
            else:
                # Really low; just absorb these for now.
                pass
        except:
            self.handleError(record)

    def handleError(self, record):
        """
        Handle errors which occur during an emit() call.

        sys.stderr does nowwhere, so redirect this into the event log, too.
        """
        if raiseExceptions:
            try:
                import cStringIO as StringIO
            except ImportError:
                import StringIO
            import traceback
            ei = sys.exc_info()
            msg = StringIO.StringIO()
            traceback.print_exception(ei[0], ei[1], ei[2], None, msg)
            msg.seek(0)
            self.servicemanager.LogErrorMsg(msg)
            del ei


class ServiceEventLogHandlerWrapper(object):
    """Pretend that the ServiceEventLogHandler is a file-like object,
    so we can use it while we don't use the proper logging module."""
    def __init__(self, service_name, level=logging.INFO):
        self.log = ServiceEventLogHandler()
        self.name = service_name
        self.level = level
        self.data = ""
    def write(self, data):
        # This could use the higher-up stuff, but don't for now.
        # Buffer until newline.
        self.data += data
        if '\n' not in data:
            return
        # Skip blank lines
        if not self.data.strip():
            return
        record = logging.LogRecord(self.name, self.level, "", "",
                                   self.data, None, None)
        self.log.emit(record)
        self.data = ""


# Messages from pop3proxy will go nowhere when executed as a service
# Try and detect that print will go nowhere and redirect.
# redirect output somewhere useful when running as a service.
import win32api
try:
    win32api.GetConsoleTitle()
except win32api.error:
    # No console - if we are running from Python sources,
    # redirect to win32traceutil, but if running from a binary
    # install, redirect to the services event log.
    # We used to redirect to log files (in the temp folder, in
    # the form SpamBayesService%d.log), but that is apparently
    # not necessarily a good place, so we moved to the official
    # location.
    # Want to move to logging module later, so for now, we
    # hack together a simple logging strategy.
    if hasattr(sys, "frozen"):
        sys.stdout = ServiceEventLogHandlerWrapper("pop3proxy")
        sys.stderr = ServiceEventLogHandlerWrapper("pop3proxy",
                                                   logging.ERROR)
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
        this_filename = __file__
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
    # and change directory here, so sb_server uses the correct
    # config file etc
    # If the "SpamBayesData" directory that we create exists, change to
    # that, otherwise into the spambayes directory itself.
    if os.path.exists(os.path.join(sb_dir, "SpamBayesData")):
        os.chdir(os.path.join(sb_dir, "SpamBayesData"))
    else:
        os.chdir(sb_dir)

    # Fix to handle problem if there is a zlib.dll in the SYSTEM32 directory.
    # (The Python DLL directory must come before that in sys.path)
    # This is a bit hackish, but shouldn't do any real harm.
    from win32com.shell import shell, shellcon
    sys32path = shell.SHGetFolderPath(0, shellcon.CSIDL_SYSTEM, 0, 0)
    for path in sys.path[:-1]:
        if path == sys32path:
            sys.path.remove(path)
            assert path not in sys.path, \
                   "Please remove multiple copies of windows\system32 in path"
            sys.path.append(path) # put it at the *end*
    del sys32path
    del shell
    del shellcon
    del path

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
        sb_server.stop()

    def SvcDoRun(self):
        import servicemanager
        # Setup our state etc
        try:
            sb_server.prepare(can_stop=False)
        except sb_server.AlreadyRunningException:
            msg = "The SpamBayes proxy service could not be started, as "\
                  "another SpamBayes server is already running on this machine"
            servicemanager.LogErrorMsg(msg)
            errCode = winerror.ERROR_SERVICE_SPECIFIC_ERROR
            self.ReportServiceStatus(win32service.SERVICE_STOPPED,
                                     win32ExitCode=errCode, svcExitCode=1)
            return
        assert not sb_server.state.launchUI, "Service can't launch a UI"

        # Start the thread running the server.
        thread = threading.Thread(target=self.ServerThread)
        thread.start()

        # Write an event log record - in debug mode we will also
        # see this message printed.
        from spambayes.Options import optionsPathname
        extra = " as user '%s', using config file '%s'" \
                % (win32api.GetUserName(),
                   optionsPathname)
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
                sb_server.start()
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
    if "install" in sys.argv:
        # Installing the service also creates a directory (if it does not
        # already exist) in which the data will be placed, unless an
        # existing configuration file can be found.
        from spambayes.Options import optionsPathname
        if not os.path.exists(optionsPathname):
            data_directory = os.path.join(os.path.dirname(sys.argv[0]),
                                          "..", "SpamBayesData")
            data_directory = os.path.abspath(data_directory)
            if not os.path.exists(data_directory):
                print "Creating data directory at", data_directory
                os.makedirs(data_directory)
    win32serviceutil.HandleCommandLine(Service)
