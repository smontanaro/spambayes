"""Options Configurator
Classes:
    OptionsConfigurator - changes select values in Options.py

Abstract:

This module implements a browser based Spambayes option file configuration
utility.  Users may use the pages in this application to customize the
settings in the bayescustomize.ini file.

This does not support the BAYESCUSTOMIZE environment variable.  Is this even
used anywhere?

To execute this module, just invoke OptionConfig.py <optional port number>
The port number is the port the http server will listen on, and defaults to 
8000.  Then point your browser at http://locahost:8000 (or whatever port you
chose).

To Do:
    o Suggestions?

"""

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tim Stone <tim@fourstonesExpressions.com>"

import SmarterHTTPServer
import BaseHTTPServer
from spambayes.Options import options
import re
import os
import ConfigParser
import copy

# This control dictionary maps http request parameters and template fields
# to ConfigParser sections and options.  The key matches both the input
# field that corresponds to a section/option, and also the <<PY-...>> template
# variable that is used to display the value of that section/option.
parm_ini_map = \
   {'hamcutoff':    ('TestDriver', 'ham_cutoff'),
    'spamcutoff':   ('TestDriver', 'spam_cutoff'),
    'dbname':       ('pop3proxy',  'pop3proxy_persistent_storage_file'),
    'headername':   ('Hammie',     'hammie_header_name'),
    'spamstring':   ('Hammie',     'header_spam_string'),
    'hamstring':    ('Hammie',     'header_ham_string'),
    'unsurestring': ('Hammie',     'header_unsure_string'),
    'p3servers':    ('pop3proxy',  'pop3proxy_servers'),
    'p3ports':      ('pop3proxy',  'pop3proxy_ports'),
    'p3hamdir':     ('pop3proxy',  'pop3proxy_ham_cache'),
    'p3spamdir':    ('pop3proxy',  'pop3proxy_spam_cache'),
    'p3unknowndir': ('pop3proxy',  'pop3proxy_unknown_cache')
   }

PIMapSect = 0
PIMapOpt = 1

class OptionsConfigurator(SmarterHTTPServer.SmarterHTTPRequestHandler):
    def homepage(self, parms):

        self.send_header("Content-type", 'text/html')

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

        bcini.read('bayescustomize.ini')

        html = templateGet('ocHome.html')

        for httpparm in parm_ini_map:
            html = templateSub(html, 'PY-%s' % (httpparm), \
                      bcini.get(parm_ini_map[httpparm][PIMapSect], \
                                parm_ini_map[httpparm][PIMapOpt]))

        html = addSbLookAndFeel(html)

        html = templateSub(html, 'PY-TITLE', \
           'Spambayes Options Configurator: Home')
        html = templateSub(html, 'PY-SBLAFNAV', \
           'Spambayes Options Configurator: Home')

        html = addSbFooter(html)

        html = templateSub(html, 'PY-FOOTERTITLE', \
           '<A href="/">Spambayes Options Configuration</A>')

        return html

    def changeopts(self,parms):

        self.send_header("Content-type", 'text/html')

        errmsg = editInput(parms)

        if errmsg != '':
            html = templateGet('ocError.html')
            html = templateSub(html, 'PY-ERROR', errmsg)

            html = addSbLookAndFeel(html)

            html = templateSub(html, 'PY-TITLE', \
               'Spambayes Options Configurator: Home > Error')
            html = templateSub(html, 'PY-SBLAFNAV', \
               'Spambayes Options Configurator: \
               <a href="homepage.methlet">Home</a> > Error')

            html = addSbFooter(html)

            html = templateSub(html, 'PY-FOOTERTITLE', \
               '<A href="homepage.methlet">Spambayes Options Configuration</A>')

            return html

        updateIniFile(parms)

        html = templateGet('ocChanged.html')

        html = addSbLookAndFeel(html)

        html = templateSub(html, 'PY-TITLE', \
           'Spambayes Options Configurator: Home > Options Changed')
        html = templateSub(html, 'PY-SBLAFNAV', \
           'Spambayes Options Configurator: \
           <a href="/">Home</a> > Options Changed')

        html = addSbFooter(html)

        html = templateSub(html, 'PY-FOOTERTITLE', \
           '<A href="/">Spambayes Options Configuration</A>')

        return html

    def restoredflts(self, parms):
        restoreIniDefaults()

        html = templateGet('ocDefault.html')

        html = addSbLookAndFeel(html)

        html = templateSub(html, 'PY-TITLE', \
           'Spambayes Options Configurator: Home > Defaults Restored')
        html = templateSub(html, 'PY-SBLAFNAV', \
           'Spambayes Options Configurator: \
           <a href="/">Home</a> > Defaults Restored')

        html = addSbFooter(html)

        html = templateSub(html, 'PY-FOOTERTITLE', \
           '<A href="/">Spambayes Options Configuration</A>')

        return html

