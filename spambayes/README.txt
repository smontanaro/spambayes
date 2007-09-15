Copyright (C) 2002-2007 Python Software Foundation; All Rights Reserved

The Python Software Foundation (PSF) holds copyright on all material
in this project.  You may use it under the terms of the PSF license;
see LICENSE.txt.


Overview
========

SpamBayes is a tool used to segregate unwanted mail (spam) from the mail you
want (ham).  Before SpamBayes can be your spam filter of choice you need to
train it on representative samples of email you receive.  After it's been
trained, you use SpamBayes to classify new mail according to its spamminess
and hamminess qualities.

When SpamBayes filters your email, it compares each unclassified message
against the information it saved from training and makes a decision about
whether it thinks the message qualifies as ham or spam, or if it's unsure
about how to classify the message.  It then passes this information on to
your mail client.  Unless you are using IMAP or Outlook, this means it adds
a header to each message, X-SpamBayes-Classification: spam|ham|unsure.  You
can then filter on this header, to file away suspected spam into its own
mail folder for example.  IMAP and Outlook both have the capacity to do the
filtering themselves, so the header is not necessary.

If you have any questions that this document does not answer, you should
definitely try the SpamBayes website <http://spambayes.org>, and in
particular, try reading the list of frequently asked questions:
<http://spambayes.org/faq.html>


Prerequisites
=============

You need to have Python 2.2 or later (2.3 is recommended).  You can
download Python from <http://www.python.org/download/>.
Many distributions of UNIX now ship with Python - try typing 'python' 
at a shell prompt.

You also need version 2.4.3 or above of the Python "email" package.
If you're running Python 2.2.3 or above then you already have a good
version of the email package.

If not, you can download email version 2.5 from the email SIG at
<http://www.python.org/sigs/email-sig> and install it - unpack the
archive, cd to the email-2.5 directory and type "python setup.py
install".  This will install it into your Python site-packages
directory.  You'll also need to move aside the standard "email"
library - go to your Python "Lib" directory and rename "email" to
"email_old".

To run the Outlook plug-in from source, you also need have the win32com
extensions installed (win32all-149 or above), which you can get from
<http://starship.python.net/crew/mhammond>.

When installing SpamBayes on some *nix systems, such as Debian, you may need
to install the python-dev package.  This can be done with a command like
"apt-get install python-dev" (this may vary between distributions).


Getting the software
====================

If you don't already have it, you can download the latest release of
SpamBayes from <http://spambayes.org/download.html>.


For the Really Impatient
========================

If you get your mail from a POP3 server, then all you should need to do
to get running is change your mail client to send and receive mail from
"localhost", and then run "python setup.py install" and then
"python scripts/sb_server.py -b" in the directory you expanded the
SpamBayes source into.  This will open a web browser window - click the
"Configuration" link at the top right and fill in the various settings.


Installation
============

The first thing you need to do is run "python setup.py install" in the
directory that you expanded the SpamBayes archive into (to do this, you
probably need to open up a console window/command prompt/DOS prompt, 
and navigate to the appropriate directory with the "cd" command).  This
will install all the files that you need into the correct locations.
After this, you can delete that directory; it is no longer required.

Before you begin
----------------

It's a good idea to train SpamBayes before you start using it, although
this isn't compulsory.  You need to save your incoming email for awhile,
segregating it into two piles, known spam (bad mail) and known ham (good
mail).  It's best to train on recent email, because your interests and the
nature of what spam looks like change over time.  Once you've collected a
fair portion of each (anything is better than nothing, but it helps to have
a couple hundred of each), you can tell SpamBayes, "Here's my ham and my
spam".  It will then process that mail and save information about different
patterns which appear in ham and spam.  That information is then used
during the filtering stage.  See the "Training" section below for details.

