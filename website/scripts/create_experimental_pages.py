#!/usr/bin/env python

"""create_experimental_pages.py

Generate any dynamic documentation for the experimental pages.
"""

# This module is part of the spambayes project, which is Copyright 2002-5
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tony Meyer <ta-meyer@ihug.co.nz>"
__credits__ = "All the spambayes folk."

import re
import textwrap

from spambayes.Options import defaults
from spambayes.OptionsClass import OptionsClass
from spambayes.OptionsClass import PATH, INTEGER, REAL, HEADER_NAME

# Replace common regexes with human-readable <wink> names.
# If the value is None, then skip those options, as they are not
# human-editable.
nice_regex_names = {PATH : "Filename",
                    INTEGER : "Whole number",
                    REAL : "Number",
                    HEADER_NAME : "Email Header Name",
                    r"[\S]+" : "Alphanumeric characters",
                    }

table_header = """Title: SpamBayes: Experimental Options.
Author-Email: spambayes@python.org
Author: SpamBayes

<h2>Available Experimental Options</h2>

    <table border='1' cellpadding='2' cellspacing='2'>
      <tr style="font-weight:bold;">
        <td>Section</td>
        <td>Option Name</td>
        <td>Valid Values</td>
        <td>Default</td>
        <td>Comments</td>
      </tr>
"""

def main():
    options = OptionsClass()
    options.load_defaults(defaults)

    # Create HTML page that outline the available options.
    output = open("experimental_options.ht", "w")
    keys = options._options.keys()
    keys.sort()
    output.write(table_header)
    for sect, opt_name in keys:
        doc = options._options[sect, opt_name].doc()
        if not doc.startswith("(EXPERIMENTAL)"):
            continue
        output.write('<tr style="height:1em">&nbsp;</tr>\n')
        opt = options.get_option(sect, opt_name)

        # Replace regex's with readable descriptions.
        if opt.allowed_values in nice_regex_names:
            replacement = nice_regex_names[opt.allowed_values]
            if replacement is None:
                continue
            opt.allowed_values = (replacement,)

        output.write(opt.as_documentation_string(sect).\
                     replace("(EXPERIMENTAL) ", ""))
        output.write('\n')
    output.write("</table>\n\n")
    output.close()

    # Create pre-filled configuration file with comments.
    output = open("experimental.ini", "w")
    keys = options._options.keys()
    keys.sort()
    currentSection = None
    for sect, opt in keys:
        doc = options._options[sect, opt].doc()
        if doc.startswith("(EXPERIMENTAL)"):
            doc = doc[15:]
        else:
            continue
        if sect != currentSection:
            if currentSection is not None:
                output.write('\n')
            output.write('[')
            output.write(sect)
            output.write("]\n")
            currentSection = sect
        if not doc:
            doc = "No information available, sorry."
        doc = re.sub(r"\s+", " ", doc)
        output.write("\n# %s\n" % ("\n# ".join(textwrap.wrap(doc)),))
        options._options[sect, opt].write_config(output)
    output.close()

if __name__ == "__main__":
    main()