def templateSub(mass, tmplvar, val):
    regex = '<<%s>>' % (tmplvar)
    hc = re.compile(regex, re.MULTILINE)
    return hc.sub('%s' % (val), mass)

def addSbLookAndFeel(str):
    sbstr = templateGet('sblookandfeel.thtml')
    return templateSub(str, 'PY-SBLOOKANDFEEL', sbstr)

def addSbFooter(str):
    ftstr = templateGet('sbfooter.thtml')
    return templateSub(str, 'PY-FOOTER', ftstr)

def editInput(parms):

    errmsg = ''

    # edit numericity of hamcutoff and spamcutoff
    try:
        hco = parms['hamcutoff'][0]
    except KeyError:
        hco = options.ham_cutoff

    try:
        sco = parms['spamcutoff'][0]
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
        errmsg += '<li>Spam cutoff must be a number, \
between 0 and 1</li>\n'

    # edit 0 <= hamcutoff < spamcutoff <= 1
    if hco < 0 or hco > 1:
        errmsg += '<li>Ham cutoff must be between 0 and 1</li>\n'
    if sco < 0 or sco > 1:
        errmsg += '<li>Spam cutoff must be between 0 and 1</li>\n'
    if not hco < sco:
        errmsg += '<li>Ham cutoff must be less than Spam cutoff</li>\n'

    # edit for equal number of pop3servers and ports
    try:
        slist = parms['p3servers'][0].split(',')
    except KeyError:
        slist = options.pop3proxy_servers.split(',')

    try:
        plist = parms['p3ports'][0].split(',')
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

    # assumes bayescustomize.ini is in this process' working directory

    inipath = os.path.abspath('bayescustomize.ini')

    bcini = ConfigParser.ConfigParser()
    bcini.read(inipath)

    for httpParm in parm_ini_map:
        map = parm_ini_map[httpParm]
        sect = map[PIMapSect]
        opt = map[PIMapOpt]

        try:
            val = parms[httpParm][0]
        except KeyError:
            continue

        try:
            bcini.add_section(sect)
        except ConfigParser.DuplicateSectionError:
            pass

        bcini.set(sect, opt, val)

    o = open(inipath, 'wb')
    bcini.write(o)
    o.close()

def restoreIniDefaults():

    # assumes bayescustomize.ini is in this process' working directory

    inipath = os.path.abspath('bayescustomize.ini')

    bcini = ConfigParser.ConfigParser()
    bcini.read(inipath)

    for sect in bcini.sections():
        for opt in bcini.options(sect):
            bcini.remove_option(sect, opt)

    o = open(inipath, 'wb')
    bcini.write(o)
    o.close()


