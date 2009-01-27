import os
import sys
import errno
import unittest
import time
from urllib import urlopen, urlencode

import sb_test_support
sb_test_support.fix_sys_path()

import sb_server

from spambayes.Options import options
default_shutdown_port = options["html_ui", "port"]

verbose = 0

def call_web_function(url, **kw):
    got = urlopen(url, urlencode(kw)).read()
    # Very simple - just look for tracebacks
    if got.find("Traceback (most recent call last)")>=0:
        print "FAILED calling URL", url
        print got
        raise AssertionError, "Opening URL %s appeared to fail" % (url,)

class Spawner:
    def __init__(self, test_case, spawn_args):
        self.test_case = test_case
        self.spawn_args = spawn_args
        # If the command is a .py file, insert an executable.
        if os.path.splitext(self.spawn_args[0])[1]=='.py':
            self.spawn_args.insert(0, sys.executable)
        self.pid = None
    def _spawn(self, args):
        return os.spawnv(os.P_NOWAIT, self.spawn_args[0], self.spawn_args)
    def start(self):
        raise NotImplementedError
    def stop(self):
        raise NotImplementedError
    def is_running(self):
        if self.pid is None:
            return False
        # damn - we could implement os.waitpid correctly
        # using the win32api - but as at 2.3, you can't check
        # if a pid is still running with os.waitpid
        if sys.platform.startswith("win32"):
            import win32process # sorry, ya gotta have win32all to run tests
            import win32con
            try:
                rc = win32process.GetExitCodeProcess(self.pid)
                result = rc==win32con.STILL_ACTIVE
            except win32process.error:
                result = False
        else:
            try:
                os.waitpid(self.pid, os.WNOHANG)
                result = True
            except os.error, details:
                if details.errno == errno.ECHILD:
                    result = False
                # other exceptions invalid?
                raise
        # Wait a few seconds for the global mutex to catch up
        for i in range(20):
            time.sleep(0.25)
            if result==is_any_sb_server_running():
                break
        # Check the platform agrees (could do xor, but even I wont be able
        # to read it in a few weeks <wink>
        if result:
            self.test_case.failUnless(is_any_sb_server_running(),
                    "My server stopped, but global server mutex held")
        else:
            self.test_case.failUnless(not is_any_sb_server_running(),
                    "My server running, but no global server mutex held")
        return result

class Spawner_sb_server(Spawner):
    def __init__(self, test_case, args, shutdown_port = default_shutdown_port):
        self.shutdown_port = shutdown_port
        f = sb_server.__file__
        if f.endswith(".pyc") or f.endswith(".pyo"):
            f = f[:-1]
        Spawner.__init__(self, test_case, [f]+args)
    def start(self):
        self.test_case.failUnless(not is_any_sb_server_running(),
                                  "Should be no server running")
        if verbose > 1:
            print "Spawning", self.spawn_args
        self.pid = self._spawn(self.spawn_args)
        # wait for it to start - 5 secs, 0.25 per check
        for i in range(20):
            time.sleep(0.25)
            if verbose > 1:
                print "Waiting for start flags: running=%s, global_mutex=%s" \
                       % (self.is_running(), is_any_sb_server_running())
            if self.is_running() and is_any_sb_server_running():
                return
        # gave up waiting.
        self.test_case.fail("sb_server appeared to not start")

    def stop(self):
        # Copied from sb_server.stop()
        # Shutdown as though through the web UI.  This will save the DB, allow
        # any open proxy connections to complete, etc.
        call_web_function('http://localhost:%d/save' % self.shutdown_port,
                          how='Save & shutdown')
        # wait for it to stop - 5 secs, 0.25 per check
        for i in range(20):
            time.sleep(0.25)
            if not self.is_running() and not is_any_sb_server_running():
                # stopped - check the exit code
                temp_pid, rc = os.waitpid(self.pid, 0)
                if rc:
                    self.test_case.fail("sb_server returned exit code %s" % rc)
                return
        # gave up waiting.
        self.test_case.fail("sb_server appeared to not stop")

def is_any_sb_server_running():
    # reach into sb_server internals, as it is authoritative (sometimes <wink>)
    try:
        mutex = sb_server.open_platform_mutex()
        sb_server.close_platform_mutex(mutex)
        return False
    except sb_server.AlreadyRunningException:
        return True

