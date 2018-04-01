"""Core Web Interface

Classes:
    CoreUserInterface - Interface class for basic (non-plugin) display

Abstract:

This module implements a browser based Spambayes user interface for the
the core server.  Users may use it to interface with various plugins.

The following functions are currently included:
[From the base class UserInterface]
  onClassify - classify a given message
  onWordquery - query a word from the database
  onTrain - train a message or mbox
  onSave - save the database and possibly shutdown
[Here]
  onHome - a home page with various options
  onUpload - upload a message for later training (used by proxytee.py)
  onReview - show messages in corpii
  onView - view a message from one of the corpii
  onShowclues - show clues for a message

To do:

Web training interface:

 o Review already-trained messages, and purge them.
 o Add a Today button on the Review page.

User interface improvements:

 o Can it cleanly dynamically update its status display while having a POP3
   conversation?  Hammering reload sucks.

 o Suggestions?
"""

# This module is part of the spambayes project, which is Copyright 2002-2007
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

# This module was forked from ProxyUI.py to provide a basic user interface
# for core_server.py.

__author__ = "Richie Hindle <richie@entrian.com>"
__credits__ = "Tim Peters, Neale Pickett, Tim Stone, all the Spambayes folk."

import sys
import cgi
import time
import types
import bisect

from spambayes import UserInterface
from spambayes.Options import options, load_options, get_pathname_option, _
## no i18n yet...
##from spambayes import i18n
from spambayes import storage
from spambayes import Stats
from spambayes.FileCorpus import FileMessageFactory, GzipFileMessageFactory
from spambayes.FileCorpus import ExpiryFileCorpus
import spambayes.message

# These are the options that will be offered on the configuration page.  If
# the option is None, then the entry is a header and the following options
# will appear in a new box on the configuration page.  These are also used
# to generate http request parameters and template fields/variables.
parm_ini_map = (
    ('Storage Options',     None),
    ('Storage',             'persistent_storage_file'),
    ('Storage',             'messageinfo_storage_file'),
    ('Storage',             'cache_messages'),
    ('Storage',             'no_cache_bulk_ham'),
    ('Storage',             'no_cache_large_messages'),
    ('Statistics Options',  None),
    ('Categorization',      'ham_cutoff'),
    ('Categorization',      'spam_cutoff'),
)

# Like the above, but these are the options that will be offered on the
# advanced configuration page.
adv_map = (
    (_('Statistics Options'), None),
    ('Classifier',            'max_discriminators'),
    ('Classifier',            'minimum_prob_strength'),
    ('Classifier',            'unknown_word_prob'),
    ('Classifier',            'unknown_word_strength'),
    ('Classifier',            'use_bigrams'),
    (_('Header Options'),     None),
    ('Headers',               'include_score'),
    ('Headers',               'header_score_digits'),
    ('Headers',               'header_score_logarithm'),
    ('Headers',               'include_thermostat'),
    ('Headers',               'include_evidence'),
    ('Headers',               'clue_mailheader_cutoff'),
    (_('Storage Options'),    None),
    ('Storage',               'persistent_use_database'),
    ('Storage',               'cache_expiry_days'),
    ('Storage',               'cache_use_gzip'),
    ('Storage',               'ham_cache'),
    ('Storage',               'spam_cache'),
    ('Storage',               'unknown_cache'),
    (_('Tokenising Options'), None),
    ('Tokenizer',             'mine_received_headers'),
    ('Tokenizer',             'replace_nonascii_chars'),
    ('Tokenizer',             'summarize_email_prefixes'),
    ('Tokenizer',             'summarize_email_suffixes'),
    (_('Training Options'),   None),
    ('Hammie',                'train_on_filter'),
    (_('Interface Options'),  None),
    ('html_ui',               'display_headers'),
    ('html_ui',               'display_received_time'),
    ('html_ui',               'display_score'),
    ('html_ui',               'display_adv_find'),
    ('html_ui',               'default_ham_action'),
    ('html_ui',               'default_spam_action'),
    ('html_ui',               'default_unsure_action'),
    ('html_ui',               'ham_discard_level'),
    ('html_ui',               'spam_discard_level'),
    ('html_ui',               'allow_remote_connections'),
    ('html_ui',               'http_authentication'),
    ('html_ui',               'http_user_name'),
    ('html_ui',               'http_password'),
    ('globals',               'language'),
)