ocHome = """
<<PY-SBLOOKANDFEEL>>
<DIV class="content">
<FORM action="changeopts.methlet" method="get">
<p>This page allows you to change certain customizable options that control
the way in which Spambayes processes your email.  Hover your mouse pointer
over an item name for an explanation of that item</p>
<TABLE class="sectiontable" cellspacing="0">
  <TBODY>
    <TR>
      <TD class="sectionheading">Statistics Options</TD>
    </TR>
    <TR>
      <TD class="sectionbody">

      <TABLE border="0" cellpadding="3">
        <TBODY>
          <TR>
            <TD align=right>
<span title="When the Spambayes classifier examines an email
 message, it calculates a probability that this mail is spam.
 This value defines the probability below which the classifier designates
 an email as ham, or desirable email.
 Adjusting this value to a larger number will result in more
 mail being classified as ham, with less certainty that all of
 them actually ARE ham.  Lowering this number will result in
 less mail being classified as ham, with greater certainty
 that they actually ARE ham.  This value should be between 0
 and 1, and should be smaller than the Spam cutoff number.">
               Ham cutoff
               </span>
            </TD>
            <TD>Current Value: <<PY-hamcutoff>><br>
              <INPUT type="text" size=5 name="hamcutoff" value="">
            </TD>
          </TR>
          <TR>
            <TD align=right>
<span title="When the Spambayes classifier examines an email
 message, it calculates a probability that this mail is spam.
 This value defines the probability above which the classifier designates
 an email as spam, or undesirable email.
 Adjusting this value to a larger number will result in less
 mail being classified as ham, with greater certainty that all of
 them actually ARE spam.  Lowering this number will result in
 more mail being classified as ham, with less certainty
 that they actually ARE spam.  This value should be between 0
 and 1, and should be larger than the Ham cutoff number.">
              Spam cutoff
              </span>
            </TD>
            <TD>Current Value: <<PY-spamcutoff>><br>
              <INPUT type="text" size=5 name="spamcutoff" value="">
            </TD>
          </TR>
          <TR>
            <TD align=right>
<span title="Spambayes uses information that it gathers from incoming emails
 and from you, the user, to get better and better at classifying your email.
 To do this, it accumulates information in a file, which is used on an ongoing
 basis to perform classifications.  When you train the database, by telling
 Spambayes how YOU classify your emails, it supplements the information in
 its database with the new information you've given it.  This item specifies
 the name of the file that this information is kept in.  The default value
 should work just fine, but you may change it to any valid filename that you
 wish.">
              Database file name
              </span>
            </TD>
            <TD>Current Value: <<PY-dbname>><br>
              <INPUT type="text" name="dbname" value="">
            </TD>
          </TR>
        </TBODY>
      </TABLE>
      </TD>
    </TR>
  </TBODY>
</TABLE>
<br>
<TABLE class="sectiontable" cellspacing="0">
  <TBODY>
    <TR>
      <TD class="sectionheading">Inserted Header Options</TD>
    </TR>
    <TR>
      <TD class="sectionbody">
      <TABLE border="0" cellpadding="3">
        <TBODY>
          <TR>
            <TD align=right>
<span title="Spambayes documents its classification of each email by inserting
 a line into the email's headers.  This line can then be used by your email
 client (provided that your client supports filtering) to move spam into
 a separate folder (recommended), delete it (not recommended), or take any
 other action that is supported by the filtering mechanism in your email
 client.  This item specifies the name of the header that Spambayes will
 insert into each email's headers.  The default value should work just fine,
 but you may change it to anything that you wish.">
              Header Name
              </span>
            </TD>
            <TD>Current Value: <<PY-headername>><br>
              <INPUT type="text" size=30 name="headername" value="">
            </TD>
          </TR>
          <TR>
            <TD align=right>
<span title="The header that Spambayes inserts into each email has a name,
 Header Name (above), and a value.  If the classifier determines that this
 email is probably spam, it places a header named as above with a value as
 specified by this string.  The default value should work just fine, but you
 may change it to anything that you wish.">
              Spam Designation
              </span>
            </TD>
            <TD>Current Value: <<PY-spamstring>><br>
              <INPUT type="text" size=10 name="spamstring" value="">
            </TD>
          </TR>
          <TR>
            <TD align=right>
<span title="The header that Spambayes inserts into each email has a name,
 Header Name (above), and a value.  If the classifier determines that this
 email is probably ham, it places a header named as above with a value as
 specified by this string.  The default value should work just fine, but you
 may change it to anything that you wish.">
              Ham Designation
              </span>
            </TD>
            <TD>Current Value: <<PY-hamstring>><br>
              <INPUT type="text" size=10 name="hamstring" value="">
            </TD>
          </TR>
          <TR>
            <TD align=right>
<span title="The header that Spambayes inserts into each email has a name,
 Header Name (above), and a value.  If the classifier cannot determine if this
 email is probably ham or spam, it places a header named as above with a value
 as specified by this string.  This lets you know that the classifier could not
 determine with any certainty what this email was.  Emails that have this
 classification should always be the subject of training.  The default value
 should work just fine, but you may change it to anything that you wish.">
              Unsure Designation
              </span>
            </TD>
            <TD>Current Value: <<PY-unsurestring>><br>
              <INPUT type="text" size=10 name="unsurestring" value="">
            </TD>
          </TR>
        </TBODY>
      </TABLE>
      </TD>
    </TR>
  </TBODY>
</TABLE>
<br>
<TABLE class="sectiontable" cellspacing="0">
  <TBODY>
    <TR>
      <TD class="sectionheading">POP3 Options</TD>
    </TR>
    <TR>
      <TD class="sectionbody">
      <TABLE border="0" cellpadding="3">
        <TBODY>
          <TR>
            <TD align=right>
<span title="The Spambayes POP3 proxy is designed to intercept incoming email
 and classify it before sending it on to your email client.  To do this, you
 must specify which pop3 server(s) you wish it to intercept.  This item is
 where you configure the proxy to monitor these server(s).  If there are more
 than one server, then simply separate them with commas.  These must be valid
 POP3 server names.  If you already have your email client configured and
 running, you can get these server names its configuration pages.  If you are
 setting up a new email POP3 account, your ISP or email provider can supply
 you with this information.  If you are using Web-based email, the Spambayes
 POP3 proxy cannot be used.">
              Servers
              </span>
            </TD>
            <TD>Current Value: <<PY-p3servers>><br>
              <INPUT type="text" size=80 name="p3servers" value="">
            </TD>
          </TR>
          <TR>
            <TD align=right>
<span title="Each POP3 server that is being monitored must be assigned to a
 'port' in the Spambayes POP3 proxy.  This port must be different for each
 monitored server, and there MUST be a port for each monitored server.  See
 the Spambayes POP3 proxy documentation for information on how your email
 client is configured to use these ports.  If there are multiple servers,
 you must specify the same number of ports, separated by commas.">
              Ports
              </span>
            </TD>
            <TD>Current Value: <<PY-p3ports>><br>
              <INPUT type="text" size=30 name="p3ports" value="">
            </TD>
          </TR>
          <TR>
            <TD align=right>
<span title="When you train the Spambayes database, by telling it which emails
 you consider to be ham and spam, it not only updates its database, but it 
 remembers those particular mails in a subdirectory.  This is so that your
 database can be retrained in the event that the Spambayes database is lost,
 for whatever reason. This item specifies the name of the directory that ham
 is remembered in.  The default value should work just fine, but you may change
 it to any valid directory name that you wish.">
              Ham Directory
              </span>
            </TD>
            <TD>Current Value: <<PY-p3hamdir>><br>
              <INPUT type="text" size=30 name="p3hamdir" value="">
            </TD>
          </TR>
          <TR>
            <TD align=right>
<span title="When you train the Spambayes database, by telling it which emails
 you consider to be ham and spam, it not only updates its database, but it
 remembers those particular mails in a subdirectory.  This is so that your
 database can be retrained in the event that the Spambayes database is lost,
 for whatever reason. This item specifies the name of the directory that spam
 is remembered in.  The default value should work just fine, but you may change
 it to any valid directory name that you wish.">
              Spam Directory</TD>
            <TD>Current Value: <<PY-p3spamdir>><br>
              <INPUT type="text" size=30 name="p3spamdir" value="">
            </TD>
          </TR>
          <TR>
            <TD align=right>
<span title="When the POP3 proxy intercepts incoming mail, it remembers it
 in a special directory so that you can go back at a later time and train the
 database using the mail.  This item specifies the name of that directory.  The
 default value should work just fine, but you may change it to any valid
 directory name that you wish.">
              Untrained Mail Directory</TD>
            <TD>Current Value: <<PY-p3unknowndir>><br>
              <INPUT type="text" size=30 name="p3unknowndir" value="">
            </TD>
          </TR>
        </TBODY>
      </TABLE>
      </TD>
    </TR>
  </TBODY>
</TABLE>
<center>
  <input type=submit name=how value="Save">
</center>
</FORM>
<br>
<FORM action="restoredflts.methlet" method="get">
<center>
  <input type=submit name=how value="Restore Defaults">
</center>
</FORM>
</DIV>
<<PY-FOOTER>>
"""

