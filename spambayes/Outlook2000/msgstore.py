from __future__ import generators

import sys, os


# Abstract definition - can be moved out when we have more than one sub-class <wink>
# External interface to this module is almost exclusively via a "folder ID"

class MsgStoreException(Exception):
    pass

class NotFoundException(MsgStoreException):
    pass

class MsgStore:
    # Stash exceptions in the class for ease of use by consumers.
    MsgStoreException = MsgStoreException
    NotFoundException = NotFoundException
    def __init__(self):
        pass
    def Close(self):
        # Close this object and free everything
        raise NotImplementedError
    def GetFolderGenerator(self, folder_ids, include_sub):
        # Return a generator of MsgStoreFolder objects.
        raise NotImplementedError
    def GetFolder(self, folder_id):
        # Return a single folder given the ID.
        raise NotImplementedError
    def GetMessage(self, message_id):
        # Return a single message given the ID.
        raise NotImplementedError

class MsgStoreFolder:
    def __init__(self):
        self.name = "<folder>"
        self.count = 0
    def GetMessageGenerator(self, folder):
        # Return a generator of MsgStoreMsg objects for the folder
        raise NotImplementedError

class MsgStoreMsg:
    def __init__(self):
        self.unread = False
    def GetEmailPackageObject(self, strip_mime_headers=True):
        # Return a "read-only" Python email package object
        # "read-only" in that changes will never be reflected to the real store.
        raise NotImplementedError
    def SetField(self, name, value):
        # Abstractly set a user field name/id to a field value.
        # User field is for the user to see - status/internal fields
        # should get their own methods
        raise NotImplementedError
    def Save(self):
        # Save changes after field changes.
        raise NotImplementedError
    def MoveTo(self, folder_id):
        # Move the message to a folder.
        raise NotImplementedError
    def CopyTo(self, folder_id):
        # Copy the message to a folder.
        raise NotImplementedError
    # And some status ones we may hopefully use.
    def BeenFiltered(self):
        # Ever been filtered by us before
        raise NotImplementedError
    def GetTrainedCorpaName(self):
        # Return None, "ham" or "spam"
        raise NotImplementedError


# Our MAPI implementation
import warnings
if sys.version_info >= (2, 3):
    # sick off the new hex() warnings!
    warnings.filterwarnings("ignore", category=FutureWarning, append=1)

from win32com.client import Dispatch, constants
from win32com.mapi import mapi
from win32com.mapi.mapitags import *
import pythoncom

MESSAGE_MOVE = 0x1 # from MAPIdefs.h
MYPR_BODY_HTML_A = 0x1013001e # magic <wink>
MYPR_BODY_HTML_W = 0x1013001f # ditto

USE_DEFERRED_ERRORS = mapi.MAPI_DEFERRED_ERRORS # or set to zero to see what changes <wink>

