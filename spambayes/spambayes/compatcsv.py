#!/usr/bin/env python

"""Implement just enough of a csv parser to support sb_dbexpimp.py's needs."""

import sys
import re

if sys.platform == "windows":
    EOL = "\r\n"
elif sys.platform == "mac":
    EOL = "\r"
else:
    EOL = "\n"

class reader:
    def __init__(self, fp):
        self.fp = fp

    def __iter__(self):
        return self

    def next(self):
        return self.parse_line(self.fp.next())

    def parse_line(self, line):
        """parse the line.

        very simple assumptions:
        * separator is a comma
        * fields are only quoted with quotation marks and only
          quoted if the field contains a comma or a quotation mark
        * embedded quotation marks are doubled
        """

        result = []
        while line:
            if line[0] == '"':
                # search for ending quotation mark
                match = re.match('"(.*?)"[^"]', line)
                if match is None:
                    # embedded newline
                    line = line + self.fp.next()
                    continue
                else:
                    field = match.group(1)
                field = field.replace('""', '"')
                try:
                    dummy = unicode(field, "ascii")
                except UnicodeError:
                    field = unicode(field, "utf-8")
                result.append(field)
                line = line[len(field)+3:]
            
            else:
                # field is terminated by a comma or EOL
                match = re.match("(.*?)(,|%s)"%EOL, line)
                if match is None:
                    print "parse error:", line
                    raise
                field = match.group(1)
                try:
                    dummy = unicode(field, "ascii")
                except UnicodeError:
                    field = unicode(field, "utf-8")
                result.append(field)
                line = line[len(field)+len(match.group(2))]
        return result

class writer:
    def __init__(self, fp):
        self.fp = fp

    def writerow(self, row):
        result = []
        for item in row:
            if isinstance(item, unicode):
                item = item.encode("utf-8")
            else:
                item = str(item)
            if re.search('["\n,]', item) is not None:
                item = '"%s"' % item.replace('"', '""')
            result.append(item)

        result = ",".join(result)
        self.fp.write(result+EOL)