ocChanged = """
<<PY-SBLOOKANDFEEL>>
<DIV class="content">
<TABLE class="sectiontable" cellspacing="0">
  <TBODY>
    <TR>
      <TD class="sectionheading">Options Changed</TD>
    </TR>
    <TR>
      <TD class="sectionbody">
         The options changes you've made have been recorded.  You will need to
         restart any Spambayes processes you have running, such as the
         pop3proxy, in order for your changes to take effect.  When you
         return to the Options Configuration homepage, you may need to
         refresh the page to see the changes you have made.
      </TD>
    </TR>
  </TBODY>
</TABLE>
</DIV>
<<PY-FOOTER>>
"""

ocDefault = """
<<PY-SBLOOKANDFEEL>>
<DIV class="content">
<TABLE class="sectiontable" cellspacing="0">
  <TBODY>
    <TR>
      <TD class="sectionheading">Option Defaults Restored</TD>
    </TR>
    <TR>
      <TD class="sectionbody">
         All options have been reverted to their default values.  You
         will need to restart any Spambayes processes you have running,
         such as the pop3proxy, in order for your changes to take effect.
         When you return to the Options Configuration homepage, you may
         need to refresh the page to see the changes you have made.
      </TD>
    </TR>
  </TBODY>
</TABLE>
</DIV>
<<PY-FOOTER>>
"""