class AlreadyRunningException(Exception):
    "exception may be raised if we are already running and check such things."
    pass

class CoreUserInterface(UserInterface.UserInterface):
    """Serves the HTML user interface for the core server."""

    def __init__(self, state):
        UserInterface.UserInterface.__init__(self, state.bayes,
                                             parm_ini_map, adv_map,
                                             state.lang_manager,
                                             state.stats)
        self.state = state
        self.app_for_version = "SpamBayes Proxy"
        if not state.can_stop:
            self.html._readonly = False
            self.html.shutdownTableCell = "&nbsp;"
            self.html._readonly = True

    def onHome(self):
        """Serve up the homepage."""
        self.state.buildStatusStrings()
        stateDict = self.state.__dict__.copy()
        stateDict.update(self.state.bayes.__dict__)
        statusTable = self.html.statusTable.clone()
        findBox = self._buildBox(_('Word query'), 'query.gif',
                                 self.html.wordQuery)
        if not options["html_ui", "display_adv_find"]:
            del findBox.advanced
        content = (self._buildBox(_('Status and Configuration'),
                                  'status.gif', statusTable % stateDict)+
                   self._buildBox(_('Train on proxied messages'),
                                  'train.gif', self.html.reviewText) +
                   self._buildTrainBox() +
                   self._buildClassifyBox() +
                   findBox +
                   self._buildBox(_('Find message'), 'query.gif',
                                  self.html.findMessage)
                   )
        self._writePreamble(_("Home"))
        self.write(content)
        self._writePostamble(help_topic="home_proxy")

    def onUpload(self, filename):
        """Save a message for later training - used by Skip's proxytee.py."""
        # Convert platform-specific line endings into unix-style.
        filename = filename.replace('\r\n', '\n').replace('\r', '\n')

        # Get a message list from the upload and write it into the cache.
        messages = self._convertUploadToMessageList(filename)
        for m in messages:
            messageName = self.state.getNewMessageName()
            message = self.state.unknownCorpus.makeMessage(messageName, m)
            self.state.unknownCorpus.addMessage(message)

        # Return a link Home.
        self.write(_("<p>OK. Return <a href='home'>Home</a>.</p>"))

    def _buildReviewKeys(self, timestamp):
        """Builds an ordered list of untrained message keys, ready for output
        in the Review list.  Returns a 5-tuple: the keys, the formatted date
        for the list (eg. "Friday, November 15, 2002"), the start of the prior
        page or zero if there isn't one, likewise the start of the given page,
        and likewise the start of the next page."""
        # Fetch all the message keys
        allKeys = self.state.unknownCorpus.keys()
        # We have to sort here to split into days.
        # Later on, we also sort the messages that will be on the page
        # (by whatever column we wish).
        allKeys.sort()

        # The default start timestamp is derived from the most recent message,
        # or the system time if there are no messages (not that it gets used).
        if not timestamp:
            if allKeys:
                timestamp = self._keyToTimestamp(allKeys[-1])
            else:
                timestamp = time.time()
        start, end, date = self._getTimeRange(timestamp)

        # Find the subset of the keys within this range.
        startKeyIndex = bisect.bisect(allKeys, "%d" % long(start))
        endKeyIndex = bisect.bisect(allKeys, "%d" % long(end))
        keys = allKeys[startKeyIndex:endKeyIndex]
        keys.reverse()

        # What timestamps to use for the prior and next days?  If there any
        # messages before/after this day's range, use the timestamps of those
        # messages - this will skip empty days.
        prior = end = 0
        if startKeyIndex != 0:
            prior = self._keyToTimestamp(allKeys[startKeyIndex-1])
        if endKeyIndex != len(allKeys):
            end = self._keyToTimestamp(allKeys[endKeyIndex])

        # Return the keys and their date.
        return keys, date, prior, start, end

    def onReview(self, **params):
        """Present a list of message for (re)training."""
        # Train/discard sumbitted messages.
        self._writePreamble("Review")
        id = ''
        numTrained = 0
        numDeferred = 0
        if params.get('go') != _('Refresh'):
            for key, value in params.items():
                if key.startswith('classify:'):
                    old_class, id = key.split(':')[1:3]
                    if value == _('spam'):
                        targetCorpus = self.state.spamCorpus
                        stats_as_ham = False
                    elif value == _('ham'):
                        targetCorpus = self.state.hamCorpus
                        stats_as_ham = True
                    elif value == _('discard'):
                        targetCorpus = None
                        try:
                            self.state.unknownCorpus.removeMessage(
                                self.state.unknownCorpus[id])
                        except KeyError:
                            pass  # Must be a reload.
                    else: # defer
                        targetCorpus = None
                        numDeferred += 1
                    if targetCorpus:
                        sourceCorpus = None
                        if self.state.unknownCorpus.get(id) is not None:
                            sourceCorpus = self.state.unknownCorpus
                        elif self.state.hamCorpus.get(id) is not None:
                            sourceCorpus = self.state.hamCorpus
                        elif self.state.spamCorpus.get(id) is not None:
                            sourceCorpus = self.state.spamCorpus
                        if sourceCorpus is not None:
                            try:
                                # fromCache is a fix for sf #851785.
                                # See the comments in Corpus.py
                                targetCorpus.takeMessage(id, sourceCorpus,
                                                         fromCache=True)
                                if numTrained == 0:
                                    self.write(_("<p><b>Training... "))
                                    self.flush()
                                numTrained += 1
                                self.stats.RecordTraining(\
                                  stats_as_ham, old_class=old_class)
                            except KeyError:
                                pass  # Must be a reload.

        # Report on any training, and save the database if there was any.
        if numTrained > 0:
            plural = ''
            if numTrained == 1:
                response = "Trained on one message. "
            else:
                response = "Trained on %d messages. " % (numTrained,)
            self._doSave()
            self.write(response)
            self.write("<br>&nbsp;")

        title = ""
        keys = []
        sourceCorpus = self.state.unknownCorpus
        # If any messages were deferred, show the same page again.
        if numDeferred > 0:
            start = self._keyToTimestamp(id)

        # Else after submitting a whole page, display the prior page or the
        # next one.  Derive the day of the submitted page from the ID of the
        # last processed message.
        elif id:
            start = self._keyToTimestamp(id)
            unused, unused, prior, unused, next = self._buildReviewKeys(start)
            if prior:
                start = prior
            else:
                start = next

        # Else if they've hit Previous or Next, display that page.
        elif params.get('go') == _('Next day'):
            start = self._keyToTimestamp(params['next'])
        elif params.get('go') == _('Previous day'):
            start = self._keyToTimestamp(params['prior'])

        # Else if an id has been specified, just show that message
        # Else if search criteria have been specified, show the messages
        # that match those criteria.
        elif params.get('find') is not None:
            prior = next = 0
            keys = set()        # so we don't end up with duplicates
            push = keys.add
            try:
                max_results = int(params['max_results'])
            except ValueError:
                max_results = 1
            key = params['find']
            if params.has_key('ignore_case'):
                ic = True
            else:
                ic = False
            error = False
            if key == "":
                error = True
                page = _("<p>You must enter a search string.</p>")
            else:
                if len(keys) < max_results and \
                   params.has_key('id'):
                    if self.state.unknownCorpus.get(key):
                        push((key, self.state.unknownCorpus))
                    elif self.state.hamCorpus.get(key):
                        push((key, self.state.hamCorpus))
                    elif self.state.spamCorpus.get(key):
                        push((key, self.state.spamCorpus))
                if params.has_key('subject') or params.has_key('body') or \
                   params.has_key('headers'):
                    # This is an expensive operation, so let the user know
                    # that something is happening.
                    self.write(_('<p>Searching...</p>'))
                    for corp in [self.state.unknownCorpus,
                                 self.state.hamCorpus,
                                 self.state.spamCorpus]:
                        for k in corp.keys():
                            if len(keys) >= max_results:
                                break
                            msg = corp[k]
                            msg.load()
                            if params.has_key('subject'):
                                subj = str(msg['Subject'])
                                if self._contains(subj, key, ic):
                                    push((k, corp))
                            if params.has_key('body'):
                                # For [ 906581 ] Assertion failed in search
                                # subject.  Can the headers be a non-string?
                                msg_body = msg.as_string()
                                msg_body = msg_body[msg_body.index('\r\n\r\n'):]
                                if self._contains(msg_body, key, ic):
                                    push((k, corp))
                            if params.has_key('headers'):
                                for nm, val in msg.items():
                                    # For [ 906581 ] Assertion failed in
                                    # search subject.  Can the headers be
                                    # a non-string?
                                    nm = str(nm)
                                    val = str(val)
                                    if self._contains(nm, key, ic) or \
                                       self._contains(val, key, ic):
                                        push((k, corp))
                if len(keys):
                    if len(keys) == 1:
                        title = _("Found message")
                    else:                      
                        title = _("Found messages")
                    keys = list(keys)
                else:
                    page = _("<p>Could not find any matching messages. " \
                             "Maybe they expired?</p>")
                    title = _("Did not find message")
                    box = self._buildBox(title, 'status.gif', page)
                    self.write(box)
                    self.write(self._buildBox(_('Find message'),
                                              'query.gif',
                                              self.html.findMessage))
                    self._writePostamble()
                    return

        # Else show the most recent day's page, as decided by _buildReviewKeys.
        else:
            start = 0

        # Build the lists of messages: spams, hams and unsure.
        if len(keys) == 0:
            keys, date, prior, this, next = self._buildReviewKeys(start)
        keyedMessageInfo = {options["Headers", "header_unsure_string"]: [],
                            options["Headers", "header_ham_string"]: [],
                            options["Headers", "header_spam_string"]: [],
                            }
        invalid_keys = []
        for key in keys:
            if isinstance(key, types.TupleType):
                key, sourceCorpus = key
            else:
                sourceCorpus = self.state.unknownCorpus
            # Parse the message, get the judgement header and build a message
            # info object for each message.
            message = sourceCorpus[key]
            try:
                message.load()
            except IOError:
                # Someone has taken this file away from us.  It was
                # probably a virus protection program, so that's ok.
                # Don't list it in the review, though.
                invalid_keys.append(key)
                continue
            judgement = message[options["Headers",
                                        "classification_header_name"]]
            if judgement is None:
                judgement = options["Headers", "header_unsure_string"]
            else:
                judgement = judgement.split(';')[0].strip()
            messageInfo = self._makeMessageInfo(message)
            keyedMessageInfo[judgement].append((key, messageInfo))
        for key in invalid_keys:
            keys.remove(key)

        # Present the list of messages in their groups in reverse order of
        # appearance, by default, or according to the specified sort order.
        if keys:
            page = self.html.reviewtable.clone()
            if prior:
                page.prior.value = prior
                del page.priorButton.disabled
            if next:
                page.next.value = next
                del page.nextButton.disabled
            templateRow = page.reviewRow.clone()

            # The decision about whether to reverse the sort
            # order has to go here, because _sortMessages gets called
            # thrice, and so the ham list would end up sorted backwards.
            sort_order = params.get('sort')
            if self.previous_sort == sort_order:
                reverse = True
                self.previous_sort = None
            else:
                reverse = False
                self.previous_sort = sort_order

            page.table = ""  # To make way for the real rows.
            for header, label in ((options["Headers",
                                           "header_unsure_string"], 'Unsure'),
                                  (options["Headers",
                                           "header_ham_string"], 'Ham'),
                                  (options["Headers",
                                           "header_spam_string"], 'Spam')):
                messages = keyedMessageInfo[header]
                if messages:
                    sh = self.html.reviewSubHeader.clone()
                    # Setup the header row
                    sh.optionalHeaders = ''
                    h = self.html.headerHeader.clone()
                    for disp_header in options["html_ui", "display_headers"]:
                        h.headerLink.href = 'review?sort=%sHeader' % \
                                            (disp_header.lower(),)
                        h.headerName = disp_header.title()
                        sh.optionalHeaders += h
                    if not options["html_ui", "display_score"]:
                        del sh.score_header
                    if not options["html_ui", "display_received_time"]:
                        del sh.received_header
                    subHeader = str(sh)
                    subHeader = subHeader.replace('TYPE', label)
                    page.table += self.html.blankRow
                    page.table += subHeader
                    self._appendMessages(page.table, messages, label,
                                         sort_order, reverse)

            page.table += self.html.trainRow
            if title == "":
                title = _("Untrained messages received on %s") % date
            box = self._buildBox(title, None, page)  # No icon, to save space.
        else:
            page = _("<p>There are no untrained messages to display. " \
                     "Return <a href='home'>Home</a>, or " \
                     "<a href='review'>check again</a>.</p>")
            title = _("No untrained messages")
            box = self._buildBox(title, 'status.gif', page)

        self.write(box)
        self._writePostamble(help_topic="review")

    def onView(self, key, corpus):
        """View a message - linked from the Review page."""
        self._writePreamble(_("View message"),
                            parent=('review', _('Review')))
        sourceCorpus = None
        message = None
        if self.state.unknownCorpus.get(key) is not None:
            sourceCorpus = self.state.unknownCorpus
        elif self.state.hamCorpus.get(key) is not None:
            sourceCorpus = self.state.hamCorpus
        elif self.state.spamCorpus.get(key) is not None:
            sourceCorpus = self.state.spamCorpus
        if sourceCorpus is not None:
            message = sourceCorpus.get(key)
        if message is not None:
            self.write("<pre>%s</pre>" % cgi.escape(message.as_string()))
        else:
            self.write(_("<p>Can't find message %r. Maybe it expired.</p>") %
                       key)
        self._writePostamble()

    def onShowclues(self, key, subject, tokens='0'):
        """Show clues for a message - linked from the Review page."""
        tokens = bool(int(tokens)) # needs the int, as bool('0') is True
        self._writePreamble(_("Message clues"),
                            parent=('review', _('Review')))
        sourceCorpus = None
        message = None
        if self.state.unknownCorpus.get(key) is not None:
            sourceCorpus = self.state.unknownCorpus
        elif self.state.hamCorpus.get(key) is not None:
            sourceCorpus = self.state.hamCorpus
        elif self.state.spamCorpus.get(key) is not None:
            sourceCorpus = self.state.spamCorpus
        if sourceCorpus is not None:
            message = sourceCorpus.get(key).as_string()
        if message is not None:
            # For Macs?
            message = message.replace('\r\n', '\n').replace('\r', '\n')
            results = self._buildCluesTable(message, subject, tokens)
            del results.classifyAnother
            self.write(results)
        else:
            self.write(_("<p>Can't find message %r. Maybe it expired.</p>") %
                       key)
        self._writePostamble()

    def onPluginconfig(self):
        html = self._buildConfigPage(self.state.plugin.ui.plugin_map)
        html.title = _('Home &gt; Plugin Configuration')
        html.pagename = _('&gt; Plugin Configuration')
        html.plugin_button.name.value = _("Back to basic configuration")
        html.plugin_button.action = "config"
        html.config_submit.value = _("Save plugin options")
        html.restore.value = _("Restore plugin options defaults")
        del html.exp_button
        del html.adv_button
        self.writeOKHeaders('text/html')
        self.write(html)

    def close_database(self):
        self.state.close()

    def reReadOptions(self):
        """Called by the config page when the user saves some new options, or
        restores the defaults."""
        load_options()

        # Recreate the state.
        self.state = self.state.recreate_state()
        self.classifier = self.state.bayes

    def verifyInput(self, parms, pmap):
        '''Check that the given input is valid.'''
        # Most of the work here is done by the parent class, but
        # we have a few extra checks
        errmsg = UserInterface.UserInterface.verifyInput(self, parms, pmap)

        if pmap != parm_ini_map:
            return errmsg

        return errmsg

    def readUIResources(self):
        """Returns ui.html and a dictionary of Gifs."""
        if self.lang_manager:
            ui_html = self.lang_manager.import_ui_html()
        else:
            from spambayes.core_resources import ui_html
        images = {}
        for baseName in UserInterface.IMAGES:
            moduleName = '%s.%s_gif' % ('spambayes.core_resources', baseName)
            module = __import__(moduleName, {}, {}, ('spambayes',
                                                     'core_resources'))
            images[baseName] = module.data
        return ui_html.data, images

