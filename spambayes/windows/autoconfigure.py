#!/usr/bin/env python

"""Automatically set up the user's mail client and SpamBayes.

Currently works with:
 o Eudora (POP3/SMTP only)
 o Mozilla Mail (POP3/SMTP only)
 o Opera Mail (M2) (POP3/SMTP only)
 o Outlook Express (POP3/SMTP only)

To do:
 o Establish which mail client(s) are to be setup.
 o Locate the appropriate configuration directory
   (e.g. for Eudora this is probably either the application directory,
   or c:\documents and settings\username\application data\qualcomm\eudora,
   i.e. sh_appdata\qualcomm\eudora)
 o This will create some unnecessary proxies in some cases.  For example,
   if I have my client set up to get mail from pop.example.com for the
   user 'tmeyer' and the user 'tonym', two proxies will be created, but
   only one is necessary.  We should check the existing proxies before
   adding a new one.
 o Figure out Outlook Express's pop3uidl.dbx file and how to hook into it
   (use the oe_mailbox.py module)
 o Other mail clients?  Other platforms?
 o This won't work all that well if multiple mail clients are used (they
   will end up trying to use the same ports).  In such a case, we really
   need to keep track of if the server is being proxied already, and
   reuse ports, but this is complicated.
 o We currently don't make any moves to protect the original file, so if
   something does wrong, it's corrupted.  We also write into the file,
   rather than a temporary one and then copy across.  This should all be
   fixed.
 o Suggestions?
"""

# This module is part of the spambayes project, which is Copyright 2002-3
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
__credits__ = "All the Spambayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

## Tested with:
##  o Eudora 5.2 on Windows XP
##  o Mozilla 1.3 on Windows XP
##  o Opera 7.11 on Windows XP
##  o Outlook Express 6 on Windows XP

import re
import os
import types
import socket
import StringIO
import ConfigParser

from spambayes.Options import options, optionsPathname

def move_to_next_free_port(port):
    # Increment port until we get to one that isn't taken.
    # I doubt this will work if there is a firewall that prevents
    # localhost connecting to particular ports, but I'm not sure
    # how else we can do this - Richie says that bind() doesn't
    # necessarily fail if the port is already bound.
    while True:
        try:
            port += 1
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", port))
            s.close()
        except socket.error:
            return port

# Let's be safe and use high ports, starting at 1110 and 1025, and going up
# as required.
pop_proxy_port = move_to_next_free_port(1109)
smtp_proxy_port = move_to_next_free_port(1024)

def configure_eudora(config_location):
    """Configure Eudora to use the SpamBayes POP3 and SMTP proxies, and
    configure SpamBayes to proxy the servers that Eudora was connecting to.
    """
    ini_filename = "%s%seudora.ini" % (config_location, os.sep)
    c = ConfigParser.ConfigParser()
    c.read(ini_filename)

    translate = {("PopServer", "POPPort") : "pop3proxy",
                 ("SMTPServer", "SMTPPort") : "smtpproxy",
                 }

    pop_proxy = pop_proxy_port
    smtp_proxy = smtp_proxy_port

    for sect in c.sections():
        if sect.startswith("Persona-") or sect == "Settings":
            if c.get(sect, "UsesIMAP") == "0":
                # Eudora stores the POP3 server name in two places.
                # Why?  Who knows?  We do the popaccount one
                # separately, because it also has the username.
                p = c.get(sect, "popaccount")
                c.set(sect, "popaccount", "%s@localhost" % \
                      (p[:p.index('@')],))
                for (eud_name, eud_port), us_name in translate.items():
                    try:
                        port = c.get(sect, eud_port)
                    except ConfigParser.NoOptionError:
                        port = None
                        
                    if us_name.lower()[:4] == "pop3":
                        if port is None:
                            port = 110
                        pop_proxy = move_to_next_free_port(pop_proxy)
                        proxy_port = pop_proxy
                    else:
                        if port is None:
                            port = 25
                        smtp_proxy = move_to_next_free_port(smtp_proxy)
                        proxy_port = smtp_proxy
                    server = "%s:%s" % (c.get(sect, eud_name), port)
                    options[us_name, "remote_servers"] += (server,)
                    options[us_name, "listen_ports"] += (proxy_port,)
                    if options["globals", "verbose"]:
                        print "[%s] Proxy %s on localhost:%s" % \
                              (sect, server, proxy_port)
                    c.set(sect, eud_name, "localhost")
                    c.set(sect, eud_port, proxy_port)
            else:
                # Setup imapfilter instead
                pass

    out = file(ini_filename, "w")
    c.write(out)
    out.close()
    options.update_file(optionsPathname)

    # Setup filtering rule
    # This assumes that the spam and unsure folders already exist!
    # (Creating them shouldn't be that difficult - it's just a mbox file,
    # and I think the .toc file is automatically created).  Left for
    # another day, however.
    filter_filename = "%s%sFilters.pce" % (config_location, os.sep)
    spam_folder_name = "Junk Mail"
    unsure_folder_name = "Possible Junk"
    header_name = options["Headers", "classification_header_name"]
    spam_tag = options["Headers", "header_spam_string"]
    unsure_tag = options["Headers", "header_unsure_string"]
    # We are assuming that a rules file already exists, otherwise there
    # is a bit more to go at the top.
    filter_rules = "rule SpamBayes-Spam\n" \
                   "transfer %s.mbx\n" \
                   "incoming\n" \
                   "header %s\n" \
                   "verb contains\n" \
                   "value %s\n" \
                   "conjunction ignore\n" \
                   "header \n" \
                   "verb contains\n" \
                   "value \n" \
                   "rule SpamBayes-Unsure\n" \
                   "transfer %s.mbx\n" \
                   "incoming\n" \
                   "header %s\n" \
                   "verb contains\n" \
                   "value %s\n" \
                   "conjunction ignore\n" \
                   "header \n" \
                   "verb contains\n" \
                   "value \n" % (spam_folder_name, header_name, spam_tag,
                                 unsure_folder_name, header_name, unsure_tag)
    filter_file = file(filter_filename, "a")
    filter_file.write(filter_rules)
    filter_file.close()

