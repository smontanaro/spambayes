"""Web User Interface

Classes:
    UserInterfaceServer - Implements the web server component
                          via a Dibbler plugin.
    BaseUserInterface - Just has utilities for creating boxes and so forth.
                        (Does not include any pages)
    UserInterface - A base class for Spambayes web user interfaces.

Abstract:

This module implements a browser based Spambayes user interface.  Users can
*not* use this class (there is no 'home' page), but developments should
sub-class it to provide an appropriate interface for their application.

Functions deemed appropriate for all application interfaces are included.
These currently include:
  onClassify - classify a given message
  onWordquery - query a word from the database
  onTrain - train a message or mbox
  onSave - save the database and possibly shutdown
  onConfig - present the appropriate configuration page
  onAdvancedconfig - present the appropriate advanced configuration page
  onExperimentalconfig - present the experimental options configuration page
  onHelp - present the help page
  onStats - present statistics information
  onBugreport - help the user fill out a bug report

To Do:

Web training interface:

 o Functional tests.
 o Keyboard navigation (David Ascher).  But aren't Tab and left/right
   arrow enough?


User interface improvements:

 o Once the pieces are on separate pages, make the paste box bigger.
 o Deployment: Windows executable?  atlaxwin and ctypes?  Or just
   webbrowser?
 o Save the stats (num classified, etc.) between sessions.
 o "Reload database" button.
 o Displaying options should be done with the locale format function
   rather than str().
 o Suggestions?

"""

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

# This module was once part of pop3proxy.py; if you are looking through
# the history of the file, you may need to go back there.
# The options/configuration section started life in OptionConfig.py.
# You can find this file in the cvs attic if you want to trawl through
# its history.

__author__ = """Richie Hindle <richie@entrian.com>,
                Tim Stone <tim@fourstonesExpressions.com>"""
__credits__ = "Tim Peters, Neale Pickett, Tony Meyer, all the Spambayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

import re
import os
import sys
import time
import email
import smtplib
import binascii
import cgi
import mailbox
import types
import StringIO

import oe_mailbox

import PyMeldLite
import Version
import Dibbler
import tokenizer
from spambayes import Stats
from spambayes import Version
from Options import options, optionsPathname, defaults, OptionsClass

IMAGES = ('helmet', 'status', 'config', 'help',
          'message', 'train', 'classify', 'query')

experimental_ini_map = (
    ('Experimental Options', None),
)

# Dynamically add any current experimental options.
# (Don't add deprecated options, or, more specifically, any
# options whose description starts with (DEPRECATED)).
for opt in options.options(True):
    sect, opt = opt[1:].split(']', 1)
    if opt[:2].lower() == "x-" and \
       not options.doc(sect, opt).lower().startswith("(deprecated)"):
        experimental_ini_map += ((sect, opt),)

class UserInterfaceServer(Dibbler.HTTPServer):
    """Implements the web server component via a Dibbler plugin."""

    def __init__(self, uiPort):
        Dibbler.HTTPServer.__init__(self, uiPort)
        print 'User interface url is http://localhost:%d/' % (uiPort)

    def requestAuthenticationMode(self):
        return options["html_ui", "http_authentication"]

    def getRealm(self):
        return "SpamBayes Web Interface"

    def isValidUser(self, name, password):
        return (name == options["html_ui", "http_user_name"] and
                password == options["html_ui", "http_password"])

    def getPasswordForUser(self, name):
        # There is only one login available in the web interface.
        return options["html_ui", "http_password"]

    def getCancelMessage(self):
        return "You must login to use SpamBayes."""


