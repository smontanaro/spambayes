#! /usr/bin/env python
"""Simple version repository for SpamBayes core, and our main apps.

Also has the ability to load this version information from a remote location
(in that case, we actually load a "ConfigParser" version of the file to
avoid importing code we can't trust.)  This allows any app to check if there
is a later version available.

The makefile process for the website will execute this as a script, which
will generate the "ConfigParser" version for the web.
"""

LATEST_VERSION_HOME="http://www.spambayes.org/download/Version.cfg"

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.
versions = {
    # Non app specific - changed when "spambayes\*" changes significantly
    "Version":          0.2,
    "Description":      "SpamBayes Beta2",
    "Date":             "July 2003",
    "Full Description": "%(Description)s, version %(Version)s (%(Date)s)",
    # Sub-dict for application specific version strings.
    "Apps": {
        "Hammie" : {
            "Version":          0.1,
            "Description":      "SpamBayes command line tool (Hammie) Beta1",
            "Date":             "January 2003",
            "Full Description": "%(Description)s, version %(Version)s (%(Date)s)",
        },
        "Outlook" : {
            "Version":          0.7,
            "BinaryVersion":    0.7,
            "Description":      "SpamBayes Outlook Addin",
            "Date":             "August 9, 2003",
            "Full Description": "%(Description)s, version %(Version)s (%(Date)s)",
            "Full Description Binary":
                                "%(Description)s, Binary version %(BinaryVersion)s (%(Date)s)",
            # Note this means we can change the download page later, and old
            # versions will still go to the new page.
            # We may also like to have a "Release Notes Page" item later?
            "Download Page": "http://starship.python.net/crew/mhammond/spambayes"
        },
        "POP3 Proxy" : {
            "Version":          0.1,
            "Description":      "SpamBayes POP3 Proxy Beta1",
            "Date":             "May 2003",
            "InterfaceVersion":            0.02,
            "InterfaceDescription":        "SpamBayes POP3 Proxy Web Interface Alpha2",
            "Full Description": """%(Description)s, version %(Version)s (%(Date)s),
using %(InterfaceDescription)s, version %(InterfaceVersion)s""",
        },
        "Lotus Notes Filter" : {
            "Version":          0.01,
            "Description":      "SpamBayes Lotus Notes Filter Alpha1",
            "Date":             "March 2003",
            "Full Description": "%(Description)s, version %(Version)s (%(Date)s)",
        },
        "SMTP Proxy" : {
            "Version":          0.01,
            "Description":      "SpamBayes SMTP Proxy Alpha1",
            "Date":             "May 2003",
            "Full Description": "%(Description)s, version %(Version)s (%(Date)s)",
        },
        "IMAP Filter" : {
            "Version":          0.01,
            "Description":      "SpamBayes IMAP Filter Alpha1",
            "Date":             "May 2003",
            "InterfaceVersion":            0.01,
            "InterfaceDescription":        "SpamBayes IMAP Filter Web Interface Alpha1",
            "Full Description": """%(Description)s, version %(Version)s (%(Date)s),
using %(InterfaceDescription)s, version %(InterfaceVersion)s""",
        },
    },
}

def get_version_string(app = None,
                       description_key = "Full Description",
                       version_dict = None):
    """Get a pretty version string, generally just to log or show in a UI"""
    if version_dict is None: version_dict = versions
    if app is None:
        dict = version_dict
    else:
        dict = version_dict["Apps"][app]
    return dict[description_key] % dict

def get_version_number(app = None,
                       version_key = "Version",
                       version_dict = None):
    """Get a version number, as a float.  This would primarily be used so some
    app or extension can determine if we are later than a specific version
    of either the engine or a specific app.
    Maybe YAGNI.
    """
    if version_dict is None: version_dict = versions
    if app is None:
        dict = version_dict
    else:
        dict = version_dict["Apps"][app]
    return dict[version_key]

# Utilities to check the "latest" version of an app.
# Assumes that a 'config' version of this file exists at the given URL
# No exceptions are caught
try:
    import ConfigParser
    class MySafeConfigParser(ConfigParser.SafeConfigParser):
        def optionxform(self, optionstr):
            return optionstr # no lower!
except AttributeError: # No SafeConfigParser!
    MySafeConfigParser = None

def fetch_latest_dict(url=LATEST_VERSION_HOME):
    if MySafeConfigParser is None:
        raise RuntimeError, \
              "Sorry, but only Python 2.3 can trust remote config files"

    import urllib2
    from spambayes.Options import options
    server = options["globals", "proxy_server"]
    if server != "":
        if ':' in server:
            server, port = server.split(':', 1)
        else:
            port = 8080
        username = options["globals", "proxy_username"]
        password = options["globals", "proxy_password"]
        proxy_support = urllib2.ProxyHandler({"http" :
                                              "http://%s:%s@%s:%d" % \
                                              (username, password, server,
                                               port)})
        opener = urllib2.build_opener(proxy_support, urllib2.HTTPHandler)
        urllib2.install_opener(opener)
    stream = urllib2.urlopen(url)
    cfg = MySafeConfigParser()
    cfg.readfp(stream)
    ret_dict = {}
    apps_dict = ret_dict["Apps"] = {}
    for sect in cfg.sections():
        if sect=="SpamBayes":
            target_dict = ret_dict
        else:
            target_dict = apps_dict.setdefault(sect, {})
        for opt in cfg.options(sect):
            val = cfg.get(sect, opt)
            # some butchering
            try:
                val = float(val)
            except ValueError:
                pass
            target_dict[opt] = val
    return ret_dict

# Utilities for generating a 'config' version of this file.
# The output of this should exist at the URL above.
def _make_cfg_section(stream, key, this_dict):
    stream.write("[%s]\n" % key)
    for name, val in this_dict.items():
        if type(val)==type(''):
            val_str = repr(val)[1:-1]
        elif type(val)==type(0.0):
            val_str = str(val)
        elif type(val)==type({}):
            val_str = None # sub-dict
        else:
            print "Skipping unknown value type: %r" % val
            val_str = None
        if val_str is not None:
            stream.write("%s:%s\n" % (name, val_str))
    stream.write("\n")

def make_cfg(stream):
    stream.write("# This file is generated from spambayes/Version.py" \
                 " - do not edit\n")
    _make_cfg_section(stream, "SpamBayes", versions)
    for appname in versions["Apps"]:
        _make_cfg_section(stream, appname, versions["Apps"][appname])
    
def main(args):
    if '-g' in args:
        make_cfg(sys.stdout)
        sys.exit(0)
    print "SpamBayes version is:", get_version_string()
    # Enumerate applications
    print
    print "Application versions:"
    for app in versions["Apps"]:
        print "%s: %s" % (app, get_version_string(app))

    print
    print "Fetching the lastest version information..."
    try:
        latest_dict = fetch_latest_dict()
    except:
        print "FAILED to fetch the latest version"
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print
    print "SpamBayes version is:", get_version_string(version_dict=latest_dict)
    # Enumerate applications
    print
    print "Application versions:"
    for app in latest_dict["Apps"]:
        print "%s: %s" % (app, get_version_string(app, version_dict=latest_dict))

if __name__=='__main__':
    import sys
    main(sys.argv)