def configure_mozilla(config_location):
    """Configure Mozilla to use the SpamBayes POP3 and SMTP proxies, and
    configure SpamBayes to proxy the servers that Mozilla was connecting
    to."""
    prefs_file = file("%s%sprefs.js" % (config_location, os.sep), "r")
    prefs = prefs_file.read()
    prefs_file.close()
    save_prefs = prefs
    pop_accounts = {}
    smtp_accounts = {}
    
    r = re.compile(r"user_pref\(\"mail.server.server(\d+).(real)?hostname\", \"([^\"]*)\"\);")
    current_pos = 0
    while True:
        m = r.search(prefs[current_pos:])
        if not m:
            break
        server_num = m.group(1)
        real = m.group(2) or ''
        server = m.group(3)
        current_pos += m.end()
        old_pref = 'user_pref("mail.server.server%s.%shostname", "%s");' % \
                   (server_num, real, server)

        # Find the port, if there is one
        port_string = 'user_pref("mail.server.server%s.port", ' % \
                      (server_num,)
        port_loc = prefs.find(port_string)
        if port_loc == -1:
            port = "110"
            old_port = None
        else:
            loc_plus_len = port_loc + len(port_string)
            end_of_number = loc_plus_len + prefs[loc_plus_len:].index(')')
            port = prefs[loc_plus_len : end_of_number]
            old_port = "%s%s);" % (port_string, port)

        # Find the type of connection
        type_string = 'user_pref("mail.server.server%s.type", "' % \
                      (server_num,)
        type_loc = prefs.find(type_string)
        if type_loc == -1:
            # no type, so ignore this one
            continue
        type_loc += len(type_string)
        account_type = prefs[type_loc : \
                             type_loc + prefs[type_loc:].index('"')]
        
        if account_type == "pop3":
            new_pref = 'user_pref("mail.server.server%s.%shostname", ' \
                       '"127.0.0.1");' % (server_num, real)
            if not pop_accounts.has_key(server_num) or real:
                pop_accounts[server_num] = (new_pref, old_pref,
                                            old_port, server, port)
        elif account_type == "imap":
            # Setup imapfilter instead
            pass

    proxy_port = pop_proxy_port
    for num, (pref, old_pref, old_port, server, port) in pop_accounts.items():
        server = "%s:%s" % (server, port)
        proxy_port = move_to_next_free_port(proxy_port)
        port_pref = 'user_pref("mail.server.server%s.port", %s);' % \
                    (num, proxy_port)
        options["pop3proxy", "remote_servers"] += (server,)
        options["pop3proxy", "listen_ports"] += (proxy_port,)
        if old_port is None:
            pref = "%s\n%s" % (pref, port_pref)
        else:
            save_prefs = save_prefs.replace(old_port, port_pref)
        save_prefs = save_prefs.replace(old_pref, pref)
        if options["globals", "verbose"]:
            print "[%s] Proxy %s on localhost:%s" % \
                  (num, server, proxy_port)

    # Do the SMTP server.
    # Mozilla recommends that only advanced users setup more than one,
    # so we'll just set that one up.  Advanced users can setup SpamBayes
    # themselves <wink>.
    prefs = save_prefs
    r = re.compile(r"user_pref\(\"mail.smtpserver.smtp(\d+).hostname\", \"([^\"]*)\"\);")
    current_pos = 0
    while True:
        m = r.search(prefs[current_pos:])
        if not m:
            break
        current_pos = m.end()
        server_num = m.group(1)
        server = m.group(2)
        old_pref = 'user_pref("mail.smtpserver.smtp%s.hostname", ' \
                   '"%s");' % (server_num, server)
        new_pref = 'user_pref("mail.smtpserver.smtp%s.hostname", ' \
                   '"127.0.0.1");' % (server_num,)

        # Find the port        
        port_string = 'user_pref("mail.smtpserver.smtp1.port", '
        port_loc = prefs.find(port_string)
        if port_loc == -1:
            port = "25"
            old_port = None
        else:
            loc_plus_len = port_loc + len(port_string)
            end_of_number = loc_plus_len + prefs[loc_plus_len:].index(')')
            port = prefs[loc_plus_len : end_of_number]
            old_port = 'user_pref("mail.smtpserver.smtp%s.port", %s);' % \
                       (server_num, port)
        smtp_accounts[server_num] = (new_pref, old_pref, old_port,
                                     server, port)

    proxy_port = smtp_proxy_port
    for num, (pref, old_pref, old_port, server, port) in smtp_accounts.items():
        server = "%s:%s" % (server, port)
        proxy_port = move_to_next_free_port(proxy_port)
        port_pref = 'user_pref("mail.smtpserver.smtp%s.port", %s);' % \
                    (num, proxy_port)
        options["smtpproxy", "remote_servers"] += (server,)
        options["smtpproxy", "listen_ports"] += (proxy_port,)
        if old_port is None:
            pref = "%s\n%s" % (pref, port_pref)
        else:
            save_prefs = save_prefs.replace(old_port, port_pref)
        save_prefs = save_prefs.replace(old_pref, pref)
        if options["globals", "verbose"]:
            print "[%s] Proxy %s on localhost:%s" % \
                  (num, server, proxy_port)

    prefs_file = file("%s%sprefs.js" % (config_location, os.sep), "w")
    prefs_file.write(save_prefs)
    prefs_file.close()
    options.update_file(optionsPathname)

    # Setup filtering rules.
    # Assumes that the folders already exist!  I don't know how difficult
    # it would be to create new Mozilla mail folders.
    filter_filename = "%s%smsgFilterRules.dat" % (config_location, os.sep)
    store_name = "" # how do we get this?
    spam_folder_url = "mailbox:////%s//Junk%20Mail" % (store_name,)
    unsure_folder_url = "mailbox:////%s//Possible%20Junk" % (store_name,)
    header_name = options["Headers", "classification_header_name"]
    spam_tag = options["Headers", "header_spam_string"]
    unsure_tag = options["Headers", "header_unsure_string"]
    rule = 'name="SpamBayes-Spam"\n' \
           'enabled="yes"\n' \
           'type="1"\n' \
           'action="Move to folder"\n' \
           'actionValue="%s"\n' \
           'condition="OR (\"%s\",contains,%s)"\n' \
           'name="SpamBayes-Unsure"\n' \
           'enabled="yes"\n' \
           'type="1"\n' \
           'action="Move to folder"\n' \
           'actionValue="%s"\n' \
           'condition="OR (\"%s\",contains,%s)"\n' % \
           (spam_folder_url, header_name, spam_tag,
            unsure_folder_url, header_name, unsure_tag)
    # This should now be written to the file, but I'm not sure how we
    # determine which subdirectory it goes into - does it have to go
    # into them all?
    # We are assuming that a rules file already exists, otherwise there
    # is a bit more to go at the top.

