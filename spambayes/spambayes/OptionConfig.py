"""Options Configurator
Classes:
    OptionsConfigurator - changes select values in Options.py

Abstract:

This module implements a browser based Spambayes option file configuration
utility.  Users may use it (via pop3proxy.py) to customize the options in
the bayescustomize.ini file.

To Do:
    o Replace some of the test options with radio buttons/checkboxes.
    o Suggestions?

"""

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tim Stone <tim@fourstonesExpressions.com>"
# Blame for bugs caused by using Dibbler: Richie Hindle <richie@entrian.com>

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

from spambayes import Dibbler, PyMeldLite
from spambayes.Options import options, optionsPathname
import sys
import ConfigParser

# This control dictionary maps http request parameters and template fields
# to ConfigParser sections and options.  The key matches both the input
# field that corresponds to a section/option, and also the HTML template
# variable that is used to display the value of that section/option.
parm_ini_map = \
   {'hamcutoff':    ('Categorization',  'ham_cutoff'),
    'spamcutoff':   ('Categorization',  'spam_cutoff'),
    'dbname':       ('pop3proxy',       'pop3proxy_persistent_storage_file'),
    'headername':   ('Hammie',          'hammie_header_name'),
    'spamstring':   ('Hammie',          'header_spam_string'),
    'hamstring':    ('Hammie',          'header_ham_string'),
    'unsurestring': ('Hammie',          'header_unsure_string'),
    'p3servers':    ('pop3proxy',       'pop3proxy_servers'),
    'p3ports':      ('pop3proxy',       'pop3proxy_ports'),
    'p3notateto':   ('pop3proxy',       'pop3proxy_notate_to'),
    'p3notatesub':  ('pop3proxy',       'pop3proxy_notate_subject'),
    'p3cachemsg':   ('pop3proxy',       'pop3proxy_cache_messages'),
    'p3addid':      ('pop3proxy',       'pop3proxy_add_mailid_to'),
    'p3stripid':    ('pop3proxy',       'pop3proxy_strip_incoming_mailids'),
    'p3prob':       ('pop3proxy',       'pop3proxy_include_prob'),
    'p3thermostat': ('pop3proxy',       'pop3proxy_include_thermostat'),
    'p3evidence':   ('pop3proxy',       'pop3proxy_include_evidence'),
    'smtpservers':  ('smtpproxy',       'smtpproxy_servers'),
    'smtpports':    ('smtpproxy',       'smtpproxy_ports'),
    'smtpham':      ('smtpproxy',       'smtpproxy_ham_address'),
    'smtpspam':     ('smtpproxy',       'smtpproxy_spam_address'),
   }

# "Restore defaults" ignores these, because it would be pointlessly
# destructive - they default to being empty, so you gain nothing by
# restoring them.
noRestore = ('pop3proxy_servers', 'pop3proxy_ports', 'pop3_notate_to',
             'smtpproxy_servers', 'smtpproxy_ports')

