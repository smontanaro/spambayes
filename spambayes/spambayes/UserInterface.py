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
  onHelp - present the help page

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
import time
import email
import binascii
import cgi
import mailbox
import types
import StringIO

import oe_mailbox
from time import gmtime, strftime

import PyMeldLite
import Version
import Dibbler
import tokenizer
from spambayes import Stats
from Options import options, optionsPathname, defaults, OptionsClass

IMAGES = ('helmet', 'status', 'config', 'help',
          'message', 'train', 'classify', 'query')

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
    sc_re = re.compile("%s:(.*)\n" % \
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
        tokens = tokenizer.tokenize(message)
        if show_tokens:
            clues = []
            for tok in tokens:
                clues.append((tok, None))
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
                evidence = mo.group(1).strip().split(';')
                for clue in evidence:
                    word, prob = clue.strip().split(': ')
                    clues.append((word.strip("'"), prob))
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

        dbxStream = StringIO.StringIO(content)
        header = oe_mailbox.dbxFileHeader(dbxStream)

        if header.isValid() and header.isMessages():
            file_info_len = oe_mailbox.dbxFileHeader.FH_FILE_INFO_LENGTH
            fh_entries = oe_mailbox.dbxFileHeader.FH_ENTRIES
            fh_ptr = oe_mailbox.dbxFileHeader.FH_TREE_ROOT_NODE_PTR
            
            info = oe_mailbox.dbxFileInfo(dbxStream,
                                          header.getEntry(file_info_len))
            entries = header.getEntry(fh_entries)
            address = header.getEntry(fh_ptr)
            
            if address and entries:
                tree = oe_mailbox.dbxTree(dbxStream, address, entries)
                dbxBuffer = ""

                for i in range(entries):
                    address = tree.getValue(i)
                    messageInfo = oe_mailbox.dbxMessageInfo(dbxStream,
                                                            address)

                    if messageInfo.isIndexed(\
                        oe_mailbox.dbxMessageInfo.MI_MESSAGE_ADDRESS):
                        address = oe_mailbox.dbxMessageInfo.MI_MESSAGE_ADDRESS
                        messageAddress = \
                                       messageInfo.getValueAsLong(address)
                        message = oe_mailbox.dbxMessage(dbxStream,
                                                        messageAddress)

                        # This fakes up a from header to conform to mbox
                        # standards.  It would be better to extract this
                        # data from the message itself, as this will
                        # result in incorrect tokens.
                        dbxBuffer += "From spambayes@spambayes.org %s\n%s" \
                                     % (strftime("%a %b %d %H:%M:%S MET %Y",
                                                 gmtime()), message.getText())
                content = dbxBuffer
        dbxStream.close()
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

    def onAdvancedconfig(self):
        html = self._buildConfigPage(self.advanced_options_map)
        html.title = 'Home &gt; Advanced Configuration'
        html.pagename = '&gt; Advanced Configuration'
        html.adv_button.name.value = "Back to basic configuration"
        html.adv_button.action = "config"
        html.config_submit.value = "Save advanced options"
        html.restore.value = "Restore advanced options defaults"
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
                        if val == False:
                            val = "No"
                        elif val == True:
                            val = "Yes"
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
                helppage.helptext = "This page lists messages that have " \
                                    "arrived in the last %s days and that " \
                                    "have not yet been trained.  You should " \
                                    "go through the messages, correcting " \
                                    "the classification where necessary, " \
                                    "and then click train, to train " \
                                    "SpamBayes with these messages" \
                                    % (options["Storage", "cache_expiry_days"],)
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
        self._writePostamble()