def configure_m2(config_location):
    """Configure M2 (Opera's mailer) to use the SpamBayes POP3 and SMTP
    proxies, and configure SpamBayes to proxy the servers that M2 was
    connecting to."""
    ini_filename = os.path.join(config_location, "Mail", "accounts.ini")
    ini_file = file(ini_filename, "r")
    faked_up = StringIO.StringIO()
    faked_up.write(";") # Missing at the start
    faked_up.write(ini_file.read())
    faked_up.seek(0)
    ini_file.close()
    c = ConfigParser.ConfigParser()
    c.readfp(faked_up)

    translate = {("Incoming Servername", "Incoming Port") : "pop3proxy",
                 ("Outgoing Servername", "Outgoing Port") : "smtpproxy",
                 }

    pop_proxy = pop_proxy_port
    smtp_proxy = smtp_proxy_port

    for sect in c.sections():
        if sect.startswith("Account") and sect != "Accounts":
            if c.get(sect, "Incoming Protocol") == "POP":
                for (m2_name, m2_port), us_name in translate.items():
                    try:
                        port = c.get(sect, m2_port)
                    except ConfigParser.NoOptionError:
                        port = None
                        
                    if us_name.lower()[:4] == "pop3":
                        if port is None:
                            port = 110
                        pop_proxy = move_to_next_free_port(pop_proxy)
                        proxy_port = pop_proxy
                    else:
                        if port is None:
                            port = 25
                        smtp_proxy = move_to_next_free_port(smtp_proxy)
                        proxy_port = smtp_proxy
                    server = "%s:%s" % (c.get(sect, m2_name), port)
                    options[us_name, "remote_servers"] += (server,)
                    options[us_name, "listen_ports"] += (proxy_port,)
                    if options["globals", "verbose"]:
                        print "[%s] Proxy %s on localhost:%s" % \
                              (sect, server, proxy_port)
                    c.set(sect, m2_name, "localhost")
                    c.set(sect, m2_port, proxy_port)
            elif c.get(sect, "Incoming Protocol") == "IMAP":
                # Setup imapfilter instead
                pass

    out = file(ini_filename, "w")
    c.write(out)
    out.close()
    options.update_file(optionsPathname)

    # Setting up a filter in M2 is very simple, but I'm not sure what the
    # right rule is - M2 doesn't move mail, it just displays a subset.
    # If someone can describe the best all-purpose rule, I'll pop it in
    # here.