# This governs the order in which the options appear on the configurator
# page, and the headings and help text that are used.
page_layout = \
(
    ("POP3 Options",
    (   ("p3servers", "Servers",
         """The Spambayes POP3 proxy intercepts incoming email and classifies
         it before sending it on to your email client.  You need to specify
         which POP3 server(s) you wish it to intercept - a POP3 server
         address typically looks like "pop3.myisp.net".  If you use more than
         one server, simply separate their names with commas.  You can get
         these server names from your existing email configuration, or from
         your ISP or system administrator.  If you are using Web-based email,
         you can't use the Spambayes POP3 proxy (sorry!).  In your email
         client's configuration, where you would normally put your POP3 server
         address, you should now put the address of the machine running
         Spambayes."""),

        ("p3ports", "Ports",
         """Each POP3 server that is being monitored must be assigned to a
         'port' in the Spambayes POP3 proxy.  This port must be different for
         each monitored server, and there <strong>must</strong> be a port for
         each monitored server.  Again, you need to configure your email
         client to use this port.  If there are multiple servers, you must
         specify the same number of ports as servers, separated by commas."""),
         
        ("p3notateto", "Notate To",
         """Some email clients (Outlook Express, for example) can only
         set up filtering rules on a limited set of headers.  These
         clients cannot test for the existence/value of an arbitrary
         header and filter mail based on that information.  To
         accomodate these kind of mail clients, the Notate To: can be
         checked, which will add "spam", "ham", or "unsure" to the
         recipient list.  A filter rule can then use this to see if
         one of these words (followed by a comma) is in the recipient
         list, and route the mail to an appropriate folder, or take
         whatever other action is supported and appropriate for the
         mail classification."""),

       ("p3notatesub", "Notate Subject",
         """This option will add the same information as Notate to:,
         but to the start of the mail subject line."""),

       ("p3cachemsg", "Cache Messages",
         """You can disable the pop3proxy caching of messages.  This
         will make the proxy a bit faster, and make it use less space
         on your hard drive.  The proxy uses its cache for reviewing
         and training of messages, so if you disable caching you won't
         be able to do further training unless you re-enable it.
         Thus, you should only turn caching off when you are satisfied
         with the filtering that Spambayes is doing for you."""),

        ("p3addid", "Add id tag",
         """If you wish to be able to find a specific message (via the 'find'
         box on the <a href="home">home</a> page), or use the SMTP proxy to
         train, you will need to know the unique id of each message.  If your
         mailer allows you to view all message headers, and includes all these
         headers in forwarded/bounced mail, then the best place for this id
         is in the headers of incoming mail.  Unfortunately, some mail clients
         do not offer these capabilities.  For these clients, you will need to
         have the id added to the body of the message.  If you are not sure,
         the safest option is to use both.  Valid options include neither
         the header nor the body (leave this blank), header only ("header"),
         body only ("body"), or both ("header body")."""),

        ("p3stripid", "Strip incoming ids",
         """If you receive messages from other spambayes users, you might
         find that incoming mail (generally replies) already has an id,
         particularly if they have set the id to appear in the body (see
         above).  This might confuse the SMTP proxy when it tries to identify
         the message to train, and make it difficult for you to identify
         the correct id to find a message.  This option strips all spambayes
         ids from incoming mail."""),

        ("p3prob", "Add spam probability header",
         """You can have spambayes insert a header with the calculated spam
         probability into each mail.  If you can view headers with your
         mailer, then you can see this information, which can be interesting
         and even instructive if you're a serious spambayes junkie."""),
        
        ("p3thermostat", "Add spam level header",
         """You can have spambayes insert a header with the calculated spam
         probability, expressed as a number of '*'s, into each mail (the more
         '*'s, the higher the probability it is spam). If your mailer
         supports it, you can use this information to fine tune your
         classification of ham/spam, ignoring the classification given."""),
        
        ("p3evidence", "Add evidence header",
         """You can have spambayes insert a header into mail, with the
         evidence that it used to classify that message (a collection of
         words with ham and spam probabilities).  If you can view headers
         with your mailer, then this may give you some insight as to why
         a particular message was scored in a particular way."""),

    )),

    ("SMTP Options",
    (   ("smtpservers", "Servers",
         """The Spambayes SMTP proxy intercepts outgoing email - if you have
         sent it to one of the addresses below, it is examined for an id and
         the message corresponding to that id is trained as ham/spam.  All
         other mail is sent along to your outgoing mail server.  You need to
         specify which SMTP server(s) you wish it to intercept - a SMTP server
         address typically looks like "smtp.myisp.net".  If you use more than
         one server, simply separate their names with commas.  You can get
         these server names from your existing email configuration, or from
         your ISP or system administrator.  If you are using Web-based email,
         you can't use the Spambayes SMTP proxy (sorry!).  In your email
         client's configuration, where you would normally put your SMTP server
         address, you should now put the address of the machine running
         Spambayes."""),

        ("smtpports", "Ports",
         """Each SMTP server that is being monitored must be assigned to a
         'port' in the Spambayes SMTP proxy.  This port must be different for
         each monitored server, and there <strong>must</strong> be a port for
         each monitored server.  Again, you need to configure your email
         client to use this port.  If there are multiple servers, you must
         specify the same number of ports as servers, separated by commas."""),
         
        ("smtpham", "Ham Address",
         """When a message is received that you wish to train on (for example,
         one that was incorrectly classified), you need to forward or bounce
         it to one of two special addresses so that the SMTP proxy can identify
         it.  If you wish to train it as ham, forward or bounce it to this
         address.  You will want to use an address that is <strong>not</strong>
         a valid email address, like ham@nowhere.nothing."""),

        ("smtpspam", "Spam Address",
         """As with Ham Address above, but the address that you need to forward
         or bounce mail that you wish to train as spam.  You will want to use
         an address that is <strong>not</strong> a valid email address, like
         spam@nowhere.nothing."""),
    )),

    ("Statistics Options",
    (   ("hamcutoff", "Ham Cutoff",
         """Spambayes gives each email message a spam probability between
         0 and 1. Emails below the Ham Cutoff probability are classified
         as Ham. Larger values will result in more messages being
         classified as ham, but with less certainty that all of them
         actually <i>are</i> ham. This value should be between 0 and 1,
         and should be smaller than the Spam Cutoff."""),

        ("spamcutoff", "Spam Cutoff",
         """Emails with a spam probability above the Spam Cutoff are
         classified as Spam - just like the Ham Cutoff but at the other
         end of the scale.  Messages that fall between the two values
         are classified as Unsure."""),

        ("dbname", "Database filename",
         """Spambayes builds a database of information that it gathers
         from incoming emails and from you, the user, to get better and
         better at classifying your email.  This option specifies the
         name of the database file.  If you don't give a full pathname,
         the name will be taken to be relative to the current working
         directory."""),
    )),
)

