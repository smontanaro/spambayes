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

import PyMeldLite
import Dibbler
import tokenizer
from Options import options, optionsPathname, defaults

IMAGES = ('helmet', 'status', 'config',
          'message', 'train', 'classify', 'query')

global classifier

class UserInterfaceServer(Dibbler.HTTPServer):
    """Implements the web server component via a Dibbler plugin."""

    def __init__(self, uiPort):
        Dibbler.HTTPServer.__init__(self, uiPort)
        print 'User interface url is http://localhost:%d/' % (uiPort)


class BaseUserInterface(Dibbler.HTTPPlugin):
    def __init__(self):
        Dibbler.HTTPPlugin.__init__(self)
        htmlSource, self._images = self.readUIResources()
        self.html = PyMeldLite.Meld(htmlSource, readonly=True)
  
    def onIncomingConnection(self, clientSocket):
        """Checks the security settings."""
        return options["html_ui", "allow_remote_connections"] or \
               clientSocket.getpeername()[0] == clientSocket.getsockname()[0]

    def _writePreamble(self, name, parent=None, showImage=True):
        """Writes the HTML for the beginning of a page - time-consuming
        methlets use this and `_writePostamble` to write the page in
        pieces, including progress messages.  `parent` (if given) should
        be a pair: `(url, label)`, eg. `('review', 'Review')`."""

        # Take the whole palette and remove the content and the footer,
        # leaving the header and an empty body.
        html = self.html.clone()
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

    def _writePostamble(self):
        """Writes the end of time-consuming pages - see `_writePreamble`."""
        footer = self.html.footer.clone()
        footer.timestamp = time.asctime(time.localtime())
        self.write("</div>" + self.html.footer)
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

    def __init__(self, bayes, config_parms=()):
        """Load up the necessary resources: ui.html and helmet.gif."""
        global classifier
        BaseUserInterface.__init__(self)
        classifier = bayes
        self.parm_ini_map = config_parms

    def onClassify(self, file, text, which):
        """Classify an uploaded or pasted message."""
        message = file or text
        message = message.replace('\r\n', '\n').replace('\r', '\n') # For Macs
        results = self._buildCluesTable(message)
        results.classifyAnother = self._buildClassifyBox()
        self._writePreamble("Classify")
        self.write(results)
        self._writePostamble()

    def _buildCluesTable(self, message, subject=None):
        cluesTable = self.html.cluesTable.clone()
        cluesRow = cluesTable.cluesRow.clone()
        del cluesTable.cluesRow   # Delete dummy row to make way for real ones
        (probability, clues) = classifier.spamprob(tokenizer.tokenize(message),\
                                                    evidence=True)
        for word, wordProb in clues:
            cluesTable += cluesRow % (cgi.escape(word), wordProb)

        results = self.html.classifyResults.clone()
        results.probability = probability
        if subject is None:
            heading = "Clues:"
        else:
            heading = "Clues for: " + subject
        results.cluesBox = self._buildBox(heading, 'status.gif', cluesTable)
        return results

    def onWordquery(self, word):
        if word == "":
            stats = "You must enter a word."
        else:
            word = word.lower()
            wordinfo = classifier._wordinfoget(word)
            if wordinfo:
                stats = self.html.wordStats.clone()
                stats.spamcount = wordinfo.spamcount
                stats.hamcount = wordinfo.hamcount
                stats.spamprob = classifier.probability(wordinfo)
            else:
                stats = "%r does not exist in the database." % cgi.escape(word)

        query = self.html.wordQuery.clone()
        query.word.value = word
        statsBox = self._buildBox("Statistics for %r" % cgi.escape(word),
                                  'status.gif', stats)
        queryBox = self._buildBox("Word query", 'query.gif', query)
        self._writePreamble("Word query")
        self.write(statsBox + queryBox)
        self._writePostamble()

    def onTrain(self, file, text, which):
        """Train on an uploaded or pasted message."""
        self._writePreamble("Train")

        # Upload or paste?  Spam or ham?
        content = file or text
        isSpam = (which == 'Train as Spam')

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
            classifier.learn(tokens, isSpam)
            f.write("From pop3proxy@spambayes.org Sat Jan 31 00:00:00 2000\n")
            f.write(message)
            f.write("\n\n")

        # Save the database and return a link Home and another training form.
        f.close()
        self._doSave()
        self.write("<p>OK. Return <a href='home'>Home</a> or train again:</p>")
        self.write(self._buildTrainBox())
        self._writePostamble()

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
        classifier.store()
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
        return self._buildBox("Train on a given message", 'message.gif', form)

    def reReadOptions(self):
        """Called by the config page when the user saves some new options,
        or restores the defaults."""
        pass

    def onConfig(self):
        # Start with an empty config form then add the sections.
        html = self.html.clone()
        # "Save and Shutdown" is confusing here - it means "Save database"
        # but that's not clear.
        html.shutdownTableCell = "&nbsp;"
        html.mainContent = self.html.configForm.clone()
        html.mainContent.configFormContent = ""
        html.mainContent.optionsPathname = optionsPathname
        configTable = None
        section = None

        # Loop though the sections.
        for sect, opt in self.parm_ini_map:
            # We need a string to use as the html key that we can change to
            # and from the sect, opt pair.  We like irony, so we use '_' as
            # the delimiter <wink>
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
        html.title = 'Home &gt; Configure'
        html.pagename = '&gt; Configure'
        self.writeOKHeaders('text/html')
        self.write(html)

    def onChangeopts(self, **parms):
        if parms.has_key("how"):
            del parms["how"]
        html = self.html.clone()
        html.shutdownTableCell = "&nbsp;"
        html.mainContent = self.html.headedBox.clone()
        errmsg = self.verifyInput(parms)

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
            if (sect, opt) in self.parm_ini_map:
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
        self.restoreConfigDefaults()
        self.reReadOptions()

        html = self.html.clone()
        html.shutdownTableCell = "&nbsp;"
        html.mainContent = self.html.headedBox.clone()
        html.mainContent.heading = "Option Defaults Restored"
        html.mainContent.boxContent = "%s.  Return <a href='home'>Home</a>." \
                                      % "Defaults restored"
        html.title = 'Home &gt; Defaults Restored'
        html.pagename = '&gt; Defaults Restored'
        self.writeOKHeaders('text/html')
        self.write(html)

    def verifyInput(self, parms):
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
                    parms[name[:-2]].append(value)
                else:
                    parms[name[:-2]] = (value,)
                del parms[name]

        for sect, opt in self.parm_ini_map:
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

    def restoreConfigDefaults(self):
        # note that the behaviour of this function has subtly changed
        # previously options were removed from the config file, now the
        # config file is updated to match the defaults
        c = ConfigParser()
        d = StringIO(defaults)
        c.readfp(d)
        del d

        # Only restore the settings that appear on the form.
        for section, option in self.parm_ini_map:
            if option is not None:
                if not options.no_restore(section, option):
                    options.set(section, option, c.get(section,option))

        op = open(optionsPathname, "r")
        options.update_file(op)
        op.close()
