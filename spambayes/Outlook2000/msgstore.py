from __future__ import generators

import sys, os

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


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
    def GetField(self, name):
        # Abstractly get a user field name/id to a field value.
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

# Our MAPI implementation
import warnings
if sys.version_info >= (2, 3):
    # sick off the new hex() warnings!
    warnings.filterwarnings("ignore", category=FutureWarning, append=1)

from win32com.client import Dispatch, constants
from win32com.mapi import mapi, mapiutil
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
        self.mapi_msg_stores = {}
        self.default_store_bin_eid = None
        self._GetMessageStore(None)
        os.chdir(cwd)

    def Close(self):
        self.mapi_msg_stores = None
        self.session.Logoff(0, 0, 0)
        self.session = None
        mapi.MAPIUninitialize()

    def _GetMessageStore(self, store_eid): # bin eid.
        try:
            # Will usually be pre-fetched, so fast-path out
            return self.mapi_msg_stores[store_eid]
        except KeyError:
            pass
        given_store_eid = store_eid
        if store_eid is None:
            # Find the EID for the default store.
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
            eid_tag, store_eid = row[0]
            self.default_store_bin_eid = store_eid

        # Open it.
        store = self.session.OpenMsgStore(
                                0,      # no parent window
                                store_eid,    # msg store to open
                                None,   # IID; accept default IMsgStore
                                # need write access to add score fields
                                mapi.MDB_WRITE |
                                    # we won't send or receive email
                                    mapi.MDB_NO_MAIL |
                                    USE_DEFERRED_ERRORS)
        # cache it
        self.mapi_msg_stores[store_eid] = store
        if given_store_eid is None: # The default store
            self.mapi_msg_stores[None] = store
        return store

    def _OpenEntry(self, id, iid = None, flags = None):
        # id is already normalized.
        store_id, item_id = id
        store = self._GetMessageStore(store_id)
        if flags is None:
            flags = mapi.MAPI_MODIFY | USE_DEFERRED_ERRORS
        return store.OpenEntry(item_id, iid, flags)

    # Given an ID, normalize it into a (store_id, item_id) binary tuple.
    # item_id may be:
    # - Simple hex EID, in wich case default store ID is assumed.
    # - Tuple of (None, hex_eid), in which case default store assumed.
    # - Tuple of (hex_store_id, hex_id)
    def NormalizeID(self, item_id):
        if type(item_id)==type(()):
            store_id, item_id = item_id
            item_id = mapi.BinFromHex(item_id)
            if store_id is None:
                store_id = self.default_store_bin_eid
            else:
                store_id = mapi.BinFromHex(store_id)
            return store_id, item_id
        assert type(item_id) in [type(''), type(u'')], "What kind of ID is '%r'?" % (item_id,)
        return self.default_store_bin_eid, mapi.BinFromHex(item_id)

    def _GetSubFolderIter(self, folder):
        table = folder.GetHierarchyTable(0)
        rows = mapi.HrQueryAllRows(table,
                                   (PR_ENTRYID, PR_STORE_ENTRYID, PR_DISPLAY_NAME_A),
                                   None,
                                   None,
                                   0)
        for (eid_tag, eid), (store_eid_tag, store_eid), (name_tag, name) in rows:
            item_id = store_eid, eid
            sub = self._OpenEntry(item_id)
            table = sub.GetContentsTable(0)
            yield MAPIMsgStoreFolder(self, item_id, name, table.GetRowCount(0))
            for store_folder in self._GetSubFolderIter(sub):
                yield store_folder

    def GetFolderGenerator(self, folder_ids, include_sub):
        for folder_id in folder_ids:
            folder_id = self.NormalizeID(folder_id)
            folder = self._OpenEntry(folder_id)
            table = folder.GetContentsTable(0)
            rc, props = folder.GetProps( (PR_DISPLAY_NAME_A,), 0)
            yield MAPIMsgStoreFolder(self, folder_id, props[0][1],
                                     table.GetRowCount(0))
            if include_sub:
                for f in self._GetSubFolderIter(folder):
                    yield f

    def GetFolder(self, folder_id):
        # Return a single folder given the ID.
        if hasattr(folder_id, "EntryID"):
            # An Outlook object
            folder_id = mapi.BinFromHex(folder_id.StoreID), \
                         mapi.BinFromHex(folder_id.EntryID)
        else:
            folder_id = self.NormalizeID(folder_id)
        folder = self._OpenEntry(folder_id)
        table = folder.GetContentsTable(0)
        rc, props = folder.GetProps( (PR_DISPLAY_NAME_A,), 0)
        return MAPIMsgStoreFolder(self, folder_id, props[0][1],
                                  table.GetRowCount(0))

    def GetMessage(self, message_id):
        # Return a single message given either the ID, or an Outlook
        # message representing the object.
        if hasattr(message_id, "EntryID"):
            # An Outlook object
            message_id = mapi.BinFromHex(message_id.Parent.StoreID), \
                         mapi.BinFromHex(message_id.EntryID)
        else:
            message_id = self.NormalizeID(message_id)
        prop_ids = PR_PARENT_ENTRYID, PR_SEARCH_KEY, PR_CONTENT_UNREAD
        mapi_object = self._OpenEntry(message_id)
        hr, data = mapi_object.GetProps(prop_ids,0)
        folder_eid = data[0][1]
        searchkey = data[1][1]
        unread = data[2][1]
        folder_id = message_id[0], folder_eid
        folder = MAPIMsgStoreFolder(self, folder_id,
                                    "Unknown - temp message", -1)
        return  MAPIMsgStoreMsg(self, folder, message_id, searchkey, unread)

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
        return "<%s '%s' (%d items), id=%s/%s>" % (self.__class__.__name__,
                                                self.name,
                                                self.count,
                                                mapi.HexFromBin(self.id[0]),
                                                mapi.HexFromBin(self.id[1]))

    def __eq__(self, other):
        if other is None: return False
        ceid = self.msgstore.session.CompareEntryIDs
        return ceid(self.id[0], other.id[0]) and \
               ceid(self.id[1], other.id[1])

    def __ne__(self, other):
        return not self.__eq__(other)

    def GetID(self):
        return mapi.HexFromBin(self.id[0]), mapi.HexFromBin(self.id[1])

    def GetOutlookItem(self):
        hex_item_id = mapi.HexFromBin(self.id[1])
        hex_store_id = mapi.HexFromBin(self.id[0])
        return self.msgstore.outlook.Session.GetFolderFromID(hex_item_id, hex_store_id)

    def GetMessageGenerator(self):
        folder = self.msgstore._OpenEntry(self.id)
        table = folder.GetContentsTable(0)
        prop_ids = PR_ENTRYID, PR_SEARCH_KEY, PR_CONTENT_UNREAD
        table.SetColumns(prop_ids, 0)
        while 1:
            # Getting 70 at a time was the random number that gave best
            # perf for me ;)
            rows = table.QueryRows(70, 0)
            if len(rows) == 0:
                break
            for row in rows:
                item_id = self.id[0], row[0][1] # assume in same store as folder!
                yield MAPIMsgStoreMsg(self.msgstore, self,
                                      item_id, row[1][1], row[2][1])