class BaseUserInterface(Dibbler.HTTPPlugin):
    def __init__(self):
        Dibbler.HTTPPlugin.__init__(self)
        htmlSource, self._images = self.readUIResources()
        self.html = PyMeldLite.Meld(htmlSource, readonly=True)
        self.app_for_version = None

    def onIncomingConnection(self, clientSocket):
        """Checks the security settings."""
        remoteIP = clientSocket.getpeername()[0]
        trustedIPs = options["html_ui", "allow_remote_connections"]

        if trustedIPs == "*" or remoteIP == clientSocket.getsockname()[0]:
            return True

        trustedIPs = trustedIPs.replace('.', '\.').replace('*', '([01]?\d\d?|2[04]\d|25[0-5])')
        for trusted in trustedIPs.split(','):
            if re.search("^" + trusted + "$", remoteIP):
                return True

        return False

    def _getHTMLClone(self, help_topic=None):
        """Gets a clone of the HTML, with the footer timestamped, and
        version information added, ready to be modified and sent to the
        browser."""
        clone = self.html.clone()
        timestamp = time.strftime('%H:%M on %A %B %d %Y', time.localtime())
        clone.footer.timestamp = timestamp
        clone.footer.version = Version.get_version_string(self.app_for_version)
        if help_topic:
            clone.helplink.href = "help?topic=%s" % (help_topic,)
        return clone

    def _writePreamble(self, name, parent=None, showImage=True):
        """Writes the HTML for the beginning of a page - time-consuming
        methlets use this and `_writePostamble` to write the page in
        pieces, including progress messages.  `parent` (if given) should
        be a pair: `(url, label)`, eg. `('review', 'Review')`."""

        # Take the whole palette and remove the content and the footer,
        # leaving the header and an empty body.
        html = self._getHTMLClone()
        html.mainContent = " "
        del html.footer

        # Add in the name of the page and remove the link to Home if this
        # *is* Home.
        html.title = name
        if name == 'Home':
            del html.homelink
            html.pagename = "Home"
        elif parent:
            html.pagename = "> <a href='%s'>%s</a> > %s" % \
                            (parent[0], parent[1], name)
        else:
            html.pagename = "> " + name

        # Remove the helmet image if we're not showing it - this happens on
        # shutdown because the browser might ask for the image after we've
        # exited.
        if not showImage:
            del html.helmet

        # Strip the closing tags, so we push as far as the start of the main
        # content.  We'll push the closing tags at the end.
        self.writeOKHeaders('text/html')
        self.write(re.sub(r'</div>\s*</body>\s*</html>', '', str(html)))

    def _writePostamble(self, help_topic=None):
        """Writes the end of time-consuming pages - see `_writePreamble`."""
        self.write("</div>" + self._getHTMLClone(help_topic).footer)
        self.write("</body></html>")

    def _trimHeader(self, field, limit, quote=False):
        """Trims a string, adding an ellipsis if necessary and HTML-quoting
        on request.  Also pumps it through email.Header.decode_header, which
        understands charset sections in email headers - I suspect this will
        only work for Latin character sets, but hey, it works for Francois
        Granger's name.  8-)"""

        try:
            sections = email.Header.decode_header(field)
        except (binascii.Error, email.Errors.HeaderParseError):
            sections = [(field, None)]
        field = ' '.join([text for text, unused in sections])
        if len(field) > limit:
            field = field[:limit-3] + "..."
        if quote:
            field = cgi.escape(field)
        return field

    def onHome(self):
        """Serve up the homepage."""
        raise NotImplementedError

    def _writeImage(self, image):
        self.writeOKHeaders('image/gif')
        self.write(self._images[image])

    # If you are easily offended, look away now...
    for imageName in IMAGES:
        exec "def %s(self): self._writeImage('%s')" % \
             ("on%sGif" % imageName.capitalize(), imageName)

    def _buildBox(self, heading, icon, content):
        """Builds a yellow-headed HTML box."""
        box = self.html.headedBox.clone()
        box.heading = heading
        if icon:
            box.icon.src = icon
        else:
            del box.iconCell
        box.boxContent = content
        return box

    def readUIResources(self):
        """Returns ui.html and a dictionary of Gifs."""

        # Using `exec` is nasty, but I couldn't figure out a way of making
        # `getattr` or `__import__` work with ResourcePackage.
        from spambayes.resources import ui_html
        images = {}
        for baseName in IMAGES:
            moduleName = '%s.%s_gif' % ('spambayes.resources', baseName)
            module = __import__(moduleName, {}, {}, ('spambayes', 'resources'))
            images[baseName] = module.data
        return ui_html.data, images