class CoreState:
    """This keeps the global state of the module - the command-line options,
    statistics like how many mails have been classified, the handle of the
    log file, the Classifier and FileCorpus objects, and so on."""

    def __init__(self):
        """Initialises the State object that holds the state of the app.
        The default settings are read from Options.py and bayescustomize.ini
        and are then overridden by the command-line processing code in the
        __main__ code below."""
        self.log_file = None
        self.bayes = None
        self.mutex = None
        self.prepared = False
        self.can_stop = True
        self.plugin = None

        # Unique names for cached messages - see `getNewMessageName()` below.
        self.last_base_message_name = ''
        self.uniquifier = 2

        # Set up the statistics.
        self.numSpams = 0
        self.numHams = 0
        self.numUnsure = 0

        self.servers = ""

        # Load up the other settings from Option.py / bayescustomize.ini
        self.ui_port = options["html_ui", "port"]
        self.launch_ui = options["html_ui", "launch_browser"]
        self.gzip_cache = options["Storage", "cache_use_gzip"]
        self.run_test_server = False
        self.is_test = False

        self.spamCorpus = self.hamCorpus = self.unknownCorpus = None
        self.spam_trainer = self.ham_trainer = None

        self.init()

    def init(self):
        assert not self.prepared, "init after prepare, but before close"