def configure_outlook_express(key):
    """Configure OE to use the SpamBayes POP3 and SMTP proxies, and
    configure SpamBayes to proxy the servers that OE was connecting to."""
    # OE stores its configuration in the registry, not a file.

    key = key + "\\Software\\Microsoft\\Internet Account Manager\\Accounts"
    
    import win32api
    import win32con

    translate = {("POP3 Server", "POP3 Port") : "pop3proxy",
                 ("SMTP Server", "SMTP Port") : "smtpproxy",
                 }

    pop_proxy = pop_proxy_port
    smtp_proxy = smtp_proxy_port

    reg = win32api.RegOpenKeyEx(win32con.HKEY_USERS, key)
    account_index = 0
    while True:
        # Loop through all the accounts
        config = {}
        try:
            subkey_name = "%s\\%s" % \
                          (key, win32api.RegEnumKey(reg, account_index))
        except win32api.error:
            break
        account_index += 1
        index = 0
        subkey = win32api.RegOpenKeyEx(win32con.HKEY_USERS, subkey_name, 0,
                                       win32con.KEY_READ | win32con.KEY_SET_VALUE)
        while True:
            # Loop through all the keys
            try:
                raw = win32api.RegEnumValue(subkey, index)
            except win32api.error:
                break
            config[raw[0]] = (raw[1], raw[2])
            index += 1

        # Process this account
        if config.has_key("POP3 Server"):
            for (server_key, port_key), sect in translate.items():
                server = "%s:%s" % (config[server_key][0],
                                    config[port_key][0])
                if sect[:4] == "pop3":
                    pop_proxy = move_to_next_free_port(pop_proxy)
                    proxy = pop_proxy
                else:
                    smtp_proxy = move_to_next_free_port(smtp_proxy)
                    proxy = smtp_proxy
                options[sect, "remote_servers"] += (server,)
                options[sect, "listen_ports"] += (proxy,)
                win32api.RegSetValueEx(subkey, server_key, 0,
                                       win32con.REG_SZ, "127.0.0.1")
                win32api.RegSetValueEx(subkey, port_key, 0,
                                       win32con.REG_SZ, str(proxy))
                if options["globals", "verbose"]:
                    print "[%s] Proxy %s on localhost:%s" % \
                          (config["Account Name"][0], server, proxy)
        elif config.has_key("IMAP Server"):
            # Setup imapfilter instead.
            pass

    options.update_file(optionsPathname)

    # Outlook Express rules are done in much the same way.  Should one
    # be set up to work with notate_to or notate_subject?  (and set that
    # option, obviously)


if __name__ == "__main__":
    # XXX This is my OE key = "S-1-5-21-95318837-410984162-318601546-13224"
    # XXX but I presume it's different for everyone?  I'll have to check on
    # XXX another machine.
    #configure_eudora(eudora_ini_dir)
    #configure_mozilla(mozilla_ini_dir)
    #configure_m2(m2_ini_dir)
    configure_outlook_express()
    pass
