#!/usr/bin/env python

"""Configuration file parser with update facility.

Handles configuration files in the exact manner as ConfigParser, but
has the ability to update the configuration files.  Handles multiple
files, and does not touch whitespace or comment lines.

c.f. ConfigParser

class:

UpdatableConfigParser -- responsible for for parsing a list of
                         configuration files, and managing the parsed
                         database, including updating those files.

    methods:

    UpdatableConfigParser inherits all of ConfigParser's methods, and
    adds the following:

    changed_options()
        returns a dictionary of file_name : section_dictionary
        where section_dictionary is a dictionary of
        section_name : option_dictionary and option_dictionary is
        a dictionary of option_name : option_value

    restore_option(section, option)
        restores the named option to the value in the file the option
        was loaded from (overwriting any changes made to the value in
        memory)

    update(prune=False, add_missing=False)
        update all files that have been loaded into the UpdatableConfigParser
        to their current values.  Iff prune is True then sections/options
        that have been removed (via remove_section or remove_option) will
        be removed from the files.  Iff add_missing is True, any options
        *that have been changed since init/the last update* which are not
        in the file will be added to the appropriate section.

    update_file(fp, prune=False, add_missing=False)
        update only the specified individual file, as per update()

    update_files(filename_list, prune=False, add_missing=False)
        update all files in the given list, as per update()

    write_updated(fp)
        create a new configuration file, as with ConfigParser.write(), but
        only write those options that have been changed since init
        or the last update

    Configuration options:        

    UpdatableConfigParser.vi = ": "
        This is the separator used between an option name and value. The
        value is overridden on execution of the read(), readfp(), or
        update methods by the last separator found in the read file /
        file-like-object, unless the UpdatableConfigParser.lock_vi option
        is set to True.  Note that only update(), update_file(), and
        write_updated() will use this value - write() will *not*.

    UpdatableConfigParser.record_original_values = True
        UpdatableConfigParser has two methods of recording changes to options.
        The default method is to record all original values, and compare these
        to current values on update.  This requires additional memory, but
        means that the original values are accessable if required (to revert,
        for example), and means that if an option is changed, then changed back
        to the original value, no update is made.
        The alternative method is to simply record any changes made (via the
        set() method).  This, in general, requires less memory, but unnecessary
        updates (as described above) may be made.

    Issues to be aware of:
        If you load in multiple configuration files, and the files contain
        conflicting values for an option, the value in the last file to be
        loaded will be used (as with ConfigParser).  However, if you change
        the value of this option, and then update the previous file(s), the
        value in the files will be recorded as the new value, even if the
        original value was not the one loaded.

        If you read a file-like object (using ConfigParser's readfp) and
        the object to read has a filename attribute, then it must have a
        write function as well, and the update functions will attempt to
        update it.  If no filename attribute is present (or the filename
        is <???>), then no updating will be attempted on these sources.

        After calling any of the update functions (update(), update_file(),
        or update_files()) the 'original values' recorded for those options
        changed are updated to the new values in the file(s).  This means
        that subsequent calls to an update function will have no effect.
        For example: we have FileA and FileB, both containing OptionC.  We
        modify the value for OptionC.  If we call update(), *both* FileA
        and FileB will contain the new value for OptionC.  If we call
        update_file(FileA), then *only* FileA will contain the new value
        for OptionC, and if we *subsequently* call update_file(FileB), no
        changes will be made.  To modify more than one source file, but
        not all source files, use the update_files() function.
        
        The os function tempnam() is currently used to get hold of a
        temp file to create the new config file before overwriting the
        old one.  This gives a runtime warning about a security risk. It
        would be nice if someone would change this to some other temp
        file system.
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

from ConfigParser import ConfigParser, ParsingError
from ConfigParser import DEFAULTSECT, NoSectionError, NoOptionError
from os import rename, remove, tempnam
import types

issues = """
A file like:
[sect1]
opt1 = val1
[sect2]
opt2 = val2
[sect1]
opt1 = val1

or even like:
[sect1]
opt1 = val1
[sect2]
opt2 = val2
[sect1]
opt3 = val3