# Tim Stone's original OptionConfig.py had these options as well, but I
# (Richie) suggested that they were overkill, and Tim agreed.  We can always
# put them back if people want them.
_insertedHeaderOptions = '''
    ("Inserted Header Options",
    (   ("headername", "Header Name",
         """Spambayes classifies each message by inserting a new header into
         the message.  This header can then be used by your email client
         (provided your client supports filtering) to move spam into a
         separate folder (recommended), delete it (not recommended), etc.
         This option specifies the name of the header that Spambayes inserts.
         The default value should work just fine, but you may change it to
         anything that you wish."""),

        ("spamstring", "Spam Designation",
         """The header that Spambayes inserts into each email has a name,
            (Header Name, above), and a value.  If the classifier determines
            that this email is probably spam, it places a header named as
            above with a value as specified by this string.  The default
            value should work just fine, but you may change it to anything
            that you wish."""),

        ("hamstring", "Ham Designation",
         """As for Spam Designation above, but for emails classified as
         Ham."""),

        ("unsurestring", "Unsure Designation",
         """As for Spam/Ham Designation above, but for emails which the
         classifer wasn't sure about (ie. the spam probability fell between
         the Ham and Spam Cutoffs).  Emails that have this classification
         should always be the subject of training."""),
    )),
'''

OK_MESSAGE = "%s.  Return <a href='home'>Home</a>."

PIMapSect = 0
PIMapOpt = 1


