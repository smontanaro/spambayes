"""Skeleton class.

Should be sub-classed to provide basic generation of able-contained HTML
document.
"""

from ht2html import __version__

import os
import sys
import time
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


class Skeleton:
    #
    # for sub-classes to override
    #

    def get_banner(self):
        """Returns HTML for the top banner, or None if no banner.
        """
        return None

    def get_left_sidebar(self):
        """Returns HTML for the left sidebar or None.
        """
        return None
    # for backwards compatibility
    get_sidebar = get_left_sidebar

    def get_right_sidebar(self):
        """Returns HTML for the right sidebar or None.
        """
        return None

    def get_banner_width(self):
        """HTML `width' of banner column as a percentage.

        Should be a string that does not include the percent sign (e.g. "90").
        This affects the column containing both the banner and body text (if
        they exist).
        """
        return '90'

    def get_corner(self):
        """Returns HTML for the upper-left corner or None.

        Note that if get_banner() and get_sidebar() both return None, then
        get_corner() is ignored.  Also if both get_banner() and get_sidebar()
        return a string, but get_corner() returns None, the smallest blank
        corner possible is emitted.
        """
        return None

    def get_body(self):
        """Returns HTML for the internal document body.

        Note that using this method causes the get_sidebar() -- if there is
        one -- to run the full height of the page.  If you don't want this,
        then make sure get_cont() returns a string.
        """
        return '<b>Intentionally left blank</b>'

    def get_cont(self):
        """Returns HTML for the continuation of the body.

        When this method returns a string, and there is a get_sidebar(), the
        continuation text appears below the get_sidebar() and get_body() at
        the full width of the screen.  If there is no get_sidebar(), then
        having a get_cont() is pointless.
        """
        return None

    def get_title(self):
        """Return the title of the page.  Required."""
        return 'Intentionally left blank'

    def get_meta(self):
        """Return extra meta-data.  Must be a string."""
        import __main__
        return '<meta name="generator" content="HT2HTML/%s">' \
               % __main__.__version__

    def get_headers(self):
        """Return extra header information.  Must be a string."""
        return ''

    def get_bgcolor(self):
        """Return the background color"""
        return '#ffffff'

    def get_fgcolor(self):
        """Return foreground color"""
        return '#000000'

    def get_linkcolor(self):
        """Return link color"""
        return '#0000bb'

    def get_vlinkcolor(self):
        """Return vlink color"""
        return '#551a8b'

    def get_alinkcolor(self):
        """Return alink color"""
        return '#ff0000'

    def get_corner_bgcolor(self):
        """Return the background color for the corner"""
        return self.get_lightshade()

    # Barry's prefs
    def get_lightshade(self):
        """Return lightest of 3 color scheme shade."""
        return '#cdba96'

    def get_mediumshade(self):
        """Return middle of 3 color scheme shade."""
        return '#cc9966'

    def get_darkshade(self):
        """Return darkest of 3 color scheme shade."""
        return '#b78900'

    def get_body_attributes(self):
        """Return extra attributes for the body start tag."""
        # These are not supported in HTML, but are needed for
        # Netscape 4
        return 'marginwidth="0" marginheight="0"'

    def get_banner_attributes(self):
        """Return extra attributes for the TABLE in the banner."""
        return 'cellspacing="0" cellpadding="2"'

    def get_charset(self):
        """Return charset of pages"""
        return 'us-ascii'

    # Style sheets
    def get_stylesheet(self):
        """Return filename of CSS stylesheet."""
        return ''

    def get_stylesheet_pi(self):
        s = self.get_stylesheet()
        if s:
            return '<?xml-stylesheet href="%s" type="%s"?>\n' \
                   % (s, self.get_stylesheet_type(s))
        else:
            return ''

    def get_stylesheet_type(self, filename):
        ext = os.path.splitext(filename)[1]
        if ext == ".css":
            return "text/css"
        elif ext in (".xsl", ".xslt"):
            return "text/xslt"
        else:
            raise ValueError("unknown stylesheet language")

    def get_style(self):
        """Return the style sheet for this document"""
        s = self.body_style()
        if s:
            return 'body { %s }' % self.body_style()
        else:
            return ''

    def body_style(self):
        if self.get_stylesheet():
            # If there's an external stylesheet, rely on that for the body.
            return ''
        else:
            return 'margin: 0px;'

    # Call this method
    def makepage(self):
        banner = self.get_banner()
        sidebar = self.get_sidebar()
        corner = self.get_corner()
        body = self.get_body()
        cont = self.get_cont()
        html = StringIO()
        stdout = sys.stdout
        closed = 0
        try:
            sys.stdout = html
            self.__do_head()
            self.__start_body()
            print '<!-- start of page table -->'
            print ('<table width="100%" border="0"'
                   ' cellspacing="0" cellpadding="0">')
            if banner is not None:
                print '<!-- start of banner row -->'
                print '<tr>'
                if corner is not None:
                    self.__do_corner(corner)
                print '<!-- start of banner -->'
                print '<td width="%s%%" bgcolor="%s" class="banner">' % (
                    self.get_banner_width(), self.get_lightshade())
                print banner
                print '</td><!-- end of banner -->'
                print '</tr><!-- end of banner row -->'
            # if there is a body but no sidebar, then we'll just close the
            # table right here and put the body (and any cont) in the full
            # page.  if there is a sidebar but no body, then we still create
            # the new row and just populate the body cell with a non-breaking
            # space.  Watch out though because we don't want to close the
            # table twice
            if sidebar is None:
                print '</table><!-- end of page table -->'
                closed = 1
            else:
                print '<tr><!-- start of sidebar/body row -->'
                self.__do_sidebar(sidebar)
            if body is not None:
                if closed:
                    print body
                else:
                    self.__do_body(body)
            if not closed:
                print '</tr><!-- end of sidebar/body row -->'
                print '</table><!-- end of page table -->'
            if cont is not None:
                self.__do_cont(cont)
            self.__finish_all()
        finally:
            sys.stdout = stdout
        return html.getvalue()

    def __do_corner(self, corner):
        print '<!-- start of corner cells -->'
        print '<td width="150" valign="middle" bgcolor="%s" class="corner">' \
              % self.get_corner_bgcolor()
        # it is important not to have a newline between the corner text and
        # the table close tag, otherwise layout is messed up
        if corner is None:
            print '&nbsp;',
        else:
            print corner,
        print '</td>'
        print '<td width="15" bgcolor="%s">&nbsp;&nbsp;</td><!--spacer-->' % (
            self.get_lightshade())
        print '<!-- end of corner cells -->'

    def __do_sidebar(self, sidebar):
        print '<!-- start of sidebar cells -->'
        print '<td width="150" valign="top" bgcolor="%s" class="sidebar">' % (
            self.get_lightshade())
        print sidebar
        print '</td>'
        print '<td width="15">&nbsp;&nbsp;</td><!--spacer-->'
        print '<!-- end of sidebar cell -->'

    def __do_body(self, body):
        print '<!-- start of body cell -->'
        print '<td valign="top" width="%s%%" class="body"><br>' % (
            self.get_banner_width())
        print body
        print '</td><!-- end of body cell -->'

    def __do_cont(self, cont):
        print '<div class="body">'
        print '<div class="continuation">'
        print '<!-- start of continued wide-body text -->'
        print cont
        print '<!-- end of continued wide-body text -->'
        print '</div>'
        print '</div>'

    def __do_head(self):
        """Return the HTML <head> stuff."""
        print '''\
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
%(xmlstyle)s<html>
<!-- THIS PAGE IS AUTOMATICALLY GENERATED.  DO NOT EDIT. -->
<!-- %(time)s -->
<!-- USING HT2HTML %(version)s -->
<!-- SEE http://ht2html.sf.net -->
<!-- User-specified headers:
Title: %(title)s
%(headers)s
-->

<head>
<title>%(title)s</title>
<meta http-equiv="Content-Type" content="text/html; charset=%(charset)s">
%(meta)s
%(style)s
</head>''' % {'title'   : self.get_title(),
              'headers' : self.get_headers(),
              'meta'    : self.get_meta(),
              'time'    : time.ctime(time.time()),
              'version' : __version__,
              'charset' : self.get_charset(),
              'style'   : self.__do_styles(),
              'xmlstyle': self.get_stylesheet_pi(),
              }

    def __do_styles(self):
        # assemble all the style information we have to produce the
        # appropriate LINK and STYLE elements
        stylesheet = self.get_stylesheet()
        localstyle = self.get_style()
        s = ''
        if stylesheet and stylesheet.strip():
            stylesheet = stylesheet.strip()
            type = self.get_stylesheet_type(stylesheet)
            s = '<link rel="STYLESHEET" href="%s" type="%s">' \
                % (stylesheet, type)
        if localstyle and localstyle.strip():
            localstyle = '<style type="text/css">\n%s\n</style>' \
                         % localstyle.strip()
            if stylesheet:
                s = s + "\n" + localstyle
            else:
                s = localstyle
        return s

    def __start_body(self):
        print '''\
<body bgcolor="%(bgcolor)s" text="%(fgcolor)s"
      %(extraattrs)s
      link="%(linkcolor)s"  vlink="%(vlinkcolor)s"
      alink="%(alinkcolor)s">''' % {
            'bgcolor'   : self.get_bgcolor(),
            'fgcolor'   : self.get_fgcolor(),
            'linkcolor' : self.get_linkcolor(),
            'vlinkcolor': self.get_vlinkcolor(),
            'alinkcolor': self.get_alinkcolor(),
            'extraattrs': self.get_body_attributes(),
            }

    def __finish_all(self):
        print '</body></html>'



# test script
class _Skeleton(Skeleton):
    def get_banner(self):
        return '<b>The Banner</b>'

    def get_sidebar(self):
        return '''<ul><li>Sidebar line 1
        <li>Sidebar line 2
        <li>Sidebar line 3
        </ul>'''

    def get_corner(self):
        return '<center><em>CORNER</em></center>'

    def get_body(self):
        return 'intentionally left blank ' * 110

    def get_cont(self):
        return 'wide stuff ' * 100

    def get_corner_bgcolor(self):
        return 'yellow'

    def get_banner_width(self):
        return "80"


if __name__ == '__main__':
    t = _Skeleton()
    print t.makepage()