class TestServer(unittest.TestCase):
    def setUp(self):
        self.failUnless(not is_any_sb_server_running(),
                        "Can't do sb_server tests while a server is running "\
                        "(platform mutex held)")
    def tearDown(self):
        # If we cause failure here, we mask the underlying error which left
        # the server running - so just print the warning.
        if is_any_sb_server_running():
            print "WARNING:", self, "completed with the platform mutex held"
    def _start_spawner(self, spawner):
        self.failUnless(not spawner.is_running(),
                        "this spawneer can't be running")
        spawner.start()
        self.failUnless(spawner.is_running(),
                        "this spawner must be running after successful start")
        self.failUnless(is_any_sb_server_running(),
                "Platform mutex not held after starting")
    def _stop_spawner(self, spawner):
        self.failUnless(spawner.is_running(), "must be running to stop")
        self.failUnless(is_any_sb_server_running(),
                "Platform mutex must be held to stop")
        spawner.stop()
        self.failUnless(not spawner.is_running(), "didn't stop after stop")
        self.failUnless(not is_any_sb_server_running(),
                "Platform mutex still held after stop")
    def test_sb_server_default(self):
        # Should be using the default port from the options file.
        from spambayes.Options import options
        port = options["html_ui", "port"]
        s = Spawner_sb_server(self, [])
        self._start_spawner(s)
        self._stop_spawner(s)

    def test_sb_server_ui_port(self):
        # Should be using the default port from the options file.
        s = Spawner_sb_server(self, ["-u8899"], 8899)
        self._start_spawner(s)
        self._stop_spawner(s)

    def test_sb_server_restore(self):
        # Make sure we can do a restore defaults and shutdown without incident.
        from spambayes.Options import options
        port = options["html_ui", "port"]
        s = Spawner_sb_server(self, [], shutdown_port=port)
        self._start_spawner(s)
        # do the reload
        call_web_function('http://localhost:%d/restoredefaults' % port, how='')
        self._stop_spawner(s)

if sys.platform.startswith("win"):
    import win32service # You need win32all to run the tests!
    import win32serviceutil
    import winerror
    service_name = "pop3proxy"

    class TestService(unittest.TestCase):
        def setUp(self):
            try:
                win32serviceutil.QueryServiceStatus(service_name)
            except win32service.error, details:
                if details[0]==winerror.ERROR_SERVICE_DOES_NOT_EXIST:
                    self.was_installed = False
                raise
            else:
                self.was_installed = True
            self.failUnless(not is_any_sb_server_running(),
                            "Can't do service tests while a server is running "\
                            "(platform mutex held)")
        def tearDown(self):
            if is_any_sb_server_running():
                print "WARNING:", self, "completed with the platform mutex held"
        def _start_service(self):
            win32serviceutil.StartService(service_name)
            for i in range(10):
                time.sleep(0.5)
                status = win32serviceutil.QueryServiceStatus(service_name)
                if status[1] == win32service.SERVICE_RUNNING:
                    break
                if verbose > 1:
                    print "Service status is %d - still waiting" % status[1]
            else:
                self.fail("Gave up waiting for service to start")
        def _stop_service(self):
            # StopServiceWithDeps checks the status of each service as it
            # stops it, which is exactly what we want here.
            win32serviceutil.StopServiceWithDeps(service_name)

        def test_simple_startstop(self):
            self._start_service()
            self._stop_service()

        def test_remote_shutdown(self):
            self._start_service()
            # Should be using the default port from the options file.
            from spambayes.Options import options
            port = options["html_ui", "port"]
            call_web_function ('http://localhost:%d/save' % port,
                               how='Save & shutdown')
            # wait for it to stop - 5 secs, 0.25 per check
            for i in range(10):
                time.sleep(0.5)
                status = win32serviceutil.QueryServiceStatus(service_name)
                if status[1] == win32service.SERVICE_STOPPED:
                    break
            else:
                self.fail("Gave up waiting for service to stop")
            self.failUnless(not is_any_sb_server_running(),
                            "Should be no platform mutex held after stopping")

if __name__=='__main__':
    sb_test_support.unittest_main()