class OptionsConfigurator(Dibbler.HTTPPlugin):
    def __init__(self, proxyUI):
        Dibbler.HTTPPlugin.__init__(self)
        self.proxyUI = proxyUI
        self.html = self.proxyUI.html.clone()

        # "Save and Shutdown" is confusing here - it means "Save database"
        # but that's not clear.
        self.html.shutdownTableCell = "&nbsp;"

    def onConfig(self):
        # start with the options config file, add bayescustomize.ini to it
        bcini = ConfigParser.ConfigParser()

        # this is a pain...
        for sect in options._config.sections():
            for opt in options._config.options(sect):
                try:
                    bcini.set(sect, opt, options._config.get(sect, opt))
                except ConfigParser.NoSectionError:
                    bcini.add_section(sect)
                    bcini.set(sect, opt, options._config.get(sect, opt))

        bcini.read(optionsPathname)

        # Start with an empty config form then add the sections.
        html = self.html.clone()
        html.mainContent = self.html.configForm.clone()
        html.mainContent.configFormContent = ""
        html.mainContent.optionsPathname = optionsPathname

        # Loop though the sections in the `page_layout` structure above.
        for sectionHeading, values in page_layout:
            # Start the yellow-headed box for this section.
            section = self.html.headedBox.clone()
            section.heading = sectionHeading
            del section.iconCell

            # Get a clone of the config table and a clone of each example row,
            # then blank out the example rows to make way for the real ones.
            configTable = self.html.configTable.clone()
            configRow1 = configTable.configRow1.clone()
            configRow2 = configTable.configRow2.clone()
            blankRow = configTable.blankRow.clone()
            del configTable.configRow1
            del configTable.configRow2
            del configTable.blankRow

            # Now within this section, loop though the values, adding a
            # labelled input control for each one, populated with the current
            # value.
            isFirstRow = True
            for name, label, unusedHelp in values:
                newConfigRow1 = configRow1.clone()
                newConfigRow2 = configRow2.clone()
                currentValue = bcini.get(parm_ini_map[name][PIMapSect], \
                                         parm_ini_map[name][PIMapOpt])

                # If this is the first row, insert the help text in a cell
                # with a `rowspan` that covers all the rows.
                if isFirstRow:
                    entries = []
                    for unusedName, topic, help in values:
                        entries.append("<p><b>%s: </b>%s</p>" % (topic, help))
                    newConfigRow1.helpSpacer = '&nbsp;' * 10
                    newConfigRow1.helpCell = '\n'.join(entries)
                else:
                    del newConfigRow1.helpSpacer
                    del newConfigRow1.helpCell

                # Populate the rows with the details and add them to the table.
                newConfigRow1.label = label
                newConfigRow1.input.name = name
                newConfigRow1.input.value = currentValue
                newConfigRow2.currentValue = currentValue
                configTable += newConfigRow1 + newConfigRow2 + blankRow
                isFirstRow = False

            # Finish off the box for this section and add it to the form.
            section.boxContent = configTable
            html.configFormContent += section

        html.title = 'Home &gt; Configure'
        html.pagename = '&gt; Configure'
        self.writeOKHeaders('text/html')
        self.write(html)

    def onChangeopts(self, **parms):
        html = self.html.clone()
        html.mainContent = self.html.headedBox.clone()
        errmsg = editInput(parms)
        if errmsg != '':
            html.mainContent.heading = "Errors Detected"
            html.mainContent.boxContent = errmsg
            html.title = 'Home &gt; Error'
            html.pagename = '&gt; Error'
            self.writeOKHeaders('text/html')
            self.write(html)
            return

        updateIniFile(parms)
        self.proxyUI.reReadOptions()

        html.mainContent.heading = "Options Changed"
        html.mainContent.boxContent = OK_MESSAGE % "Options changed"
        html.title = 'Home &gt; Options Changed'
        html.pagename = '&gt; Options Changed'
        self.writeOKHeaders('text/html')
        self.write(html)

    def onRestoredefaults(self, how):
        restoreIniDefaults()
        self.proxyUI.reReadOptions()

        html = self.html.clone()
        html.mainContent = self.html.headedBox.clone()
        html.mainContent.heading = "Option Defaults Restored"
        html.mainContent.boxContent = OK_MESSAGE % "Defaults restored"
        html.title = 'Home &gt; Defaults Restored'
        html.pagename = '&gt; Defaults Restored'
        self.writeOKHeaders('text/html')
        self.write(html)


