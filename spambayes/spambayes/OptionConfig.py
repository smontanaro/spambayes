"""Options Configurator
Classes:
    OptionsConfigurator - changes select values in Options.py

Abstract:

This module implements a browser based Spambayes option file configuration
utility.  Users may use it (via pop3proxy.py) to customize the options in
the bayescustomize.ini file.

To Do:
    o Checkboxes need a default value (i.e. what to set the option as
      when no boxes are checked).  This needs to be thought about and
      then implemented.  add_id is an example of what it does at the
      moment.
    o The values check could be much more generic.  Acceptable values are
      (mostly) already in the code, so they can be tested against, in a
      loop, rather than lots of individual, specific, pieces of code.
    o Suggestions?

"""

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tim Stone <tim@fourstonesExpressions.com>"
# Blame for bugs caused by using Dibbler: Richie Hindle <richie@entrian.com>
# Blame for bugs caused by the radio buttons / checkboxes: Tony Meyer
# <ta-meyer@ihug.co.nz>

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

from spambayes import Dibbler, PyMeldLite
from spambayes.Options import options, optionsPathname, defaults
import sys
from ConfigParser import NoSectionError, ConfigParser
from StringIO import StringIO

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
# The field type may be "text", "rb" (radio button), or "cb" (checkbox)
page_layout = \
(
    ("POP3 Options",
    (   ("p3servers", "Servers", "text", None,
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

        ("p3ports", "Ports", "text", None,
         """Each POP3 server that is being monitored must be assigned to a
         'port' in the Spambayes POP3 proxy.  This port must be different for
         each monitored server, and there <strong>must</strong> be a port for
         each monitored server.  Again, you need to configure your email
         client to use this port.  If there are multiple servers, you must
         specify the same number of ports as servers, separated by commas."""),
         
        ("p3notateto", "Notate To", "rb", ("True", "False"),
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

       ("p3notatesub", "Notate Subject", "rb", ("True", "False"),
         """This option will add the same information as Notate to:,
         but to the start of the mail subject line."""),

       ("p3cachemsg", "Cache Messages", "rb", ("True", "False"),
         """You can disable the pop3proxy caching of messages.  This
         will make the proxy a bit faster, and make it use less space
         on your hard drive.  The proxy uses its cache for reviewing
         and training of messages, so if you disable caching you won't
         be able to do further training unless you re-enable it.
         Thus, you should only turn caching off when you are satisfied
         with the filtering that Spambayes is doing for you."""),
    )),

    ("Header Options",
    (   ("p3addid", "Add id tag", "cb",
         ("header", "body"),
         """If you wish to be able to find a specific message (via the 'find'
         box on the <a href="home">home</a> page), or use the SMTP proxy to
         train, you will need to know the unique id of each message.  If your
         mailer allows you to view all message headers, and includes all these
         headers in forwarded/bounced mail, then the best place for this id
         is in the headers of incoming mail.  Unfortunately, some mail clients
         do not offer these capabilities.  For these clients, you will need to
         have the id added to the body of the message.  If you are not sure,
         the safest option is to use both."""),

        ("p3stripid", "Strip incoming ids", "rb", ("True", "False"),
         """If you receive messages from other spambayes users, you might
         find that incoming mail (generally replies) already has an id,
         particularly if they have set the id to appear in the body (see
         above).  This might confuse the SMTP proxy when it tries to identify
         the message to train, and make it difficult for you to identify
         the correct id to find a message.  This option strips all spambayes
         ids from incoming mail."""),

        ("p3prob", "Add spam probability header", "rb", ("True", "False"),
         """You can have spambayes insert a header with the calculated spam
         probability into each mail.  If you can view headers with your
         mailer, then you can see this information, which can be interesting
         and even instructive if you're a serious spambayes junkie."""),
        
        ("p3thermostat", "Add spam level header", "rb", ("True", "False"),
         """You can have spambayes insert a header with the calculated spam
         probability, expressed as a number of '*'s, into each mail (the more
         '*'s, the higher the probability it is spam). If your mailer
         supports it, you can use this information to fine tune your
         classification of ham/spam, ignoring the classification given."""),
        
        ("p3evidence", "Add evidence header", "rb", ("True", "False"),
         """You can have spambayes insert a header into mail, with the
         evidence that it used to classify that message (a collection of
         words with ham and spam probabilities).  If you can view headers
         with your mailer, then this may give you some insight as to why
         a particular message was scored in a particular way."""),
    )),

    ("SMTP Options",
    (   ("smtpservers", "Servers", "text", None,
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

        ("smtpports", "Ports", "text", None,
         """Each SMTP server that is being monitored must be assigned to a
         'port' in the Spambayes SMTP proxy.  This port must be different for
         each monitored server, and there <strong>must</strong> be a port for
         each monitored server.  Again, you need to configure your email
         client to use this port.  If there are multiple servers, you must
         specify the same number of ports as servers, separated by commas."""),
         
        ("smtpham", "Ham Address", "text", None,
         """When a message is received that you wish to train on (for example,
         one that was incorrectly classified), you need to forward or bounce
         it to one of two special addresses so that the SMTP proxy can identify
         it.  If you wish to train it as ham, forward or bounce it to this
         address.  You will want to use an address that is <strong>not</strong>
         a valid email address, like ham@nowhere.nothing."""),

        ("smtpspam", "Spam Address", "text", None,
         """As with Ham Address above, but the address that you need to forward
         or bounce mail that you wish to train as spam.  You will want to use
         an address that is <strong>not</strong> a valid email address, like
         spam@nowhere.nothing."""),
    )),

    ("Statistics Options",
    (   ("hamcutoff", "Ham Cutoff", "text", None, 
         """Spambayes gives each email message a spam probability between
         0 and 1. Emails below the Ham Cutoff probability are classified
         as Ham. Larger values will result in more messages being
         classified as ham, but with less certainty that all of them
         actually <i>are</i> ham. This value should be between 0 and 1,
         and should be smaller than the Spam Cutoff."""),

        ("spamcutoff", "Spam Cutoff", "text", None,
         """Emails with a spam probability above the Spam Cutoff are
         classified as Spam - just like the Ham Cutoff but at the other
         end of the scale.  Messages that fall between the two values
         are classified as Unsure."""),

        ("dbname", "Database filename", "text", None,
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
            configTextRow1 = configTable.configTextRow1.clone()
            configRbRow1 = configTable.configRbRow1.clone()
            configCbRow1 = configTable.configCbRow1.clone()
            configRow2 = configTable.configRow2.clone()
            blankRow = configTable.blankRow.clone()
            del configTable.configTextRow1
            del configTable.configRbRow1
            del configTable.configCbRow1
            del configTable.configRow2
            del configTable.blankRow

            # Now within this section, loop though the values, adding a
            # labelled input control for each one, populated with the current
            # value.
            isFirstRow = True
            for name, label, fldtype, validInput, unusedHelp in values:
                currentValue = options._config.get(parm_ini_map[name][PIMapSect], \
                                         parm_ini_map[name][PIMapOpt])

                # Populate the rows with the details and add them to the table.
                if fldtype == "text":
                   newConfigRow1 = configTextRow1.clone()
                   newConfigRow1.label = label
                   newConfigRow1.input.name = name
                   newConfigRow1.input.value = currentValue
                elif fldtype == "rb":
                   newConfigRow1 = configRbRow1.clone()
                   newConfigRow1.label = label
                   newConfigRow1.inputT.name = name
                   newConfigRow1.inputF.name = name
                   if currentValue == "True":
                      newConfigRow1.inputT.checked = "checked"
                   elif currentValue == "False":
                      newConfigRow1.inputF.checked = "checked"
                elif fldtype == "cb":
                   newConfigRow1 = configCbRow1.clone()
                   newConfigRow1.label = label
                   blankOption = newConfigRow1.input.clone()
                   firstOpt = True
                   i = 0
                   for val in validInput:
                      newOption = blankOption.clone()
                      newOption.val_label = val
                      newOption.input_box.name = name + '-' + str(i)
                      i += 1
                      newOption.input_box.value = val
                      if val in currentValue.split():
                         newOption.input_box.checked = "checked"
                      if firstOpt:
                         newConfigRow1.input = newOption
                         firstOpt = False
                      else:
                         newConfigRow1.input += newOption
                    
                # If this is the first row, insert the help text in a cell
                # with a `rowspan` that covers all the rows.
                if isFirstRow:
                    entries = []
                    for name, topic, type, vals, help in values:
                        entries.append("<p><b>%s: </b>%s</p>" % (topic, help))
                    newConfigRow1.helpSpacer = '&nbsp;' * 10
                    newConfigRow1.helpCell = '\n'.join(entries)
                else:
                    del newConfigRow1.helpSpacer
                    del newConfigRow1.helpCell

                newConfigRow2 = configRow2.clone()
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

        for name, value in parms.items():
           if name in parm_ini_map.keys():
              options._config.set(parm_ini_map[name][PIMapSect], \
                                  parm_ini_map[name][PIMapOpt], value)
           
        op = open(optionsPathname, "r")
        options._config.update_file(op)
        options._update()
        op.close()
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
    # This is really a bit of a kludge, and a nicer solution would
    # be most welcome.  Most especially, note that this will fall
    # apart if there are more than 9 checkboxes in an option, or
    # if "-" appears as the second-to-last character in an option
    # value
    for name, value in parms.items():
       if name[-2:-1] == '-':
          if parms.has_key(name[:-2]):
             parms[name[:-2]] += ' ' + value
          else:
             parms[name[:-2]] = value
          del parms[name]

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
        parms['p3addid'] = "" # checkboxes need a default!
        aid = parms['p3addid']
            
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

def restoreIniDefaults():
    # Get the pathname of the ini file as discovered by the Options module.
    # note that the behaviour of this function has subtly changed
    # previously options were removed from the config file, now the config
    # file is updated to match the defaults
    inipath = optionsPathname

    c = ConfigParser()
    d = StringIO(defaults)
    c.readfp(d)
    del d

    # Only restore the settings that appear on the form.
    for section, option in parm_ini_map.values():
        if option not in noRestore:
            try:
               options._config.set(section, option,
                                    c.get(section,option))
            except NoSectionError:
                pass    # Already missing.
    op = open(inipath)
    options._config.update_file(op)
    options._update()
    op.close()