class MAPIMsgStore(MsgStore):
    def __init__(self, outlook = None):
        self.outlook = outlook
        cwd = os.getcwd()
        mapi.MAPIInitialize(None)
        logonFlags = (mapi.MAPI_NO_MAIL |
                      mapi.MAPI_EXTENDED |
                      mapi.MAPI_USE_DEFAULT)
        self.session = mapi.MAPILogonEx(0, None, None, logonFlags)
        self._FindDefaultMessageStore()
        os.chdir(cwd)

    def Close(self):
        self.mapi_msgstore = None
        self.session.Logoff(0, 0, 0)
        self.session = None
        mapi.MAPIUninitialize()

    def _FindDefaultMessageStore(self):
        tab = self.session.GetMsgStoresTable(0)
        # Restriction for the table:  get rows where PR_DEFAULT_STORE is true.
        # There should be only one.
        restriction = (mapi.RES_PROPERTY,   # a property restriction
                       (mapi.RELOP_EQ,      # check for equality
                        PR_DEFAULT_STORE,   # of the PR_DEFAULT_STORE prop
                        (PR_DEFAULT_STORE, True))) # with True
        rows = mapi.HrQueryAllRows(tab,
                                   (PR_ENTRYID,),   # columns to retrieve
                                   restriction,     # only these rows
                                   None,            # any sort order is fine
                                   0)               # any # of results is fine
        # get first entry, a (property_tag, value) pair, for PR_ENTRYID
        row = rows[0]
        eid_tag, eid = row[0]
        # Open the store.
        self.mapi_msgstore = self.session.OpenMsgStore(
                                0,      # no parent window
                                eid,    # msg store to open
                                None,   # IID; accept default IMsgStore
                                # need write access to add score fields
                                mapi.MDB_WRITE |
                                    # we won't send or receive email
                                    mapi.MDB_NO_MAIL |
                                    USE_DEFERRED_ERRORS)

    def _GetSubFolderIter(self, folder):
        table = folder.GetHierarchyTable(0)
        rows = mapi.HrQueryAllRows(table,
                                   (PR_ENTRYID, PR_DISPLAY_NAME_A),
                                   None,
                                   None,
                                   0)
        for (eid_tag, eid),(name_tag, name) in rows:
            sub = self.mapi_msgstore.OpenEntry(eid,
                                               None,
                                               mapi.MAPI_MODIFY |
                                                   USE_DEFERRED_ERRORS)
            table = sub.GetContentsTable(0)
            yield MAPIMsgStoreFolder(self, eid, name, table.GetRowCount(0))
            folder = self.mapi_msgstore.OpenEntry(eid,
                                                  None,
                                                  mapi.MAPI_MODIFY |
                                                      USE_DEFERRED_ERRORS)
            for store_folder in self._GetSubFolderIter(folder):
                yield store_folder

    def GetFolderGenerator(self, folder_ids, include_sub):
        for folder_id in folder_ids:
            folder_id = mapi.BinFromHex(folder_id)
            folder = self.mapi_msgstore.OpenEntry(folder_id,
                                                  None,
                                                  mapi.MAPI_MODIFY |
                                                      USE_DEFERRED_ERRORS)
            table = folder.GetContentsTable(0)
            rc, props = folder.GetProps( (PR_DISPLAY_NAME_A,), 0)
            yield MAPIMsgStoreFolder(self, folder_id, props[0][1],
                                     table.GetRowCount(0))
            if include_sub:
                for f in self._GetSubFolderIter(folder):
                    yield f

    def GetFolder(self, folder_id):
        # Return a single folder given the ID.
        folder_id = mapi.BinFromHex(folder_id)
        folder = self.mapi_msgstore.OpenEntry(folder_id,
                                              None,
                                              mapi.MAPI_MODIFY |
                                                  USE_DEFERRED_ERRORS)
        table = folder.GetContentsTable(0)
        rc, props = folder.GetProps( (PR_DISPLAY_NAME_A,), 0)
        return MAPIMsgStoreFolder(self, folder_id, props[0][1],
                                  table.GetRowCount(0))

    def GetMessage(self, message_id):
        # Return a single message given the ID.
        message_id = mapi.BinFromHex(message_id)
        prop_ids = PR_PARENT_ENTRYID, PR_CONTENT_UNREAD
        mapi_object = self.mapi_msgstore.OpenEntry(message_id,
                                                   None,
                                                   mapi.MAPI_MODIFY |
                                                       USE_DEFERRED_ERRORS)
        hr, data = mapi_object.GetProps(prop_ids,0)
        folder_eid = data[0][1]
        unread = data[1][1]
        folder = MAPIMsgStoreFolder(self, folder_eid,
                                    "Unknown - temp message", -1)
        return  MAPIMsgStoreMsg(self, folder, message_id, unread)

##    # Currently no need for this
##    def GetOutlookObjectFromID(self, eid):
##        if self.outlook is None:
##            from win32com.client import Dispatch
##            self.outlook = Dispatch("Outlook.Application")
##        return self.outlook.Session.GetItemFromID(mapi.HexFromBin(eid))


_MapiTypeMap = {
    type(0.0): PT_DOUBLE,
    type(0): PT_I4,
    type(''): PT_STRING8,
    type(u''): PT_UNICODE,
    # In Python 2.2.2, bool isn't a distinct type (type(1==1) is type(0)).
#    type(1==1): PT_BOOLEAN,
}