def editInput(parms):

    errmsg = ''

    # edit numericity of hamcutoff and spamcutoff
    try:
        hco = parms['hamcutoff']
    except KeyError:
        hco = options.ham_cutoff

    try:
        sco = parms['spamcutoff']
    except KeyError:
        sco = options.spam_cutoff

    errmsg = ''
    try:
        hco = float(hco)
    except ValueError:
        errmsg += '<li>Ham cutoff must be a number, between 0 and 1</li>\n'

    try:
        sco = float(sco)
    except ValueError:
        errmsg += '<li>Spam cutoff must be a number, between 0 and 1</li>\n'

    # edit 0 <= hamcutoff < spamcutoff <= 1
    if hco < 0 or hco > 1:
        errmsg += '<li>Ham cutoff must be between 0 and 1</li>\n'
    if sco < 0 or sco > 1:
        errmsg += '<li>Spam cutoff must be between 0 and 1</li>\n'
    if not hco < sco:
        errmsg += '<li>Ham cutoff must be less than Spam cutoff</li>\n'

    try:
        nto = parms['p3notateto']
    except KeyError:
        if options.pop3proxy_notate_to:
            nto = "True"
        else:
            nto = "False"
    
    if not nto == "True" and not nto == "False":
        errmsg += """<li>Notate To: must be "True" or "False".</li>\n"""
    
    try:
        nsub = parms['p3notatesub']
    except KeyError:
        if options.pop3proxy_notate_sub:
            nsub = "True"
        else:
            nsub = "False"
    
    if not nsub == "True" and not nsub == "False":
        errmsg += """<li>Notate Subject: must be "True" or "False".</li>\n"""
    
    try:
        cachemsg = parms['p3cachemsg']
    except KeyError:
        if options.pop3proxy_cache_messages:
            cachemsg = "True"
        else:
            cachemsg = "False"
    
    if not cachemsg == "True" and not cachemsg == "False":
        errmsg += """<li>Cache Messages: must be "True" or "False".</li>\n"""
    
    try:
        prob = parms['p3prob']
    except KeyError:
        if options.pop3proxy_include_prob:
            prob = "True"
        else:
            prob = "False"
            
    if not prob == "True" and not prob == "False":
        errmsg += """<li>Add Spam Probability Header: must be "True" or "False".</li>\n"""
    
    try:
        prob = parms['p3thermostat']
    except KeyError:
        if options.pop3proxy_include_thermostat:
            prob = "True"
        else:
            prob = "False"
            
    if not prob == "True" and not prob == "False":
        errmsg += """<li>Add Spam Level Header: must be "True" or "False".</li>\n"""
    
    try:
        prob = parms['p3evidence']
    except KeyError:
        if options.pop3proxy_include_evidence:
            prob = "True"
        else:
            prob = "False"
            
    if not prob == "True" and not prob == "False":
        errmsg += """<li>Add Spam Evidence Header: must be "True" or "False".</li>\n"""
    
    try:
        aid = parms['p3addid']
    except KeyError:
        aid = options.pop3proxy_add_mailid_to
            
    if not aid == "" and not aid == "body" \
       and not aid == "header" and not aid == "body header" \
       and not aid == "header body":
        errmsg += """<li>Add Id Tag: must be "",
        "body", "header", "body header", or "header body".</li>\n"""

    try:
        sid = parms['p3stripid']
    except KeyError:
        if options.pop3proxy_strip_incoming_mailids:
            sid = "True"
        else:
            sid = "False"
            
    if not sid == "True" and not sid == "False":
        errmsg += """<li>Strip Incoming Ids: must be "True" or "False".</li>\n"""

    # edit for equal number of pop3servers and ports
    try:
        slist = parms['p3servers'].split(',')
    except KeyError:
        slist = options.pop3proxy_servers.split(',')

    try:
        plist = parms['p3ports'].split(',')
    except KeyError:
        plist = options.pop3proxy_ports.split(',')

    # edit for duplicate ports
    if len(slist) != len(plist):
        errmsg += '<li>The number of ports specified must match the \
number of servers specified</li>\n'

    plist.sort()
    for p in range(len(plist)-1):
        try:
            if plist[p] == plist[p+1]:
                errmsg += '<li>All port numbers must be unique</li>'
                break
        except IndexError:
            pass

    return errmsg

def updateIniFile(parms):

    # Get the pathname of the ini file as discovered by the Options module.
    inipath = optionsPathname

    bcini = ConfigParser.ConfigParser()
    bcini.read(inipath)

    for httpParm in parm_ini_map:
        map = parm_ini_map[httpParm]
        sect = map[PIMapSect]
        opt = map[PIMapOpt]

        try:
            val = parms[httpParm]
        except KeyError:
            continue

        try:
            bcini.add_section(sect)
        except ConfigParser.DuplicateSectionError:
            pass

        bcini.set(sect, opt, val)

    o = open(inipath, 'wt')
    bcini.write(o)
    o.close()

def restoreIniDefaults():

    # Get the pathname of the ini file as discovered by the Options module.
    inipath = optionsPathname

    bcini = ConfigParser.ConfigParser()
    bcini.read(inipath)

    # Only restore the settings that appear on the form.
    for section, option in parm_ini_map.values():
        if option not in noRestore:
            try:
                bcini.remove_option(section, option)
            except ConfigParser.NoSectionError:
                pass    # Already missing.

    o = open(inipath, 'wt')
    bcini.write(o)
    o.close()