class MAPIMsgStoreMsg(MsgStoreMsg):
    def __init__(self, msgstore, folder, entryid, searchkey, unread):
        self.folder = folder
        self.msgstore = msgstore
        self.mapi_object = None
        self.id = entryid
        # Search key is the only reliable thing after a move/copy operation
        # only problem is that it can potentially be changed - however, the
        # Outlook client provides no such (easy/obvious) way
        # (ie, someone would need to really want to change it <wink>)
        # Thus, searchkey is the only reliable long-lived message key.
        self.searchkey = searchkey
        self.unread = unread
        self.dirty = False

    def __repr__(self):
        if self.unread:
            urs = "read"
        else:
            urs = "unread"
        return "<%s, (%s) id=%s/%s>" % (self.__class__.__name__,
                                     urs,
                                     mapi.HexFromBin(self.id[0]),
                                     mapi.HexFromBin(self.id[1]))

    def __eq__(self, other):
        if other is None: return False
        ceid = self.msgstore.session.CompareEntryIDs
        return ceid(self.id[0], other.id[0]) and \
               ceid(self.id[1], other.id[1])

    def __ne__(self, other):
        return not self.__eq__(other)

    def GetID(self):
        return mapi.HexFromBin(self.id[0]), mapi.HexFromBin(self.id[1])

    def GetOutlookItem(self):
        hex_item_id = mapi.HexFromBin(self.id[1])
        hex_store_id = mapi.HexFromBin(self.id[0])
        return self.msgstore.outlook.Session.GetItemFromID(hex_item_id, hex_store_id)

    def _GetPropFromStream(self, prop_id):
        try:
            stream = self.mapi_object.OpenProperty(prop_id,
                                                   pythoncom.IID_IStream,
                                                   0, 0)
            chunks = []
            while 1:
                chunk = stream.Read(4096)
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
        # Oh - and for multipart/signed messages <frown>
        self._EnsureObject()
        prop_ids = (PR_TRANSPORT_MESSAGE_HEADERS_A,
                    PR_BODY_A,
                    MYPR_BODY_HTML_A,
                    PR_HASATTACH)
        hr, data = self.mapi_object.GetProps(prop_ids,0)
        headers = self._GetPotentiallyLargeStringProp(prop_ids[0], data[0])
        body = self._GetPotentiallyLargeStringProp(prop_ids[1], data[1])
        html = self._GetPotentiallyLargeStringProp(prop_ids[2], data[2])
        has_attach = data[3][1]
        # Mail delivered internally via Exchange Server etc may not have
        # headers - fake some up.
        if not headers:
            headers = self._GetFakeHeaders ()
        # Mail delivered via the Exchange Internet Mail MTA may have
        # gibberish at the start of the headers - fix this.
        elif headers.startswith("Microsoft Mail"):
            headers = "X-MS-Mail-Gibberish: " + headers
        if not html and not body:
            # Only ever seen this for "multipart/signed" messages, so
            # without any better clues, just handle this.
            # Find all attachments with PR_ATTACH_MIME_TAG_A=multipart/signed
            pass

        return "%s\n%s\n%s" % (headers, html, body)

    def _GetFakeHeaders(self):
        # This is designed to fake up some SMTP headers for messages
        # on an exchange server that do not have such headers of their own
        prop_ids = PR_SUBJECT_A, PR_DISPLAY_NAME_A, PR_DISPLAY_TO_A, PR_DISPLAY_CC_A
        hr, data = self.mapi_object.GetProps(prop_ids,0)
        subject = self._GetPotentiallyLargeStringProp(prop_ids[0], data[0])
        sender = self._GetPotentiallyLargeStringProp(prop_ids[1], data[1])
        to = self._GetPotentiallyLargeStringProp(prop_ids[2], data[2])
        cc = self._GetPotentiallyLargeStringProp(prop_ids[3], data[3])
        headers = ["X-Exchange-Message: true"]
        if subject: headers.append("Subject: "+subject)
        if sender: headers.append("From: "+sender)
        if to: headers.append("To: "+to)
        if cc: headers.append("CC: "+cc)
        return "\n".join(headers) + "\n"

    def _EnsureObject(self):
        if self.mapi_object is None:
            self.mapi_object = self.msgstore._OpenEntry(self.id)

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
        # Future optimization note - from GetIDsFromNames doco
        # Name-to-identifier mapping is represented by an object's
        # PR_MAPPING_SIGNATURE property. PR_MAPPING_SIGNATURE contains
        # a MAPIUID structure that indicates the service provider
        # responsible for the object. If the PR_MAPPING_SIGNATURE
        # property is the same for two objects, assume that these
        # objects use the same name-to-identifier mapping.
        # [MarkH: Note MAPIUUID object are supported and hashable]

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

    def GetField(self, prop):
        self._EnsureObject()
        if type(prop) != type(0):
            props = ( (mapi.PS_PUBLIC_STRINGS, prop), )
            prop = self.mapi_object.GetIDsFromNames(props, 0)[0]
            if PROP_TYPE(prop) == PT_ERROR: # No such property
                return None
            prop = PROP_TAG( PT_UNSPECIFIED, PROP_ID(prop))
        hr, props = self.mapi_object.GetProps((prop,), 0)
        ((tag, val), ) = props
        if PROP_TYPE(tag) == PT_ERROR:
            if val == mapi.MAPI_E_NOT_ENOUGH_MEMORY:
                # Too big for simple properties - get via a stream
                return self._GetPropFromStream(prop)
            return None
        return val

    def Save(self):
        assert self.dirty, "asking me to save a clean message!"
        self.mapi_object.SaveChanges(mapi.KEEP_OPEN_READWRITE | USE_DEFERRED_ERRORS)
        self.dirty = False

    def _DoCopyMove(self, folder, isMove):
##        self.mapi_object = None # release the COM pointer
        assert not self.dirty, \
               "asking me to move a dirty message - later saves will fail!"
        dest_folder = self.msgstore._OpenEntry(folder.id)
        source_folder = self.msgstore._OpenEntry(self.folder.id)
        flags = 0
        if isMove: flags |= MESSAGE_MOVE
        eid = self.id[1]
        source_folder.CopyMessages((eid,),
                                   None,
                                   dest_folder,
                                   0,
                                   None,
                                   flags)
        # At this stage, I think we have lost meaningful ID etc values
        # Set everything to None to make it clearer what is wrong should
        # this become an issue.  We would need to re-fetch the eid of
        # the item, and set the store_id to the dest folder.
        self.id = None
        self.folder = None

    def MoveTo(self, folder):
        self._DoCopyMove(folder, True)

    def CopyTo(self, folder):
        self._DoCopyMove(folder, False)

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