ocError = """
<<PY-SBLOOKANDFEEL>>
<DIV class="content">
<TABLE class="sectiontable" cellspacing="0">
  <TBODY>
    <TR>
      <TD class="sectionheading">Errors Detected</TD>
    </TR>
    <TR>
      <TD class="sectionbody">
         <ul>
         <<PY-ERROR>>
         </ul>
      </TD>
    </TR>
  </TBODY>
</TABLE>
</DIV>
<<PY-FOOTER>>
"""

sbLAF = """
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<HTML>
<HEAD>
<META http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
<META name="GENERATOR" content="IBM WebSphere Studio Homepage Builder V6.0.0 for Windows">
<META http-equiv="Content-Style-Type" content="text/css">
<TITLE><<PY-TITLE>></TITLE>
<STYLE>
<!--
             body {
  font: 90% arial, swiss, helvetica;
  margin: 0 ;
}
table {
  font: 90% arial, swiss, helvetica ;
}
form {
  margin: 0 ;
}
.banner {
  background: #c0e0ff;
  padding=5;
  padding-left: 15;
  border-top: 1px solid black;
  border-bottom: 1px solid black ;
}
.header {
  font-size: 133% ;
}
.content {
  margin: 15 ;
}
.messagetable td {
  padding-left: 1ex;
  padding-right: 1ex ;
}
.sectiontable {
  border: 1px solid #808080;
  width: 95% ;
}
.sectionheading {
  background: fffae0;
  padding-left: 1ex;
  border-bottom: 1px solid #808080;
  font-weight: bold ;
}
.sectionbody {
  padding: 1em ;
}
.reviewheaders a {
  color: #000000 ;
}
.stripe_on td {
  background: #f4f4f4 ;
}
-->
</STYLE>
</HEAD>
<BODY>
<DIV class="banner">
<IMG src="helmet.gif" align="absmiddle">&nbsp;
<SPAN class="header"><<PY-SBLAFNAV>></SPAN>
</DIV>
"""

sbFoot = """
<br>
<TABLE width="100%" cellspacing="0">
  <TBODY>
    <TR>
      <TD class="banner"><<PY-FOOTERTITLE>></TD>
      <TD align="right" class="banner"><A href="http://www.spambayes.org/">Spambayes.org</A></TD>
    </TR>
  </TBODY>
</TABLE>
</BODY>
</HTML>
"""

# This control dictionary is used to locate html within this or another
# module.  It maps a filename to an attribute, which is used to acquire
# content when a url references a resource named in the dictionary.
#
# A filename could be mapped to a variable or a function, either within
# this module or in a separate module (which would have to be imported)
localFiles = {'ocHome.html':ocHome, \
             'ocChanged.html':ocChanged, \
             'ocDefault.html':ocDefault, \
             'ocError.html':ocError, \
             'sblookandfeel.thtml':sbLAF, \
             'sbfooter.thtml':sbFoot}

def templateGet(filename):
    try:
        str = localFiles[filename]
    except KeyError:
        try:
            f = open(filename, 'rb')
        except IOError:
            str = 'Template file %s Not Found' % (filename)
        else:
            str = f.read()
            f.close()

    return str

def run(HandlerClass = OptionsConfigurator,
         ServerClass = BaseHTTPServer.HTTPServer):
    BaseHTTPServer.test(HandlerClass, ServerClass)

if __name__ == '__main__':
    run()