class MAPIMsgStoreFolder(MsgStoreMsg):
    def __init__(self, msgstore, id, name, count):
        self.msgstore = msgstore
        self.id = id
        self.name = name
        self.count = count

    def __repr__(self):
        return "<%s '%s' (%d items), id=%s>" % (self.__class__.__name__,
                                                self.name,
                                                self.count,
                                                mapi.HexFromBin(self.id))

    def GetOutlookEntryID(self):
        return mapi.HexFromBin(self.id)

    def GetMessageGenerator(self):
        folder = self.msgstore.mapi_msgstore.OpenEntry(self.id,
                                                       None,
                                                       mapi.MAPI_MODIFY |
                                                           USE_DEFERRED_ERRORS)
        table = folder.GetContentsTable(0)
        prop_ids = PR_ENTRYID, PR_CONTENT_UNREAD
        table.SetColumns(prop_ids, 0)
        while 1:
            # Getting 70 at a time was the random number that gave best
            # perf for me ;)
            rows = table.QueryRows(70, 0)
            if len(rows) == 0:
                break
            for row in rows:
                yield MAPIMsgStoreMsg(self.msgstore, self,
                                      row[0][1], row[1][1])


class MAPIMsgStoreMsg(MsgStoreMsg):
    def __init__(self, msgstore, folder, entryid, unread):
        self.folder = folder
        self.msgstore = msgstore
        self.mapi_object = None
        self.id = entryid
        self.unread = unread
        self.dirty = False

    def __repr__(self):
        if self.unread:
            urs = "read"
        else:
            urs = "unread"
        return "<%s, (%s) id=%s>" % (self.__class__.__name__,
                                     urs,
                                     mapi.HexFromBin(self.id))

    def GetOutlookEntryID(self):
        return mapi.HexFromBin(self.id)

    def _GetPropFromStream(self, prop_id):
        try:
            stream = self.mapi_object.OpenProperty(prop_id,
                                                   pythoncom.IID_IStream,
                                                   0, 0)
            chunks = []
            while 1:
                chunk = stream.Read(1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return "".join(chunks)
        except pythoncom.com_error, d:
            print "Error getting property from stream", d
            return ""

    def _GetPotentiallyLargeStringProp(self, prop_id, row):
        got_tag, got_val = row
        if PROP_TYPE(got_tag) == PT_ERROR:
            ret = ""
            if got_val == mapi.MAPI_E_NOT_FOUND:
                pass # No body for this message.
            elif got_val == mapi.MAPI_E_NOT_ENOUGH_MEMORY:
                # Too big for simple properties - get via a stream
                ret = self._GetPropFromStream(prop_id)
            else:
                tag_name = mapiutil.GetPropTagName(prop_id)
                err_string = mapiutil.GetScodeString(got_val)
                print "Warning - failed to get property %s: %s" % (tag_name,
                                                                   err_string)
        else:
            ret = got_val
        return ret

    def _GetMessageText(self):
        # This is finally reliable.  The only messages this now fails for
        # are for "forwarded" messages, where the forwards are actually
        # in an attachment.  Later.

        # Note:  There's no distinction made here between msgs that have
        # been received, and, e.g., msgs that were sent and moved from the
        # Sent Items folder.  It would be good not to train on the latter,
        # since it's simply not received email.  An article on the web said
        # the distinction can't be made with 100% certainty, but that a good
        # heuristic is to believe that a msg has been received iff at least
        # one of these properties has a sensible value:
        #     PR_RECEIVED_BY_EMAIL_ADDRESS
        #     PR_RECEIVED_BY_NAME
        #     PR_RECEIVED_BY_ENTRYID
        #     PR_TRANSPORT_MESSAGE_HEADERS
        self._EnsureObject()
        prop_ids = PR_TRANSPORT_MESSAGE_HEADERS_A, PR_BODY_A, MYPR_BODY_HTML_A
        hr, data = self.mapi_object.GetProps(prop_ids,0)
        headers = self._GetPotentiallyLargeStringProp(prop_ids[0], data[0])
        body = self._GetPotentiallyLargeStringProp(prop_ids[1], data[1])
        html = self._GetPotentiallyLargeStringProp(prop_ids[2], data[2])
        return "%s\n%s\n%s" % (headers, html, body)

    def _EnsureObject(self):
        if self.mapi_object is None:
            self.mapi_object = self.msgstore.mapi_msgstore.OpenEntry(
                                   self.id,
                                   None,
                                   mapi.MAPI_MODIFY | USE_DEFERRED_ERRORS)

    def GetEmailPackageObject(self, strip_mime_headers=True):
        import email
        # XXX If this was originally a MIME msg, we're hosed at this point --
        # the boundary tag in the headers doesn't exist in the body, and
        # the msg is simply ill-formed.  The miserable hack here simply
        # squashes the text part (if any) and the HTML part (if any) together,
        # and strips MIME info from the original headers.
        text = self._GetMessageText()
        try:
            msg = email.message_from_string(text)
        except:
            print "FAILED to create email.message from: ", `text`
            raise

        if strip_mime_headers:
            # If we're going to pass this to a scoring function, the MIME
            # headers must be stripped, else the email pkg will run off
            # looking for MIME boundaries that don't exist.  The charset
            # info from the original MIME armor is also lost, and we don't
            # want the email pkg to try decoding the msg a second time
            # (assuming Outlook is in fact already decoding text originally
            # in base64 and quoted-printable).
            # We want to retain the MIME headers if we're just displaying
            # the msg stream.
            if msg.has_key('content-type'):
                del msg['content-type']
            if msg.has_key('content-transfer-encoding'):
                del msg['content-transfer-encoding']
        return msg

    def SetField(self, prop, val):
        # XXX If the SpamProb (Hammie, whatever) property is passed in as an
        # XXX int, Outlook displays the field as all blanks, and sorting on
        # XXX it doesn't do anything, etc.  I don't know why.  Since I'm
        # XXX running Python 2.2.2, the _MapiTypeMap above confuses ints
        # XXX with bools, but the problem persists even if I comment out the
        # XXX PT_BOOLEAN entry from that dict.  Dumping in prints below show
        # XXX that type_tag is 3 then, and that matches the defn of PT_I4 in
        # XXX my system header files.
        # XXX Later:  This works after all, but the field shows up as all
        # XXX blanks unless I *first* modify the view (like Messages) in
        # XXX Outlook to define a custom Integer field of the same name.
        self._EnsureObject()
        if type(prop) != type(0):
            props = ( (mapi.PS_PUBLIC_STRINGS, prop), )
            propIds = self.mapi_object.GetIDsFromNames(props, mapi.MAPI_CREATE)
            type_tag = _MapiTypeMap.get(type(val))
            if type_tag is None:
                raise ValueError, "Don't know what to do with '%r' ('%s')" % (
                                     val, type(val))
            prop = PROP_TAG(type_tag, PROP_ID(propIds[0]))
        if val is None:
            # Delete the property
            self.mapi_object.DeleteProps((prop,))
        else:
            self.mapi_object.SetProps(((prop,val),))
        self.dirty = True

    def Save(self):
        assert self.dirty, "asking me to save a clean message!"
        self.mapi_object.SaveChanges(mapi.KEEP_OPEN_READWRITE)
        self.dirty = False

    def _DoCopyMode(self, folder, isMove):
##        self.mapi_object = None # release the COM pointer
        assert not self.dirty, \
               "asking me to move a dirty message - later saves will fail!"
        dest_folder = self.msgstore.mapi_msgstore.OpenEntry(
                          folder.id,
                          None,
                          mapi.MAPI_MODIFY | USE_DEFERRED_ERRORS)
        source_folder = self.msgstore.mapi_msgstore.OpenEntry(
                            self.folder.id,
                            None,
                            mapi.MAPI_MODIFY | USE_DEFERRED_ERRORS)
        flags = 0
        if isMove: flags |= MESSAGE_MOVE
        source_folder.CopyMessages((self.id,),
                                   None,
                                   dest_folder,
                                   0,
                                   None,
                                   flags)
        self.folder = self.msgstore.GetFolder(mapi.HexFromBin(folder.id))

    def MoveTo(self, folder):
        self._DoCopyMode(folder, True)

    def CopyTo(self, folder):
        self._DoCopyMode(folder, True)

def test():
    from win32com.client import Dispatch
    outlook = Dispatch("Outlook.Application")
    eid = outlook.Session.GetDefaultFolder(constants.olFolderInbox).EntryID

    store = MAPIMsgStore()
    for folder in store.GetFolderGenerator([eid,], True):
        print folder
        for msg in folder.GetMessageGenerator():
            print msg
    store.Close()


if __name__=='__main__':
    test()