For more detailed instructions, please read the appropriate section below
(if you don't know, you probably want the POP3 Proxy section).

Outlook plug-in
---------------

For information about how to use the Outlook plug-in, please read the
"about.html" file in the Outlook2000 directory.  If you want to run the
Outlook plug-in from source, you should also read the "README.txt" file
in that directory.


POP3 Proxy
----------

You need to configure your email client to talk to the proxies instead of
the real email servers.  Change your equivalent of "pop3.example.com" to
"localhost" (or to the name of the machine you're running the proxy on) in
your email client's setup, and do the same with your equivalent of
"smtp.example.com".

Now launch SpamBayes, either by running "pop3proxy_service.py install"
and then "net start pop3proxy" (for those using Windows 2000, Windows NT
or Windows XP), or the "sb_server.py" script (for everyone else).  Note
that if you want to use the service, you need to also have Mark
Hammond's win32 extensions for Python installed:

<http://starship.python.net/crew/mhammond/win32/Downloads.html>

All you need to do to configure SpamBayes is to open a web page to
<http://localhost:8880>, click on the "Configuration" link at the top
right, and fill in the relevant details.  Everything should be OK with the
defaults, except for the POP3 and SMTP server information at the top, which
is required. For the local ports to proxy on, if you are only proxying one
server, and you are using Windows, then 110 is probably the best port to
try first.  If that doesn't work, try using 8110 (and if you are proxying
multiple ports, continue with 8111, 8112, and so on).  Note that *nix users
may not have permission to bind ports lower than 1025, so should choose
numbers higher than that.

When you check your mail in your mail client now, messages should have an
addition SpamBayes header (you may not be able to see this by default).
You should be able to create a mail folder called "Spam" and set up a
filtering rule that puts emails with an "X-Spambayes-Classification: spam"
header into that folder.

Note that if you set your mail client to delete the mail without
downloading the whole message (like Outlook Express's "delete from server"
rule) that you may not get accurate results - the classification will
be based on the headers only, not the body.  This is not recommended.


IMAP Filter
-----------

To configure SpamBayes, run "sb_imapfilter.py -b", which should open a web
page to <http://localhost:8880>, click on the "Configuration" link at the
top right, and fill in the relevant details.  Everything should be OK with
the defaults, except for the server information at the top.

You now need to let SpamBayes know which IMAP folders it should work with.
Use the "configure folders to filter" and "configure folders to train"
links on the web page <http://localhost:8880> to do this.  The 'filter'
folders are those that will have mail that you want to identify as either
ham (good) or spam (bad) - this will probably be your Inbox.  The 'train'
folders are those that contain examples of ham and spam, to assist SpamBayes
with its classification.  (Folders can be used for both training and
filtering).

You then need to set the IMAP filter up to run periodically.  At the moment,
you'll need to do this from a command (or DOS) prompt.  You should run the
command "python sb_imapfilter.py -c -t -l 5".  The '-c' means that the script
should classify new mail, the '-t' means that the script should train any
mail that you have told it to, and the '-l 5' means that the script should
execute every five minutes (you can change this as required).


XML-RPC Server
--------------

The XML-RPC server (new in 1.1a4) web interface is almost identical the the
POP3 proxy user interface.  Instead of proxying POP3 communications though
it provides an XML-RPC server your (typically non-mail) applications can use
to score content submissions.

To install and configure it:

1. Unpack and install the distribution:

    tar xvfz spambayes-1.1a4.tar.gz
    cd spambayes-1.1a4
    python setup.py install

2. Devote a runtime directory to it:

    SBDIR=/usr/local/spambayes/core_server  # or whatever...
    mkdir -p $SBDIR

3. Create an INI file:

    cd $SBDIR
    cat > bayescustomize.ini <<EOF
[globals]
verbose:False

[Headers]
include_evidence:True
include_score:True

[Tokenizer]
record_header_absence:True
summarize_email_prefixes:True
summarize_email_suffixes:True
mine_received_headers:True
x-pick_apart_urls:True
x-fancy_url_recognition:False
x-lookup_ip:True
lookup_ip_cache:$SBDIR/dnscache.pck
max_image_size:100000
crack_image_cache:$SBDIR/imagecache.pck

crack_images:True
image_size:True
ocr_engine:gocr
[Classifier]
use_bigrams:False

[Categorization]
ham_cutoff:0.2
spam_cutoff:0.85

[Storage]
persistent_storage_file:$SBDIR/hammie.db
persistent_use_database:pickle
messageinfo_storage_file:$SBDIR/messageinfo.fs

[html_ui]
display_score:True
EOF

4. Finally, start it:

    BAYESCUSTOMIZE=$SBDIR/bayescustomize.ini core_server.py -m XMLRPCPlugin

Note that it creates both a web server (defaulting to localhost:8880) and an
XML-RPC server (defaulting to localhost:8001).


Procmail filtering
------------------

Many people on Unix-like systems have procmail available as an optional or
as the default local delivery agent.  Integrating SpamBayes checking with
Procmail is straightforward.

First, create a SpamBayes database, by running "sb_filter.py -n".  If
you have some mail around that you can use to train it, do you (see the
"command line training" section below).  Note that if you don't, all your
mail will start out as 'unsure'.

Now, create a .spambayesrc file.  There are lots of options you could have
in here, but for the moment, just have these:

    [Storage]
    persistent_use_database = True
    persistent_storage_file = ~/.hammiedb

(Replace the latter with the location of the .hammiedb file that
sb_filter.py created in the first step).

Once you've trained SpamBayes on your
collection of know ham and spam, you can use the sb_filter.py script to
classify incoming mail like so:

    :0 fw:hamlock
    | /usr/local/bin/sb_filter.py

The above Procmail recipe tells it to run /usr/local/bin/sb_filter.py.
Since no command line arguments are given, it relies on the options file
specified by the BAYESCUSTOMIZE variable for all parameters.  While
sb_filter.py is running, Procmail uses the lock file hamlock to prevent
multiple invocations from stepping on each others' toes.  (It's not strictly
necessary in this case since no files on-disk are modified, but Procmail
will still complain if you don't specify a lock file.)

The result of running sb_filter.py in filter mode is that Procmail will
use the output from the run as the mail message for further processing
downstream. sb_filter.py inserts an X-SpamBayes-Classification header in
the output message which looks like:

    X-SpamBayes-Classification: ham; 0.00; '*H*': 1.00; '*S*': 0.00; 'python': 0.00;
	'linux,': 0.01; 'desirable': 0.01; 'cvs,': 0.01; 'perl.': 0.02;
	...

You can then use this to segregate your messages into various inboxes, like
so:

    :0
    * ^X-SpamBayes-Classification: spam
    spam

    :0
    * ^X-SpamBayes-Classification: unsure
    unsure

The first recipe catches all messages which sb_filter.py classified as spam.
The second catches all messages about which it was unsure.  The combination
allows you to isolate spam from your good mail and tuck away messages it was
unsure about so you can scan them more closely.


VM and Gnus
-----------

VM and Gnus are mail readers distributed with Emacs and XEmacs.  The
SpamBayes.el file in the contrib directory contains code and
instructions for VM and Gnus integration.


Training
========

POP3 Proxy
----------

You can train the system through the web interface: <http://localhost:8880>.
Follow the "Review messages" link and you'll see a list of the emails that
the system has seen so far.  Check the appropriate boxes and hit Train.
The messages disappear and if you go back to the home page you'll see that
the "Total emails trained" has increased.

Alternatively, when you receive an incorrectly classified message, you can
forward it to the SMTP proxy for training.  If the message should have been
classified as spam, forward or bounce the message to
spambayes_spam@localhost, and if the message should have been classified as
ham, forward it to spambayes_ham@localhost.  You can still review the
training through the web interface, if you wish to do so.

Note that some mail clients (particularly Outlook Express) do not forward
all headers when you bounce, forward or redirect mail.  For these clients,
you will need to use the web interface to train.

Once you've done this on a few spams and a few hams, you'll find that the
X-Spambayes-Classification header is getting it right most of the time.
The more you train it the more accurate it gets.  There's no need to train
it on every message you receive, but you should train on a few spams and a
few hams on a regular basis.  You should also try to train it on about the
same number of spams as hams.

You can train it on lots of messages in one go by either using the
sb_filter.py script as explained in the "Command-line training" section,
or by giving messages to the web interface via the "Train" form on the
Home page. You can train on individual messages (which is tedious) or
using mbox files.


IMAP Filter
-----------

If you are running the IMAP filter with the '-t' switch, as described above,
then all you need to do to train is move examples of mail into the
appropriate folders, via your mail client (for example, move mail that was
not classified as spam into (one of) the folder(s) that you specified as
a spam training folder in the steps above.

Note that training, even without any classifying, using the IMAP filter,
means that your messages will be recreated (i.e. the old one is marked for
deletion and a new copy is made) on the server.  The messages will be
identical to the original, except that they will include an additional
header, so that SpamBayes can keep track of which messages have already
been processed.
                                           

Command-line training
---------------------

Given a pair of Unix mailbox format files (each message starts with a line
which begins with 'From '), one containing nothing but spam and the other
containing nothing but ham, you can train Spambayes using a command like

    sb_mboxtrain.py -g ~/tmp/newham -s ~/tmp/newspam

The above command is command-line-centric (eg. UNIX, or Windows command
prompt).  You can also use the web interface for training as detailed above.


Overview
========

[This section will tell you more about how and what SpamBayes is, but does
not contain any additional information about setting it up.]

There are eight main components to the SpamBayes system:

 o A database.  Loosely speaking, this is a collection of words and
   associated spam and ham probabilities.  The database says "If a message
   contains the word 'Viagra' then there's a 98% chance that it's spam, and
   a 2% chance that it's ham."  This database is created by training - you
   give it messages, tell it whether those messages are ham or spam, and it
   adjusts its probabilities accordingly.  How to train it is covered
   below.  By default it lives in a file called "hammie.db".

 o The tokenizer/classifier.  This is the core engine of the system.  The
   tokenizer splits emails into tokens (words, roughly speaking), and the
   classifier looks at those tokens to determine whether the message looks
   like spam or not.  You don't use the tokenizer/classifier directly -
   it powers the other parts of the system.

 o The POP3 proxy.  This sits between your email client (Eudora, Outlook
   Express, etc) and your incoming email server, and adds the
   classification header to emails as you download them.  A typical
   user's email setup looks like this:

       +-----------------+                              +-------------+
       | Outlook Express |      Internet or intranet    |             |
       |  (or similar)   | <--------------------------> | POP3 server |
       |                 |                              |             |
       +-----------------+                              +-------------+

   The POP3 server runs either at your ISP for Internet mail, or somewhere
   on your internal network for corporate mail.  The POP3 proxy sits in the
   middle and adds the classification header as you retrieve your email:

       +-----------------+        +------------+        +-------------+
       | Outlook Express |        | SpamBayes  |        |             |
       |  (or similar)   | <----> | POP3 proxy | <----> | POP3 server |
       |                 |        |            |        |             |
       +-----------------+        +------------+        +-------------+

   So where you currently have your email client configured to talk to
   say, "pop3.my-isp.com", you instead configure the *proxy* to talk to
   "pop3.my-isp.com" and configure your email client to talk to the proxy.
   The POP3 proxy can live on your PC, or on the same machine as the POP3
   server, or on a different machine entirely, it really doesn't matter.
   Say it's living on your PC, you'd configure your email client to talk
   to "localhost".  You can configure the proxy to talk to multiple POP3
   servers, if you have more than one email account.

 o The SMTP proxy.  This sits between your email client (Eudora, Outlook
   Express, etc) and your outgoing email server.  Any mail sent to
   SpamBayes_spam@localhost or SpamBayes_ham@localhost is intercepted
   and trained appropriately.  A typical user's email setup looks like
   this:

       +-----------------+                              +-------------+
       | Outlook Express |      Internet or intranet    |             |
       |  (or similar)   | <--------------------------> | SMTP server |
       |                 |                              |             |
       +-----------------+                              +-------------+

   The SMTP server runs either at your ISP for Internet mail, or somewhere
   on your internal network for corporate mail.  The SMTP proxy sits in the
   middle and checks for mail to train on as you send your email:

       +-----------------+        +------------+        +-------------+
       | Outlook Express |        | SpamBayes  |        |             |
       |  (or similar)   | <----> | SMTP proxy | <----> | SMTP server |
       |                 |        |            |        |             |
       +-----------------+        +------------+        +-------------+

   So where you currently have your email client configured to talk to
   say, "smtp.my-isp.com", you instead configure the *proxy* to talk to
   "smtp.my-isp.com" and configure your email client to talk to the proxy.
   The SMTP proxy can live on your PC, or on the same machine as the SMTP
   server, or on a different machine entirely, it really doesn't matter.
   Say it's living on your PC, you'd configure your email client to talk
   to "localhost".  You can configure the proxy to talk to multiple SMTP
   servers, if you have more than one email account.

 o The web interface.  This is a server that runs alongside the POP3 proxy,
   SMTP proxy, and IMAP filter (see below) and lets you control it through
   the web.  You can upload emails to it for training or classification,
   query the probabilities database ("How many of my emails really *do*
   contain the word Viagra"?), find particular messages, and most
   importantly, train it on the emails you've received.  When you start
   using the system, unless you train it using the sb_filter script it will
   classify most things as Unsure, and often make mistakes.  But it keeps
   copies of all the email's its seen, and through the web interface you
   can train it by going through a list of all the emails you've received
   and checking a Ham/Spam box next to each one.  After training on a few
   messages (say 20 spams and 20 hams), you'll find that it's getting it
   right most of the time.   The web training interface automatically
   checks the Ham/Spam boxes according to what it thinks, so all you need
   to do it correct the odd mistake - it's very quick and easy.

 o The Outlook plug-in.  For Outlook 2000 and Outlook XP users (not Outlook
   Express) this lets you manage the whole thing from within Outlook.  You
   set up a Ham folder and a Spam folder, and train it simply by dragging
   messages into those folders.  Alternatively there are buttons to do the
   same thing. And it integrates into Outlook's filtering system to make it
   easy to file all the suspected spam into its own folder, for instance.

 o The sb_filter.py script.  This does three jobs: command-line training,
   procmail filtering, and XML-RPC.  See below for details of how to use
   sb_filter for training, and how to use it as procmail filter. You  can
   also run an XML-RPC server, so that a programmer can write code that
   uses a remote server to classify emails programmatically - see
   sb_xmlrpcserver.py.

 o The IMAP filter.  This is a cross between the POP3 proxy and the Outlook
   plugin.  If your mail sits on an IMAP server, you can use the this to
   filter your mail.  You can designate folders that contain mail to train
   as ham and folders that contain mail to train as spam, and the filter
   does this for you.  You can also designate folders to filter, along with
   a folder for messages SpamBayes is unsure about, and a folder for
   suspected spam. When new mail arrives, the filter will move mail to the
   appropriate location (ham is left in the original folder).