class UserInterface(BaseUserInterface):
    """Serves the HTML user interface."""

    def __init__(self, bayes, config_parms=(), adv_parms=()):
        """Load up the necessary resources: ui.html and helmet.gif."""
        BaseUserInterface.__init__(self)
        self.classifier = bayes
        self.parm_ini_map = config_parms
        self.advanced_options_map = adv_parms
        self.app_for_version = None # subclasses must fill this in

    def onClassify(self, file, text, which):
        """Classify an uploaded or pasted message."""
        message = file or text
        message = message.replace('\r\n', '\n').replace('\r', '\n') # For Macs
        results = self._buildCluesTable(message)
        results.classifyAnother = self._buildClassifyBox()
        self._writePreamble("Classify")
        self.write(results)
        self._writePostamble()

    ev_re = re.compile("%s:(.*?)(?:\n\S|\n\n)" % \
                       re.escape(options["Headers",
                                         "evidence_header_name"]),
                       re.DOTALL)
    sc_re = re.compile("%s:\s*([\d.]+)" % \
                       re.escape(options["Headers", "score_header_name"]))

    def _fillCluesTable(self, clues):
        accuracy = 6
        cluesTable = self.html.cluesTable.clone()
        cluesRow = cluesTable.cluesRow.clone()
        del cluesTable.cluesRow   # Delete dummy row to make way for real ones
        fetchword = self.classifier._wordinfoget
        for word, wordProb in clues:
            record = fetchword(word)
            if record:
                nham = record.hamcount
                nspam = record.spamcount
                if wordProb is None:
                    wordProb = self.classifier.probability(record)
            elif word != "*H*" and word != "*S*":
                nham = nspam = 0
            else:
                nham = nspam = "-"
            if wordProb is None:
                wordProb = "-"
            else:
                wordProb = round(float(wordProb), accuracy)
            cluesTable += cluesRow % (cgi.escape(word), wordProb,
                                      nham, nspam)
        return cluesTable

    def _buildCluesTable(self, message, subject=None, show_tokens=False):
        tokens = list(tokenizer.tokenize(message))
        if show_tokens:
            clues = [(tok, None) for tok in tokens]
            probability = self.classifier.spamprob(tokens)
            cluesTable = self._fillCluesTable(clues)
            head_name = "Tokens"
        else:
            (probability, clues) = self.classifier.spamprob(tokens, evidence=True)
            cluesTable = self._fillCluesTable(clues)
            head_name = "Clues"

        results = self.html.classifyResults.clone()
        results.probability = "%.2f%% (%s)" % (probability*100, probability)
        if subject is None:
            heading = "%s: (%s)" % (head_name, len(clues))
        else:
            heading = "%s for: %s (%s)" % (head_name, subject, len(clues))
        results.cluesBox = self._buildBox(heading, 'status.gif', cluesTable)
        if not show_tokens:
            mo = self.sc_re.search(message)
            if mo:
                # Also display the score the message received when it was
                # classified.
                prob = float(mo.group(1).strip())
                results.orig_prob_num = "%.2f%% (%s)" % (prob*100, prob)
            else:
                del results.orig_prob
            mo = self.ev_re.search(message)
            if mo:
                # Also display the clues as they were when the message was
                # classified.
                clues = []
                evidence = re.findall(r"'(.+?)': ([^;]+)(?:;|$)", mo.group(1))
                for word, prob in evidence:
                    clues.append((word, prob))
                cluesTable = self._fillCluesTable(clues)

                if subject is None:
                    heading = "Original clues: (%s)" % (len(evidence),)
                else:
                    heading = "Original clues for: %s (%s)" % (subject,
                                                               len(evidence),)
                orig_results = self._buildBox(heading, 'status.gif',
                                              cluesTable)
                results.cluesBox += orig_results
        else:
            del results.orig_prob
        return results

    def onWordquery(self, word, query_type="basic", max_results='10',
                    ignore_case=False):
        # It would be nice if the default value for max_results here
        # always matched the value in ui.html.
        try:
            max_results = int(max_results)
        except ValueError:
            # Ignore any invalid number, like "foo"
            max_results = 10

        original_word = word

        query = self.html.wordQuery.clone()
        query.word.value = "%s" % (word,)
        for q_type in [query.advanced.basic,
                               query.advanced.wildcard,
                               query.advanced.regex]:
            if query_type == q_type.id:
                q_type.checked = 'checked'
                if query_type != "basic":
                    del query.advanced.max_results.disabled
        if ignore_case:
            query.advanced.ignore_case.checked = 'checked'
        query.advanced.max_results.value = str(max_results)
        queryBox = self._buildBox("Word query", 'query.gif', query)
        if not options["html_ui", "display_adv_find"]:
            del queryBox.advanced

        stats = []
        if word == "":
            stats.append("You must enter a word.")
        elif query_type == "basic" and not ignore_case:
            wordinfo = self.classifier._wordinfoget(word)
            if wordinfo:
                stat = (word, wordinfo.spamcount, wordinfo.hamcount,
                        self.classifier.probability(wordinfo))
            else:
                stat = "%r does not exist in the database." % \
                       cgi.escape(word)
            stats.append(stat)
        else:
            if query_type != "regex":
                word = re.escape(word)
            if query_type == "wildcard":
                word = word.replace("\\?", ".")
                word = word.replace("\\*", ".*")

            flags = 0
            if ignore_case:
                flags = re.IGNORECASE
            r = re.compile(word, flags)

            reached_limit = False
            for w in self.classifier._wordinfokeys():
                if not reached_limit and len(stats) >= max_results:
                    reached_limit = True
                    over_limit = 0
                if r.match(w):
                    if reached_limit:
                        over_limit += 1
                    else:
                        wordinfo = self.classifier._wordinfoget(w)
                        stat = (w, wordinfo.spamcount, wordinfo.hamcount,
                                self.classifier.probability(wordinfo))
                        stats.append(stat)
            if len(stats) == 0 and max_results > 0:
                stat = "There are no words that begin with '%s' " \
                        "in the database." % (word,)
                stats.append(stat)
            elif reached_limit:
                if over_limit == 1:
                    singles = ["was", "match", "is"]
                else:
                    singles = ["were", "matches", "are"]
                stat = "There %s %d additional %s that %s not " \
                       "shown here." % (singles[0], over_limit,
                                        singles[1], singles[2])
                stats.append(stat)

        self._writePreamble("Word query")
        if len(stats) == 1:
            if isinstance(stat, types.TupleType):
                stat = self.html.wordStats.clone()
                word = stats[0][0]
                stat.spamcount = stats[0][1]
                stat.hamcount = stats[0][2]
                stat.spamprob = "%.6f" % stats[0][3]
            else:
                stat = stats[0]
                word = original_word
            row = self._buildBox("Statistics for '%s'" % \
                                 cgi.escape(word),
                                 'status.gif', stat)
            self.write(row)
        else:
            page = self.html.multiStats.clone()
            page.multiTable = "" # make way for the real rows
            page.multiTable += self.html.multiHeader.clone()
            stripe = 0
            for stat in stats:
                if isinstance(stat, types.TupleType):
                    row = self.html.statsRow.clone()
                    row.word, row.spamcount, row.hamcount = stat[:3]
                    row.spamprob = "%.6f" % stat[3]
                    setattr(row, 'class', ['stripe_on', 'stripe_off'][stripe])
                    stripe = stripe ^ 1
                    page.multiTable += row
                else:
                    self.write(self._buildBox("Statistics for '%s'" % \
                                              cgi.escape(original_word),
                                              'status.gif', stat))
            self.write(self._buildBox("Statistics for '%s'" % \
                                      cgi.escape(original_word), 'status.gif',
                                      page))
        self.write(queryBox)
        self._writePostamble()

    def onTrain(self, file, text, which):
        """Train on an uploaded or pasted message."""
        self._writePreamble("Train")

        # Upload or paste?  Spam or ham?
        content = file or text
        isSpam = (which == 'Train as Spam')

        # Attempt to convert the content from a DBX file to a standard mbox
        if file:
            content = self._convertToMbox(content)

        # Convert platform-specific line endings into unix-style.
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # The upload might be a single message or am mbox file.
        messages = self._convertUploadToMessageList(content)

        # Append the message(s) to a file, to make it easier to rebuild
        # the database later.   This is a temporary implementation -
        # it should keep a Corpus of trained messages.
        if isSpam:
            f = open("_pop3proxyspam.mbox", "a")
        else:
            f = open("_pop3proxyham.mbox", "a")

        # Train on the uploaded message(s).
        self.write("<b>Training...</b>\n")
        self.flush()
        for message in messages:
            tokens = tokenizer.tokenize(message)
            self.classifier.learn(tokens, isSpam)
            f.write("From pop3proxy@spambayes.org Sat Jan 31 00:00:00 2000\n")
            f.write(message)
            f.write("\n\n")

        # Save the database and return a link Home and another training form.
        f.close()
        self._doSave()
        self.write("<p>OK. Return <a href='home'>Home</a> or train again:</p>")
        self.write(self._buildTrainBox())
        self._writePostamble()

    def _convertToMbox(self, content):
        """Check if the given buffer is in a non-mbox format, and convert it
        into mbox format if so.  If it's already an mbox, return it unchanged.

        Currently, the only supported non-mbox format is Outlook Express DBX.
        In such a case we use the module oe_mailbox to convert the DBX
        content into a standard mbox file.  Testing if the file is a
        DBX one is very quick (just a matter of checking the first few
        bytes), and should not alter the overall performance."""
        content = oe_mailbox.convertToMbox(content)
        return content

    def _convertUploadToMessageList(self, content):
        """Returns a list of raw messages extracted from uploaded content.
        You can upload either a single message or an mbox file."""
        if content.startswith('From '):
            # Get a list of raw messages from the mbox content.
            class SimpleMessage:
                def __init__(self, fp):
                    self.guts = fp.read()
            contentFile = StringIO.StringIO(content)
            mbox = mailbox.PortableUnixMailbox(contentFile, SimpleMessage)
            return map(lambda m: m.guts, mbox)
        else:
            # Just the one message.
            return [content]

    def _doSave(self):
        """Saves the database."""
        self.write("<b>Saving... ")
        self.flush()
        self.classifier.store()
        self.write("Done</b>.\n")

    def onSave(self, how):
        """Command handler for "Save" and "Save & shutdown"."""
        isShutdown = how.lower().find('shutdown') >= 0
        self._writePreamble("Save", showImage=(not isShutdown))
        self._doSave()
        if isShutdown:
            self.write("<p>%s</p>" % self.html.shutdownMessage)
            self.write("</div></body></html>")
            self.flush()
            ## Is this still required?: self.shutdown(2)
            self.close()
            raise SystemExit
        self._writePostamble()

    def _buildClassifyBox(self):
        """Returns a "Classify a message" box.  This is used on both the Home
        page and the classify results page.  The Classify form is based on the
        Upload form."""

        form = self.html.upload.clone()
        del form.or_mbox
        del form.submit_spam
        del form.submit_ham
        form.action = "classify"
        return self._buildBox("Classify a message", 'classify.gif', form)

    def _buildTrainBox(self):
        """Returns a "Train on a given message" box.  This is used on both
        the Home page and the training results page.  The Train form is
        based on the Upload form."""

        form = self.html.upload.clone()
        del form.submit_classify
        return self._buildBox("Train on a message, mbox file or dbx file",
                              'message.gif', form)

    def reReadOptions(self):
        """Called by the config page when the user saves some new options,
        or restores the defaults."""
        pass

    def onExperimentalconfig(self):
        html = self._buildConfigPage(experimental_ini_map)
        html.title = 'Home &gt; Experimental Configuration'
        html.pagename = '&gt; Experimental Configuration'
        html.adv_button.name.value = "Back to basic configuration"
        html.adv_button.action = "config"
        html.config_submit.value = "Save experimental options"
        html.restore.value = "Restore experimental options defaults (all off)"
        del html.exp_button
        self.writeOKHeaders('text/html')
        self.write(html)

    def onAdvancedconfig(self):
        html = self._buildConfigPage(self.advanced_options_map)
        html.title = 'Home &gt; Advanced Configuration'
        html.pagename = '&gt; Advanced Configuration'
        html.adv_button.name.value = "Back to basic configuration"
        html.adv_button.action = "config"
        html.config_submit.value = "Save advanced options"
        html.restore.value = "Restore advanced options defaults"
        del html.exp_button
        self.writeOKHeaders('text/html')
        self.write(html)

    def onConfig(self):
        html = self._buildConfigPage(self.parm_ini_map)
        html.title = 'Home &gt; Configure'
        html.pagename = '&gt; Configure'
        self.writeOKHeaders('text/html')
        self.write(html)

    def _buildConfigPage(self, parm_map):
        # Start with an empty config form then add the sections.
        html = self._getHTMLClone()
        # "Save and Shutdown" is confusing here - it means "Save database"
        # but that's not clear.
        html.shutdownTableCell = "&nbsp;"
        html.mainContent = self.html.configForm.clone()
        html.mainContent.configFormContent = ""
        html.mainContent.optionsPathname = optionsPathname
        return self._buildConfigPageBody(html, parm_map)

    def _buildConfigPageBody(self, html, parm_map):
        configTable = None
        section = None

        # Loop though the sections.
        for sect, opt in parm_map:
            # We need a string to use as the html key that we can change to
            # and from the sect, opt pair.  We like irony, so we use '_' as
            # the delimiter <wink>.
            if opt is None:
                if configTable is not None and section is not None:
                    # Finish off the box for this section and add it
                    # to the form.
                    section.boxContent = configTable
                    html.configFormContent += section
                # Start the yellow-headed box for this section.
                section = self.html.headedBox.clone()
                # Get a clone of the config table and a clone of each
                # example row, then blank out the example rows to make way
                # for the real ones.
                configTable = self.html.configTable.clone()
                configTextRow1 = configTable.configTextRow1.clone()
                configTextRow2 = configTable.configTextRow2.clone()
                configCbRow1 = configTable.configCbRow1.clone()
                configRow2 = configTable.configRow2.clone()
                blankRow = configTable.blankRow.clone()
                del configTable.configTextRow1
                del configTable.configTextRow2
                del configTable.configCbRow1
                del configTable.configRow2
                del configTable.blankRow
                del configTable.folderRow
                section.heading = sect
                del section.iconCell
                continue
            html_key = sect + '_' + opt

            # Populate the rows with the details and add them to the table.
            if type(options.valid_input(sect, opt)) in types.StringTypes:
                # we provide a text input
                newConfigRow1 = configTextRow1.clone()
                newConfigRow1.label = options.display_name(sect, opt)
                newConfigRow1.input.name = html_key
                newConfigRow1.input.value = options.unconvert(sect, opt)
            else:
                # we provide checkboxes/radio buttons
                newConfigRow1 = configCbRow1.clone()
                newConfigRow1.label = options.display_name(sect, opt)
                blankOption = newConfigRow1.input.clone()
                firstOpt = True
                i = 0
                for val in options.valid_input(sect, opt):
                    newOption = blankOption.clone()
                    if options.multiple_values_allowed(sect, opt):
                        if val in options[sect, opt]:
                            newOption.input_box.checked = "checked"
                        newOption.input_box.type = "checkbox"
                        newOption.input_box.name = html_key + '-' + str(i)
                        i += 1
                    else:
                        if val == options[sect, opt]:
                            newOption.input_box.checked = "checked"
                        newOption.input_box.type = "radio"
                        newOption.input_box.name = html_key
                    # Tim thinks that Yes/No makes more sense than True/False
                    if options.is_boolean(sect, opt):
                        if val is True:
                            val = "Yes"
                        elif val is False:
                            val = "No"
                    newOption.val_label = str(val)
                    newOption.input_box.value = str(val)
                    if firstOpt:
                        newConfigRow1.input = newOption
                        firstOpt = False
                    else:
                        newConfigRow1.input += newOption
            # Insert the help text in a cell
            newConfigRow1.helpCell = '<strong>' + \
                                     options.display_name(sect, opt) + \
                                     ':</strong> ' + \
                                     cgi.escape(options.doc(sect, opt))

            newConfigRow2 = configRow2.clone()
            currentValue = options[sect, opt]

            if type(currentValue) in types.StringTypes:
                currentValue = currentValue.replace(',', ', ')
                newConfigRow2 = configTextRow2.clone()
            else:
                currentValue = options.unconvert(sect, opt)
                newConfigRow2 = configRow2.clone()

            # Tim thinks that Yes/No makes more sense than True/False
            if options.is_boolean(sect, opt):
                if currentValue == "False":
                    currentValue = "No"
                elif currentValue == "True":
                    currentValue = "Yes"
            # XXX Something needs to be done here, otherwise really
            # XXX long options squeeze the help text too far to the
            # XXX right.  Browsers can't wrap the text (even if
            # XXX no-wrap is False) unless there is whitespace to
            # XXX wrap on - comma's don't count.  This works, but
            # XXX it's a bit ugly.  Ideas?
            # currentValue = str(currentValue).replace(',', '<br />')
            newConfigRow2.currentValue = currentValue
            configTable += newConfigRow1 + newConfigRow2 + blankRow

        # Finish off the box for this section and add it to the form.
        if section is not None:
            section.boxContent = configTable
            html.configFormContent += section
        return html

    def onChangeopts(self, **parms):
        pmap = self.parm_ini_map
        if parms.has_key("how"):
            if parms["how"] == "Save advanced options":
                pmap = self.advanced_options_map
            elif parms["how"] == "Save experimental options":
                pmap = experimental_ini_map
            del parms["how"]
        html = self._getHTMLClone()
        html.shutdownTableCell = "&nbsp;"
        html.mainContent = self.html.headedBox.clone()
        errmsg = self.verifyInput(parms, pmap)

        if errmsg != '':
            html.mainContent.heading = "Errors Detected"
            html.mainContent.boxContent = errmsg
            html.title = 'Home &gt; Error'
            html.pagename = '&gt; Error'
            self.writeOKHeaders('text/html')
            self.write(html)
            return

        for name, value in parms.items():
            sect, opt = name.split('_', 1)
            if (sect, opt) in pmap:
                options.set(sect, opt, value)
            # If a section name has an underscore in it (like html_ui)
            # the split won't work the first time
            else:
                sect2, opt = opt.split('_', 1)
                sect += '_' + sect2
                options.set(sect, opt, value)

        options.update_file(optionsPathname)
        self.reReadOptions()

        html.mainContent.heading = "Options Changed"
        html.mainContent.boxContent = "%s.  Return <a href='home'>Home</a>." \
                                      % "Options changed"
        html.title = 'Home &gt; Options Changed'
        html.pagename = '&gt; Options Changed'
        self.writeOKHeaders('text/html')
        self.write(html)

    def onRestoredefaults(self, how):
        if how == "Restore advanced options defaults":
            self.restoreConfigDefaults(self.advanced_options_map)
        elif how == "Restore experimental options defaults (all off)":
            self.restoreConfigDefaults(experimental_ini_map)
        else:
            self.restoreConfigDefaults(self.parm_ini_map)
        self.reReadOptions()

        html = self._getHTMLClone()
        html.shutdownTableCell = "&nbsp;"
        html.mainContent = self.html.headedBox.clone()
        html.mainContent.heading = "Option Defaults Restored"
        html.mainContent.boxContent = "%s.  Return <a href='home'>Home</a>." \
                                      % "Defaults restored"
        html.title = 'Home &gt; Defaults Restored'
        html.pagename = '&gt; Defaults Restored'
        self.writeOKHeaders('text/html')
        self.write(html)
        self.reReadOptions()

    def verifyInput(self, parms, pmap):
        '''Check that the given input is valid.'''
        # Most of the work here is done by the options class, but
        # we may have a few extra checks that are beyond its capabilities
        errmsg = ''

        # mumbo-jumbo to deal with the checkboxes
        # XXX This will break with more than 9 checkboxes
        # XXX A better solution is needed than this
        for name, value in parms.items():
            if name[-2:-1] == '-':
                if parms.has_key(name[:-2]):
                    parms[name[:-2]] += (value,)
                else:
                    parms[name[:-2]] = (value,)
                del parms[name]

        for sect, opt in pmap:
            if opt is None:
                nice_section_name = sect
                continue
            html_key = sect + '_' + opt
            if not parms.has_key(html_key):
                # This is a set of checkboxes where none are selected
                value = ()
                entered_value = "None"
            else:
                value = parms[html_key]
                entered_value = value
                # Tim thinks that Yes/No makes more sense than True/False
                if options.is_boolean(sect, opt):
                    if value == "No":
                        value = False
                    elif value == "Yes":
                        value = True
                if options.multiple_values_allowed(sect, opt) and \
                   value == "":
                    value = ()
                value = options.convert(sect, opt, value)
            if not options.is_valid(sect, opt, value):
                errmsg += '<li>\'%s\' is not a value valid for [%s] %s' % \
                          (entered_value, nice_section_name,
                           options.display_name(sect, opt))
                if type(options.valid_input(sect, opt)) == type((0,1)):
                    errmsg += '. Valid values are: '
                    for valid in options.valid_input(sect, opt):
                        errmsg += str(valid) + ','
                    errmsg = errmsg[:-1] # cut last ','
                errmsg += '</li>'
            parms[html_key] = value

        return errmsg

    def restoreConfigDefaults(self, parm_map):
        # note that the behaviour of this function has subtly changed:
        # previously options were removed from the config file, now the
        # config file is updated to match the defaults
        d = OptionsClass()
        d.load_defaults(defaults)

        # Only restore the settings that appear on the form.
        for section, option in parm_map:
            if option is not None:
                if not options.no_restore(section, option):
                    options.set(section, option, d.get(section,option))

        options.update_file(optionsPathname)

    def onHelp(self, topic=None):
        """Provide a help page, either the default if topic is not
        supplied, or specific to the topic given."""
        self._writePreamble("Help")
        helppage = self.html.helppage.clone()
        if topic:
            # Present help specific to a certain page.  We probably want to
            # load this from a file, rather than fill up UserInterface.py,
            # but for demonstration purposes, do this for now.
            # (Note that this, of course, should be in ProxyUI, not here.)
            if topic == "review":
                helppage.helpheader = "Review Page Help"
                helppage.helptext = """<p>When you first start using
SpamBayes, all your mail will be classified as 'unsure' because SpamBayes
doesn't have any preconceived ideas about what good or bad mail looks like.
As soon as you start training the classification will improve, and by the
time you've classified even 20 messages of each you'll be seeing quite
reasonable results.</p>

<p>SpamBayes saves a <strong>temporary copy</strong> of all incoming mail
so that classification can be independant of whatever mail client you are
using. You need to run through these messages and tell SpamBayes how to
handle mail like that in the future. This page lists messages that have
arrived in the last %s days and that have not yet been trained. For each
message listed, you need to choose to either <strong>discard</strong>
(don't train on this message), <strong>defer</strong> (leave training on
this message until later), or train (as either good -
<strong>ham</strong>), or bad - <strong>spam</strong>). You do this by
simply clicking in the circle in the appropriate column; if you wish to
change all the messages to the same action, you can simply click the column
heading.</p>

<p>You are presented with the subject and sender of each message, but, if
this isn't enough information for you to make a decision on the message,
you can also view the message text (this is the raw text, so you can't do
any damage if the message contains a virus or any other malignant data).
To do this, simply click on the subject of the message.</p>

<p>Once you have chosen the actions you wish to perform on all the
displayed messages, click the <em>Train</em> button at the end of the page.
SpamBayes will then update its database to reflect this data.</p>

<p>Note that the messages are split up into the classification that
SpamBayes would place the message with current training data (if this is
correct, you might choose to <em>Discard</em> the message, rather than
train on it - see the <a href="http://entrian.com/sbwiki">SpamBayes wiki
</a> for discussion of training techniques).  You can also see the
<em>Tokens</em> that the message contains (the words in the message,
plus some additional tokens that SpamBayes generates) and the <em>Clues
</em> that SpamBayes used in classifying the message (not all tokens are
used in classification).</p>

<p>So that the page isn't overwhelmingly long, messages waiting for review
are split by the day they arrived.  You can use the <em>Previous Day</em>
or <em>Next Day</em> buttons at the top of the page to move between days.
If mail arrives while the review page is open the new messages will
<strong>not</strong> be automatically added to the displayed list; to add
the new message, click the <em>Refresh</em> button at the top of the page.
</p><hr />""" % (options["Storage", "cache_expiry_days"],)
            elif topic == "stats":
                # This does belong with UserInterface.py, but should
                # still probably be loaded from a file or something to
                # avoid all this clutter.  Someone come up with the
                # best solution! (A pickle?  A single text file? A text
                # file per help page in a directory?)
                helppage.helpheader = "Statistics Page Help"
                helppage.helptext = """<p>SpamBayes keeps track of certain
information about the messages that are classified.  For your interest,
this page displays statistics about the messages that have been classified
and trained so far.</p>

<p>Currently the page displays information about the
number of messages that have been classified as good, bad and unsure, how
many of these were false negatives or positives, and how many messages
were classified as unsure (and what their correct classification was).</p>

<p>Note that the data for this page resides in the &quot;message info&quot;
database that SpamBayes uses, and so only reflects messages since the
last time this database was created.</p><hr />"""
            elif topic == "home_proxy":
                # Also belongs with UserInterface.py, and probably
                # not with the source!
                helppage.helpheader = "Home Page Help"
                helppage.helptext = """<p>This is the main page for the
SpamBayes web interface.  You are presented with some information about
the current status of SpamBayes, and can follow links to review messages
or alter your configuration.</p>

<p>If you have messages stored in a mbox or dbx (Outlook Express) file
that you wish to 'bulk' train, or if you wish to train on a message
that you type in, you can do this on this page.  Click the
&quot;Browse&quot; button (or paste the text in, including headers),
and then click the <em>Train as Ham</em> or <em>Train as Spam</em>
button.</p>

<p>Likewise, if you have a message that you wish to classify, you
can do this.  Either paste the message into the text box, or click
&quot;Browse&quot; and locate the text file that the message is
located in.  Click <em>Classify</em>, and you will be taken to a
page describing the classification of that message.</p>

<p>If you want to find out information about a word in the statistics
database that forms the heart of SpamBayes, you can use the &quot;Word
Query&quot; facility.  Enter in the word that you wish to search for
and click <em>Tell me about this word</em>.  If you enable the advanced
find query, you can also search using wildcards or regular expressions.</p>

<p>You can also search for a specific message in the cache of temporary
copies of messages that have been proxied.  You might wish to do this if
you realise that you have incorrectly trained a message and need to correct
the training.  You can search the subject, headers, or message body, or
for the SpamBayes ID (which is in the headers of messages that SpamBayes
proxies).  Messages that are found will be presented in the standard
review page.  Note that once messages expire from the cache (after %s
days), you can no longer find them.</p>
<hr />""" % (options["Storage", "cache_expiry_days"],)
        self.write(helppage)
        self._writePostamble()

    def onStats(self):
        """Provide statistics about previous SpamBayes activity."""
        # Caching this information somewhere would be a good idea,
        # rather than regenerating it every time.  If people complain
        # about it being too slow, then do this!
        s = Stats.Stats()
        self._writePreamble("Statistics")
        stats = s.GetStats()
        stats = self._buildBox("Statistics", None, "<br/><br/>".join(stats))
        self.write(stats)
        self._writePostamble(help_topic="stats")

    def onBugreport(self):
        """Create a message to post to spambayes@python.org that hopefully
        has enough information for us to help this person with their
        problem."""
        self._writePreamble("Send Help Message", ("help", "Help"))
        report = self.html.bugreport.clone()
        # Prefill the report
        sb_ver = Version.get_version_string(self.app_for_version)
        if hasattr(sys, "frozen"):
            sb_type = "binary"
        else:
            sb_type = "source"
        py_ver = sys.version
        try:
            # Use "Windows" instead of "nt" or people might be confused.
            os_name = "Windows %d.%d.%d.%d (%s)" % sys.getwindowsversion()
        except AttributeError:
            # Not available in non-Windows, or pre 2.3
            os_name = os.name
        report.message_body = "I am using %s (%s), with version %s of " \
                              "Python; my operating system is %s.  I have " \
                              "trained %d ham and %d spam.\n\nThe problem " \
                              "I am having is [DESCRIBE YOUR PROBLEM HERE] " \
                              % (sb_ver, sb_type, py_ver, os_name,
                                 self.classifier.nham, self.classifier.nspam)
        domain_guess = options["pop3proxy", "remote_servers"][0]
        for pre in ["pop.", "pop3.", "mail.",]:
            if domain_guess.startswith(pre):
                domain_guess = domain_guess[len(pre):]
        report.from_addr.value = "[YOUR EMAIL ADDRESS]@%s" % (domain_guess,)
        report.cc_addr.value = report.from_addr.value
        report.subject.value = "Problem with %s" % (self.app_for_version,)
        # If the user has a log file, attach it.
        try:
            import win32api
        except ImportError:
            pass
        else:
            if hasattr(sys, "frozen"):
                temp_dir = win32api.GetTempPath()
                for name in ["SpamBayesService", "SpamBayesServer",]:
                    for i in xrange(3):
                        pn = os.path.join(temp_dir, "%s%d.log" % (name,
                                                                  (i+1)))
                        if os.path.exists(pn):
                            # I can't seem to set a default value for a
                            # "File" input type, so have to change it to
                            # "Text" if one is found.
                            report.file.type = "text"
                            report.file.value = pn
                            # For the moment, just attach the first one
                            # we find.
                            break
                    if report.file.value:
                        break

            try:
                smtp_server = options["smtpproxy", "remote_servers"][0]
            except IndexError:
                smtp_server = None
            if not smtp_server:
                self.write(self._buildBox("Warning", "status.gif",
                           "You will be unable to send this message from " \
                           "this page, as you do not have your SMTP " \
                           "server's details entered in your configuration. " \
                           "Please either <a href='config'>enter those " \
                           "details</a>, or copy the text below into your " \
                           "regular mail application."))
                del report.submitrow

        self.write(report)
        self._writePostamble()

    def onSubmitreport(self, from_addr, to_addr, cc_addr, message,
                       subject, attach):
        """Send the help message/bug report to the specified address."""
        # For guessing MIME type based on file name extension
        import mimetypes

        from email import Encoders
        from email.MIMEBase import MIMEBase
        from email.MIMEAudio import MIMEAudio
        from email.MIMEMultipart import MIMEMultipart
        from email.MIMEImage import MIMEImage
        from email.MIMEText import MIMEText

        if not self._verifyEnteredDetails(from_addr, cc_addr, message):
            self._writePreamble("Error", ("help", "Help"))
            self.write(self._buildBox("Error", "status.gif",
                                      "You must fill in the details that " \
                                      "describe your specific problem " \
                                      "before you can send the message."))
        else:
            self._writePreamble("Sent", ("help", "Help"))
            mailer = smtplib.SMTP(options["smtpproxy", "remote_servers"][0])

            # Create the enclosing (outer) message
            outer = MIMEMultipart()
            outer['Subject'] = subject
            outer['To'] = to_addr
            if cc_addr:
                outer['CC'] = cc_addr
            outer['From'] = from_addr
            outer.preamble = self._wrap(message)
            # To guarantee the message ends with a newline
            outer.epilogue = ''

            # Guess the content type based on the file's extension.
            try:
                ctype, encoding = mimetypes.guess_type(attach)
                if ctype is None or encoding is not None:
                    # No guess could be made, or the file is encoded (compressed),
                    # so use a generic bag-of-bits type.
                    ctype = 'application/octet-stream'
                maintype, subtype = ctype.split('/', 1)
                if maintype == 'text':
                    fp = open(attach)
                    # Note: we should handle calculating the charset
                    msg = MIMEText(fp.read(), _subtype=subtype)
                    fp.close()
                elif maintype == 'image':
                    fp = open(attach, 'rb')
                    msg = MIMEImage(fp.read(), _subtype=subtype)
                    fp.close()
                elif maintype == 'audio':
                    fp = open(attach, 'rb')
                    msg = MIMEAudio(fp.read(), _subtype=subtype)
                    fp.close()
                else:
                    fp = open(attach, 'rb')
                    msg = MIMEBase(maintype, subtype)
                    msg.set_payload(fp.read())
                    fp.close()
                    # Encode the payload using Base64
                    Encoders.encode_base64(msg)
            except IOError:
                # Couldn't access the file, so don't attach it.
                pass
            else:
                # Set the filename parameter
                msg.add_header('Content-Disposition', 'attachment',
                               filename=os.path.basename(attach))
                outer.attach(msg)
            msg = MIMEText(self._wrap(message))
            outer.attach(msg)

            recips = []
            for r in [to_addr, cc_addr]:
                if r:
                    recips.append(r)
            mailer.sendmail(from_addr, recips, outer.as_string())
            self.write("Sent message.  Please do not send again, or " \
                       "refresh this page!")
        self._writePostamble()

    def _verifyEnteredDetails(self, from_addr, cc_addr, message):
        """Ensure that the user didn't just send the form message, and
        at least changed the fields."""
        if from_addr.startswith("[YOUR EMAIL ADDRESS]") or \
           cc_addr.startswith("[YOUR EMAIL ADDRESS]"):
            return False
        if message.endswith("[DESCRIBE YOUR PROBLEM HERE]"):
            return False
        return True

    def _wrap(self, text, width=70):
        """Wrap the text into lines no bigger than the specified width."""
        try:
            from textwrap import fill
        except ImportError:
            pass
        else:
            return "\n".join([fill(paragraph, width) \
                              for paragraph in text.split('\n')])
        # No textwrap module, so do the same stuff (more-or-less) ourselves.
        def fill(text, width):
            if len(text) <= width:
                return text
            wordsep_re = re.compile(r'(-*\w{2,}-(?=\w{2,})|'   # hyphenated words
                                    r'(?<=\S)-{2,}(?=\w))')    # em-dash
            chunks = wordsep_re.split(text)
            chunks = filter(None, chunks)
            return '\n'.join(self._wrap_chunks(chunks, width))
        return "\n".join([fill(paragraph, width) \
                          for paragraph in text.split('\n')])

    def _wrap_chunks(self, chunks, width):
        """Stolen from textwrap; see that module in Python >= 2.3 for
        details."""
        lines = []
        while chunks:
            cur_line = []
            cur_len = 0
            if chunks[0].strip() == '' and lines:
                del chunks[0]
            while chunks:
                l = len(chunks[0])
                if cur_len + l <= width:
                    cur_line.append(chunks.pop(0))
                    cur_len += l
                else:
                    break
            if chunks and len(chunks[0]) > width:
                space_left = width - cur_len
                cur_line.append(chunks[0][0:space_left])
                chunks[0] = chunks[0][space_left:]
            if cur_line and cur_line[-1].strip() == '':
                del cur_line[-1]
            if cur_line:
                lines.append(''.join(cur_line))
        return lines
