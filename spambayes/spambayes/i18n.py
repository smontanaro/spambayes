"""Internationalisation

Classes:
    LanguageManager - Interface class for languages.

Abstract:

Manages the internationalisation (i18n) aspects of SpamBayes.
"""

# This module is part of the spambayes project, which is Copyright 2002-4
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Hernan Martinez Foffani <hfoffani@yahoo.com>"
__credits__ = "Tony Meyer, All the SpamBayes folk."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

import os
import sys
from locale import getdefaultlocale
from gettext import translation, NullTranslations
# Note, we must not import spambayes.Options, or Outlook will not be happy.

## Set language environment for gettext and for dynamic load of dialogs.
##
## Our directory layout is:
##   spambayes
##       spambayes
##           i18n.py             <--- this file
##       languages               <--- the directory for lang packs
##           es                  <-- generic language data
##               DIALOGS
##               LC_MESSAGES
##               __init__.py     <-- resourcepackage __init__.py
##              ui.html          <-- web interface translation
##           es_ES               <-- specific language/country data.
##               DIALOGS         <-- resource dialogs
##               LC_MESSAGES     <-- gettext messages files
##               __init__.py     <-- resourcepackage __init__.py
##              ui.html          <-- web interface translation
##           zn
##           zn_TW
##       Outlook2000
##       utilities
##       ..etc..


class LanguageManager:
    def __init__(self, directory=os.path.dirname(__file__)):
        """Initialisation.

        'directory' is the parent directory of the 'languages'
        directory.  It defaults to the directory of this module."""
        self.current_langs_codes = []
        self.local_dir = os.path.join(directory, "..", "languages")
        self._sys_path_modifications = []

    def set_language(self, lang_code=None):
        """Set a language as the current one."""
        if not lang_code:
            return
        self.current_langs_codes = [ lang_code ]
        self._rebuild_syspath_for_dialogs()
        self._install_gettext()
        
    def locale_default_lang(self):
        """Get the default language for the locale."""
        # Note that this may return None.
        return getdefaultlocale()[0] 
            
    def add_language(self, lang_code=None):
        """Add a language to the current languages list.

        The list acts as a fallback mechanism, where the first language of
        the list is used if possible, and if not the second one, and so on.
        """
        if not lang_code:
            return
        self.current_langs_codes.insert(0, lang_code)
        self._rebuild_syspath_for_dialogs()
        self._install_gettext()

    def clear_language(self):
        """Clear the current language(s) and set SpamBayes to use
        the default."""
        self.current_langs_codes = []
        self._clear_syspath()
        lang = NullTranslations()
        lang.install()

    def import_ui_html(self):
        """Load and return the appropriate ui_html.py module for the
        current language."""
        for language in self.current_langs_codes:
            moduleName = 'languages.%s.i18n_ui_html' % (language, )
            try:
                module = __import__(moduleName, {}, {}, ('languages',
                                                         language))
            except ImportError:
                # That language isn't available - fall back to the
                # next one.
                pass
            else:
                return module
        # Nothing available - use the default.
        from spambayes.resources import ui_html
        return ui_html

    def _install_gettext(self):
        """Set the gettext specific environment."""
        lang = translation("messages", self.local_dir,
                            self.current_langs_codes, fallback=True)
        lang.install()

    def _rebuild_syspath_for_dialogs(self):
        """Add to sys.path the directories of the translated dialogs.

        For each language of the current list, we add two directories,
        one for language code and country and the other for the language
        code only, so we can simulate the fallback procedures."""
        self._clear_syspath()
        for lcode in self.current_langs_codes:
            code_and_country = os.path.join(self.local_dir, lcode,
                                            'DIALOGS')
            code_only = os.path.join(self.local_dir, lcode.split("_")[0],
                                     'DIALOGS')
            if code_and_country not in sys.path:
                sys.path.append(code_and_country)
                self._sys_path_modifications.append(code_and_country)
            if code_only not in sys.path:
                sys.path.append(code_only)
                self._sys_path_modifications.append(code_only)

    def _clear_syspath(self):
        """Clean sys.path of the stuff that we put in it."""
        for path in self._sys_path_modifications:
            sys.path.remove(path)
        self._sys_path_modifications = []


def test():
    lm = LanguageManager()
    print "INIT: len(sys.path): ", len(sys.path)
    print "TEST default lang"
    lm.set_language(lm.locale_default_lang())
    print "\tCurrent Languages: ", lm.current_langs_codes
    print "\tlen(sys.path): ", len(sys.path)
    print "\t", _("Help")

    print "TEST clear_language"
    lm.clear_language()
    print "\tCurrent Languages: ", lm.current_langs_codes
    print "\tlen(sys.path): ", len(sys.path)
    print "\t", _("Help")

    print "TEST set_language"
    for langcode in ["kk_KK", "z", "", "es", None, "es_AR"]:
        print "lang: ", langcode

        lm.set_language(langcode)
        print "\tCurrent Languages: ", lm.current_langs_codes
        print "\tlen(sys.path): ", len(sys.path)
        print "\t", _("Help")

    lm.clear_language()

    print "TEST add_language"
    for langcode in ["kk_KK", "z", "", "es", None, "es_AR"]:
        print "lang: ", langcode

        lm.add_language(langcode)
        print "\tCurrent Languages: ", lm.current_langs_codes
        print "\tlen(sys.path): ", len(sys.path)
        print "\t", _("Help")

if __name__ == '__main__':
    test()
