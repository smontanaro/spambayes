"""Simple version repository for SpamBayes core, and our main apps"""

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
            "Version":          0.3,
            "BinaryVersion":    003,
            "Description":      "SpamBayes Outlook Addin Beta1",
            "Date":             "July 2003",
            "Full Description": "%(Description)s, version %(Version)s (%(Date)s)",
            "Full Description Binary":
                                "%(Description)s, Binary version %(BinaryVersion)s (%(Date)s)",
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

def get_version_string(app = None, description_key = "Full Description"):
    """Get a pretty version string, generally just to log or show in a UI"""
    if app is None:
        dict = versions
    else:
        dict = versions["Apps"][app]
    return dict[description_key] % dict

def get_version_number(app = None, version_key = "Version"):
    """Get a version number, as a float.  This would primarily be used so some
    app or extension can determine if we are later than a specific version
    of either the engine or a specific app.
    Maybe YAGNI.
    """
    if app is None:
        dict = versions
    else:
        dict = versions["Apps"][app]
    return dict[version_key]

if __name__=='__main__':
    print "SpamBayes version is:", get_version_string()
    # Enumerate applications
    print
    print "Application versions:"
    for app in versions["Apps"]:
        print "%s: %s" % (app, get_version_string(app))
