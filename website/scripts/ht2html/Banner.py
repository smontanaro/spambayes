"""Generate a site links table for use in a banner.
"""

import sys
try:
    from cStringIO import StringIO
except IOError:
    from StringIO import StringIO

class Banner:
    def __init__(self, links, cols=4):
        """Initialize the Banner instance.

        This class is intended to be a mixin-class with Skeleton.

        links must be a list of 2-tuples of the form: (URL, text).  If URL is
        None, then the text is not hyperlinked.  These are arranged in a table
        in order, evenly in the specified number of columns.

        """
        self.__links = links
        self.__cols = cols
        rows, leftover = divmod(len(links), self.__cols)
        if leftover:
            rows = rows + 1
        self.__rows = rows

    def get_banner(self):
        stdout = sys.stdout
        html = StringIO()
        try:
            sys.stdout = html
            self.__start_table()
            self.__do_table()
            self.__end_table()
        finally:
            sys.stdout = stdout
        return html.getvalue()

    def __start_table(self):
        print '<!-- start of site links table -->'
        print '<table width="100%" border="0"'
        print self.get_banner_attributes()
        print '       bgcolor="%s">' % (
            self.get_bgcolor())
        print '<tr>'

    def __end_table(self):
        print '</tr>'
        print '</table><!-- end of site links table -->'

    def __do_table(self):
        col = 0
        for item in self.__links:
            if len(item) == 3:
                url, text, extra = item
            else:
                url, text = item
                extra = ''
            if not url:
                s = text + extra
            else:
                s = '<a href="%s">%s</a>%s' % (url, text, extra)
            if col >= self.__cols:
                # break the row
                print '</tr><tr>'
                col = 0
            print '    <td bgcolor="%s">' % self.get_lightshade()
            print s
            print '    </td>'
            col = col + 1
        # fill rest of row with non-breaking spaces.
        while col and col < self.__cols:
            print '    <td bgcolor="%s">' % self.get_lightshade()
            print '&nbsp;&nbsp;</td>'
            col = col + 1


from Skeleton import _Skeleton

class _Banner(_Skeleton, Banner):
    def __init__(self, links):
        Banner.__init__(self, links)

    def get_banner(self):
        return Banner.get_banner(self)

if __name__ == '__main__':
    t = _Banner([('page1.html', 'First Page'),
                 ('page2.html', 'Second Page'),
                 ('page3.html', 'Third Page'),
                 ('page4.html', 'Fourth Page'),
                 (None,         '<b>Fifth Page</b>'),
                 ('page6.html', 'Sixth Page'),
                 ])
    print t.makepage()