will not work as it should with add_missing set to True.
"""

class UpdatableConfigParser(ConfigParser):
    def __init__(self, defaults=None):
        ConfigParser.__init__(self, defaults)
        self.__data = {}
        self.__changed_options = {}
        self.__pruned = {}
        # override base class
        self.__sections = self._ConfigParser__sections
        self._ConfigParser__read = self.__read
        # configuration defaults
        self.vi = ": "
        self.lock_vi = False
        self.record_original_values = True

    def remove_option(self, section, option):
        # c.f. ConfigParser.remove_option()
        existed = ConfigParser.remove_option(self, section, option)
        if existed:
            for sect, opt in self.__data.keys():
                if sect == section and opt == option:
                    del self.__data[(sect, opt)]
                    self.__pruned[sect] = opt
        return existed

    def remove_section(self, section):
        # c.f. ConfigParser.remove_section()
        existed = ConfigParser.remove_section(self, section)
        if existed:
            for sect, opt in self.__data.keys():
                if sect == section:
                    del self.__data[(sect, opt)]
                    self.__pruned[sect] = None
        return existed

    def set(self, section, option, value):
        # c.f. ConfigParser.set()
        ConfigParser.set(self, section, option, value)
        if self.record_original_values == False:
            for file, sect in self.__data.items():
                if sect == section:
                    sectdict = {}
                    optdict = {}
                    if self.__changed_options.has_key(file):
                        sectdict = self.__changed_options[file]
                        if sectdict.has_key(section):
                            optdict = sectdict[section]
                    optdict[option] = value
                    sectdict[section] = optdict
                    self.__changed_options[file] = sectdict

    def __read(self, fp, fpname):
        # c.f. ConfigParser.__read()
        cursect = None                            # None, or a dictionary
        optname = None
        lineno = 0
        e = None                                  # None, or an exception
        while True:
            line = fp.readline()
            if not line:
                break
            lineno = lineno + 1
            # comment or blank line?
            if line.strip() == '' or line[0] in '#;':
                continue
            if line.split(None, 1)[0].lower() == 'rem' and line[0] in "rR":
                # no leading whitespace
                continue
            # continuation line?
            if line[0].isspace() and cursect is not None and optname:
                value = line.strip()
                if value:
                    cursect[optname] = "%s\n%s" % (cursect[optname], value)
            # a section header or option header?
            else:
                # is it a section header?
                mo = self.SECTCRE.match(line)
                if mo:
                    sectname = mo.group('header')
                    if sectname in self.__sections:
                        cursect = self.__sections[sectname]
                    elif sectname == DEFAULTSECT:
                        cursect = self.__defaults
                    else:
                        cursect = {'__name__': sectname}
                        self.__sections[sectname] = cursect
                    # So sections can't start with a continuation line
                    optname = None
                # no section header in the file?
                elif cursect is None:
                    raise MissingSectionHeaderError(fpname, lineno, `line`)
                # an option line?
                else:
                    mo = self.OPTCRE.match(line)
                    if mo:
                        optname, vi, optval = mo.group('option', 'vi', 'value')
                        if self.lock_vi == False:
                            self.vi = vi
                        if vi in ('=', ':') and ';' in optval:
                            # ';' is a comment delimiter only if it follows
                            # a spacing character
                            pos = optval.find(';')
                            if pos != -1 and optval[pos-1].isspace():
                                optval = optval[:pos]
                        optval = optval.strip()
                        # allow empty values
                        if optval == '""':
                            optval = ''
                        optname = self.optionxform(optname.rstrip())
                        cursect[optname] = optval
                        sectname = cursect['__name__']
                        self.__updateData(fpname, sectname, optname, optval)
                    else:
                        # a non-fatal parsing error occurred.  set up the
                        # exception but keep going. the exception will be
                        # raised at the end of the file and will contain a
                        # list of all bogus lines
                        if not e:
                            e = ParsingError(fpname)
                        e.append(lineno, `line`)
        # if any parsing errors occurred, raise an exception
        if e:
            raise e

    def __updateData(self, filename, sectname, optname, value):
        if filename == "<???>":
            return
        if self.record_original_values == True:
            self.__updateDataIncludingOriginalValue(filename,
                                                     sectname,
                                                     optname,
                                                     value)
        else:
            self.__updateDataNoOriginalValue(filename, sectname,
                                              optname)

    def __updateDataIncludingOriginalValue(self, filename,
                                            sectname, optname, value):
        if self.__data.has_key((sectname, optname)):
            existing_files, original = self.__data[(sectname, optname)]
            if filename not in existing_files:
                existing_files += filename,
            self.__data[(sectname, optname)] = (existing_files, value)
        else:
            self.__data[(sectname, optname)] = ((filename,), value)

    def __updateDataNoOriginalValue(self, filename, sectname, optname):
        if self.__data.has_key((sectname, optname)):
            existing_data = self.__data[(sectname, optname)]
            if filename not in existing_files:
                existing_files += filename,
            self.__data[(sectname, optname)] = existing_files
        else:
            self.__data[(sectname, optname)] = (filename,)

    def changed_options(self):
        """Return any options that have changed since reading or updating."""
        if self.record_original_values == False:
            return self.__changed_options
        else:            
            files_to_update = {}
            for sectname, sectdict in self.__sections.items():
                if sectname == '__name__':
                    continue
                for optname, optvalue in sectdict.items():
                    if optname == '__name__':
                        continue
                    if self.__data.has_key((sectname, optname)):
                        source_files, original = self.__data[(sectname, optname)]
                        if optvalue != original:
                            for file in source_files:
                                if files_to_update.has_key(file):
                                    # we are already updating this file
                                    section_names = files_to_update[file]
                                    if section_names.has_key(sectname):
                                        # this section is already being updated
                                        option_names = section_names[sectname]
                                    else:
                                        option_names = {}
                                else:
                                    section_names = {}
                                    option_names = {}
                                option_names[optname] = optvalue
                                section_names[sectname] = option_names
                                files_to_update[file] = section_names
            return files_to_update

    def restore_option(section, option):
        """ restore an option to the value in the source file"""
        if self.__data.has_key((section, option)):
            if self.record_original_values:
                file, original = self.__data[(section, option)]
            else:
                file = self.__data[(section, option)]
                c = ConfigParser()
                c.read(file)
                if c.has_option(section, option):
                    original = c.get(section, option)
                else:
                    raise NoOptionError(section, option)
            self.set(section, option, original)
        else:
            raise NoOptionError(section, option)

    def update(self, prune=False, add_missing=False):
        """Write any updates to the appropriate file(s)."""
        files_to_update = self.changed_options()
        for file, info in files_to_update.items():
            old_cfg = open(file, "r")
            self.__updateFile(old_cfg, info, prune, add_missing)
            old_cfg.close()

    def update_file(self, fp, prune=False, add_missing=False):
        """Write any updates to the appropriate file."""
        files_to_update = self.changed_options()
        if files_to_update.has_key(fp.name):
            self.__updateFile(fp, files_to_update[fp.name],
                              prune, add_missing)

    def update_files(self, files, prune=False, add_missing=False):
        """Write any updates to the appropriate files."""
        files_to_update = self.changed_options()
        for file in files:
            if files_to_update.has_key(file):
                old_cfg = open(file, "r")
                self.__updateFile(old_cfg, files_to_update[file],
                                  prune, add_missing)
                old_cfg.close()

    def write_updated(self, fp):
        """Write all changed options to the specified file."""
        files_to_update = self.changed_options()
        c = ConfigParser()
        for file, info in files_to_update.items():
            for sectname, optdict in info.items():
                if sectname != "__name__":
                    if not c.has_section(sectname):
                        c.add_section(sectname)
                    for key, value in optdict.items():
                        if key != "__name__":
                            c.set(sectname, key, str(value))
        c.write(fp)

    def __updateFile(self, old_cfg, info, prune=False, add_missing=False):
        temp_name = tempnam()
        new_cfg = open(temp_name, "w")
        current_section = None
        update_section = None
        new_value = None
        lineno = 0
        e = None                                  # None, or an exception
        while True:
            line = old_cfg.readline()
            if not line:
                break
            lineno = lineno + 1
            # comment or blank line?
            if line.strip() == '' or line[0] in '#;':
                new_cfg.write(line)
                continue
            if line.split(None, 1)[0].lower() == 'rem' and line[0] in "rR":
                # no leading whitespace
                new_cfg.write(line)
                continue
            # XXX we need to handle continuation lines
            # a section header or option header?
            else:
                # is it a section header?
                mo = self.SECTCRE.match(line)
                if mo:
                    if add_missing == True:
                        # we might have options to add from the previous section
                        if update_section is not None:
                            while len(update_section) > 0:
                                optname, optval = update_section.values()[0]
                                new_cfg.write(optname + self.vi + optval + '\n')
                                del update_section[optname]
                            del info[current_section]
                    new_cfg.write(line)
                    current_section = mo.group('header')
                    if info.has_key(current_section):
                        update_section = info[current_section]
                    else:
                        update_section = None
                # an option line?
                else:
                    if current_section is None:
                        # we don't care
                        new_cfg.write(line)
                        continue
                    mo = self.OPTCRE.match(line)
                    if mo:
                        optname, vi, optval = mo.group('option', 'vi', 'value')
                        if self.lock_vi == False:
                            self.vi = vi
                        optname = optname.rstrip().lower()
                        if self.__pruned.has_key(current_section):
                            opt = self.__pruned[current_section]
                            if opt is None or opt == optname:
                                continue
                        if update_section is not None and \
                           update_section.has_key(optname):
                            new_cfg.write(optname + ' ' + vi + ' ' + \
                                          update_section[optname] + '\n')
                            self.__updateData(old_cfg.name, current_section, \
                                               optname, update_section[optname])
                            del update_section[optname]
                        else:
                            new_cfg.write(line)
                    else:
                        # a non-fatal parsing error occurred.  set up the
                        # exception but keep going. the exception will be
                        # raised at the end of the file and will contain a
                        # list of all bogus lines
                        if not e:
                            e = ParsingError(file)
                        e.append(lineno, `line`)
        # if any parsing errors occurred, raise an exception
        if e:
            raise e
        if add_missing == True:
            # add any new sections
            while len(info) > 0:
                sectname, optdict = info.values()[0]
                new_cfg.write('[' + sectname + "]\n")
                while len(optdict) > 0:
                    optname, optval = optdict.values()[0]
                    new_cfg.write(optname + vi + optval + '\n')
                    del optdict[optname]
                del info[sectname]
        new_cfg.close()
        old_cfg.close()
        try:
            rename(temp_name, old_cfg.name)
        except OSError:
            try:
                remove(old_cfg.name)
                rename(temp_name, old_cfg.name)
            except OSError:
                print "Warning: Could not complete config " \
                      "update of %s" % old_cfg.name
        # the caller expects old_cfg to be an open reference to the
        # config file since this is the state on calling, so we return
        # an open reference to the *new* config file, even though
        # the caller will probably just close this
        old_cfg = open(old_cfg.name, "r")