## no i18n yet...
##         # Load the environment for translation.
##         self.lang_manager = i18n.LanguageManager()
##         # Set the system user default language.
##         self.lang_manager.set_language(\
##             self.lang_manager.locale_default_lang())
##         # Set interface to use the user language in the configuration file.
##         for language in reversed(options["globals", "language"]):
##             # We leave the default in there as the last option, to fall
##             # back on if necessary.
##             self.lang_manager.add_language(language)
##         if options["globals", "verbose"]:
##             print "Asked to add languages: " + \
##                   ", ".join(options["globals", "language"])
##             print "Set language to " + \
##                   str(self.lang_manager.current_langs_codes)
        self.lang_manager = None

        # Open the log file.
        if options["globals", "verbose"]:
            self.log_file = open('_core_server.log', 'wb', 0)

        # Remember reported errors.
        self.reported_errors = {}

    def close(self):
        assert self.prepared, "closed without being prepared!"
        if self.bayes is not None:
            # Only store a non-empty db.
            if self.bayes.nham != 0 and self.bayes.nspam != 0:
                self.bayes.store()
            self.bayes.close()
            self.bayes = None
        spambayes.message.Message().message_info_db = None

        self.spamCorpus = self.hamCorpus = self.unknownCorpus = None
        self.spam_trainer = self.ham_trainer = None

        self.prepared = False
        self.close_platform_mutex()

    def prepare(self, can_stop=True):
        """Do whatever needs to be done to prepare for running.  If
        can_stop is False, then we may not let the user shut down the
        proxy - for example, running as a Windows service this should
        be the case."""

        self.init()
        # If we can, prevent multiple servers from running at the same time.
        assert self.mutex is None, "Should not already have the mutex"
        self.open_platform_mutex()

        self.can_stop = can_stop

        # Do whatever we've been asked to do...
        self.create_workers()
        self.prepared = True

    def build_status_strings(self):
        """Build the status message(s) to display on the home page of the
        web interface."""
        nspam = self.bayes.nspam
        nham = self.bayes.nham
        if nspam > 10 and nham > 10:
            db_ratio = nham/float(nspam)
            if db_ratio > 5.0:
                self.warning = _("Warning: you have much more ham than " \
                                 "spam - SpamBayes works best with " \
                                 "approximately even numbers of ham and " \
                                 "spam.")
            elif db_ratio < (1/5.0):
                self.warning = _("Warning: you have much more spam than " \
                                 "ham - SpamBayes works best with " \
                                 "approximately even numbers of ham and " \
                                 "spam.")
            else:
                self.warning = ""
        elif nspam > 0 or nham > 0:
            self.warning = _("Database only has %d good and %d spam - " \
                             "you should consider performing additional " \
                             "training.") % (nham, nspam)
        else:
            self.warning = _("Database has no training information.  " \
                             "SpamBayes will classify all messages as " \
                             "'unsure', ready for you to train.")
        # Add an additional warning message if the user's thresholds are
        # truly odd.
        spam_cut = options["Categorization", "spam_cutoff"]
        ham_cut = options["Categorization", "ham_cutoff"]
        if spam_cut < 0.5:
            self.warning += _("<br/>Warning: we do not recommend " \
                              "setting the spam threshold less than 0.5.")
        if ham_cut > 0.5:
            self.warning += _("<br/>Warning: we do not recommend " \
                              "setting the ham threshold greater than 0.5.")
        if ham_cut > spam_cut:
            self.warning += _("<br/>Warning: your ham threshold is " \
                              "<b>higher</b> than your spam threshold. " \
                              "Results are unpredictable.")

    def create_workers(self):
        """Using the options that were initialised in __init__ and then
        possibly overridden by the driver code, create the Bayes object,
        the Corpuses, the Trainers and so on."""
        if self.is_test:
            self.use_db = "pickle"
            self.db_name = '_core_server.pickle'   # This is never saved.
        if not hasattr(self, "db_name"):
            self.db_name, self.use_db = storage.database_type([])
        self.bayes = storage.open_storage(self.db_name, self.use_db)

        # Load stats manager.
        self.stats = Stats.Stats(options,
                                 spambayes.message.Message().message_info_db)

        self.build_status_strings()

        # Don't set up the caches and training objects when running the
        # self-test, so as not to clutter the filesystem.
        if not self.is_test:
            # Create/open the Corpuses.  Use small cache sizes to avoid
            # hogging lots of memory.
            sc = get_pathname_option("Storage", "core_spam_cache")
            hc = get_pathname_option("Storage", "core_ham_cache")
            uc = get_pathname_option("Storage", "core_unknown_cache")
            for d in [sc, hc, uc]:
                storage.ensureDir(d)
            if self.gzip_cache:
                factory = GzipFileMessageFactory()
            else:
                factory = FileMessageFactory()
            age = options["Storage", "cache_expiry_days"]*24*60*60
            self.spamCorpus = ExpiryFileCorpus(age, factory, sc,
                                               '[0123456789\-]*',
                                               cacheSize=20)
            self.hamCorpus = ExpiryFileCorpus(age, factory, hc,
                                              '[0123456789\-]*',
                                              cacheSize=20)
            self.unknownCorpus = ExpiryFileCorpus(age, factory, uc,
                                                  '[0123456789\-]*',
                                                  cacheSize=20)

            # Given that (hopefully) users will get to the stage
            # where they do not need to do any more regular training to
            # be satisfied with spambayes' performance, we expire old
            # messages from not only the trained corpora, but the unknown
            # as well.
            self.spamCorpus.removeExpiredMessages()
            self.hamCorpus.removeExpiredMessages()
            self.unknownCorpus.removeExpiredMessages()

            # Create the Trainers.
            self.spam_trainer = storage.SpamTrainer(self.bayes)
            self.ham_trainer = storage.HamTrainer(self.bayes)
            self.spamCorpus.addObserver(self.spam_trainer)
            self.hamCorpus.addObserver(self.ham_trainer)

    def getNewMessageName(self):
        """The message name is the time it arrived with a uniquifier
        appended if two arrive within one clock tick of each other.
        """
        message_name = "%10.10d" % long(time.time())
        if message_name == self.last_base_message_name:
            message_name = "%s-%d" % (message_name, self.uniquifier)
            self.uniquifier += 1
        else:
            self.last_base_message_name = message_name
            self.uniquifier = 2
        return message_name

    def record_classification(self, cls, score):
        """Record the classification in the session statistics.

        cls should match one of the options["Headers", "header_*_string"]
        values.

        score is the score the message received.        
        """
        if cls == options["Headers", "header_ham_string"]:
            self.numHams += 1
        elif cls == options["Headers", "header_spam_string"]:
            self.numSpams += 1
        else:
            self.numUnsure += 1
        self.stats.RecordClassification(score)

    def buildStatusStrings(self):
        return ""

    def recreate_state(self):
        if self.prepared:    
            # Close the state (which saves if necessary)
            self.close()
        # And get a new one going.
        state = CoreState()

        state.prepare()
        return state

    def open_platform_mutex(self, mutex_name="SpamBayesServer"):
        """Implementations of a mutex or other resource which can prevent
        multiple servers starting at once.  Platform specific as no
        reasonable cross-platform solution exists (however, an old trick is
        to use a directory for a mutex, as a create/test atomic API
        generally exists).  Will set self.mutex or may throw
        AlreadyRunningException
        """

        if sys.platform.startswith("win"):
            try:
                import win32event, win32api, winerror
                # ideally, the mutex name could include either the username,
                # or the munged path to the INI file - this would mean we
                # would allow multiple starts so long as they weren't for
                # the same user.  However, as of now, the service version
                # is likely to start as a different user, so a single mutex
                # is best for now.
                # XXX - even if we do get clever with another mutex name, we
                # should consider still creating a non-exclusive
                # "SpamBayesServer" mutex, if for no better reason than so
                # an installer can check if we are running
                try:
                    hmutex = win32event.CreateMutex(None, True, mutex_name)
                except win32event.error, details:
                    # If another user has the mutex open, we get an "access
                    # denied" error - this is still telling us what we need
                    # to know.
                    if details[0] != winerror.ERROR_ACCESS_DENIED:
                        raise
                    raise AlreadyRunningException
                # mutex opened - now check if we actually created it.
                if win32api.GetLastError()==winerror.ERROR_ALREADY_EXISTS:
                    win32api.CloseHandle(hmutex)
                    raise AlreadyRunningException
                self.mutex = hmutex
                return
            except ImportError:
                # no win32all - no worries, just start
                pass
        self.mutex = None

    def close_platform_mutex(self):
        """Toss out the current mutex."""
        if sys.platform.startswith("win"):
            if self.mutex is not None:
                self.mutex.Close()
        self.mutex = None
