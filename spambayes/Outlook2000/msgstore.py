from __future__ import generators

import sys, os, re
import locale

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0

# Nod to our automated test suite - we *do* want these messages filtered!
test_suite_running = False

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
    def GetParent(self):
        # return a folder object with the parent, or None
        raise NotImplementedError
    def GetMessageGenerator(self, folder, only_filter_candidates = True):
        # Return a generator of MsgStoreMsg objects for the folder
        raise NotImplementedError

class MsgStoreMsg:
    def __init__(self):
        pass
    def GetEmailPackageObject(self):
        # Return a "read-only" Python email package object
        # "read-only" in that changes will never be reflected to the real store.
        raise NotImplementedError
    def SetField(self, name, value):
        # Abstractly set a user field name/id to a field value.
        # User field is for the user to see - status/internal fields
        # should get their own methods
        raise NotImplementedError
    def GetSubject(self):
        # Get the subject - function as it may require a trip to the store!
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
    def IsFilterCandidate(self):
        # Return True if this is a message that should be checked for spam
        # Return False if it should be ignored (eg, user-composed message,
        # undeliverable report, meeting request etc.
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
MSGFLAG_READ = 0x1 # from MAPIdefs.h
MSGFLAG_UNSENT = 0x00000008

MYPR_BODY_HTML_A = 0x1013001e # magic <wink>
MYPR_BODY_HTML_W = 0x1013001f # ditto

CLEAR_READ_FLAG = 0x00000004
CLEAR_RN_PENDING = 0x00000020
CLEAR_NRN_PENDING = 0x00000040
SUPPRESS_RECEIPT = 0x1

USE_DEFERRED_ERRORS = mapi.MAPI_DEFERRED_ERRORS # or set to zero to see what changes <wink>

# Does this exception probably mean "object not found"?
def IsNotFoundCOMException(exc_val):
    hr, msg, exc, arg_err = exc_val
    return hr in [mapi.MAPI_E_OBJECT_DELETED, mapi.MAPI_E_NOT_FOUND]

# Does this exception probably mean "object not available 'cos you ain't logged
# in, or 'cos the server is down"?
def IsNotAvailableCOMException(exc_val):
    hr, msg, exc, arg_err = exc_val
    return hr == mapi.MAPI_E_FAILONEPROVIDER

def GetCOMExceptionString(exc_val):
    hr, msg, exc, arg_err = exc_val
    err_string = mapiutil.GetScodeString(hr)
    return "Exception 0x%x (%s): %s" % (hr, err_string, msg)

class MAPIMsgStore(MsgStore):
    def __init__(self, outlook = None):
        self.outlook = outlook
        cwd = os.getcwd() # remember the cwd - mapi changes it under us!
        mapi.MAPIInitialize(None)
        logonFlags = (mapi.MAPI_NO_MAIL |
                      mapi.MAPI_EXTENDED |
                      mapi.MAPI_USE_DEFAULT)
        self.session = mapi.MAPILogonEx(0, None, None, logonFlags)
        # Note that if the CRT still has a default "C" locale, MAPILogonEx()
        # will change it.  See locale comments in addin.py
        locale.setlocale(locale.LC_NUMERIC, "C")
        self.mapi_msg_stores = {}
        self.default_store_bin_eid = None
        self._GetMessageStore(None)
        os.chdir(cwd)

    def Close(self):
        self.mapi_msg_stores = None
        self.session.Logoff(0, 0, 0)
        self.session = None
        mapi.MAPIUninitialize()

    def GetProfileName(self):
        # Return the name of the MAPI profile currently in use.
        # XXX - note - early win32all versions are missing
        # GetStatusTable :(
        try:
            self.session.GetStatusTable
        except AttributeError:
            # We try and recover from this when win32all is updated, so no need to whinge.
            return None

        MAPI_SUBSYSTEM = 39
        restriction = mapi.RES_PROPERTY, (mapi.RELOP_EQ, PR_RESOURCE_TYPE,
                                          (PR_RESOURCE_TYPE, MAPI_SUBSYSTEM))
        table = self.session.GetStatusTable(0)
        rows = mapi.HrQueryAllRows(table,
                                    (PR_DISPLAY_NAME_A,),   # columns to retrieve
                                    restriction,     # only these rows
                                    None,            # any sort order is fine
                                    0)               # any # of results is fine
        assert len(rows)==1, "Should be exactly one row"
        (tag, val), = rows[0]
        return val

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

    # Normalize an "external" hex ID to an internal binary ID.
    def NormalizeID(self, item_id):
        assert type(item_id)==type(()), \
               "Item IDs must be a tuple (not a %r)" % item_id
        store_id, entry_id = item_id
        return mapi.BinFromHex(store_id), mapi.BinFromHex(entry_id)

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
            try:
                folder = self._OpenEntry(folder_id)
                table = folder.GetContentsTable(0)
            except pythoncom.com_error, details:
                # We will ignore *all* such errors for the time
                # being, but give verbose details for results we don't
                # know about
                if IsNotAvailableCOMException(details):
                    print "NOTE: Skipping folder for this session - temporarily unavailable"
                elif IsNotFoundCOMException(details):
                    print "NOTE: Skipping deleted folder"
                else:
                    print "WARNING: Unexpected MAPI error opening folder"
                    print GetCOMExceptionString(details)
                continue
            rc, props = folder.GetProps( (PR_DISPLAY_NAME_A,), 0)
            yield MAPIMsgStoreFolder(self, folder_id, props[0][1],
                                     table.GetRowCount(0))
            if include_sub:
                for f in self._GetSubFolderIter(folder):
                    yield f

    def GetFolder(self, folder_id):
        # Return a single folder given the ID.
        try:
            # See if this is an Outlook folder item
            sid = mapi.BinFromHex(folder_id.StoreID)
            eid = mapi.BinFromHex(folder_id.EntryID)
            folder_id = sid, eid
        except AttributeError:
            # No 'EntryID'/'StoreID' properties - a 'normal' ID
            folder_id = self.NormalizeID(folder_id)
        except pythoncom.com_error, details:
            if IsNotFoundCOMException(details):
                print "Unable to open folder '%r'" \
                      "- the folder was not found" % folder_id
            else:
                print "Unexpected MAPI error opening folder"
                print GetCOMExceptionString(details)
            return None
        # Also catch COM exceptions opening the folder and table.
        try:
            folder = self._OpenEntry(folder_id)
            table = folder.GetContentsTable(0)
        except pythoncom.com_error, details:
            # We will ignore *all* such errors for the time
            # being, but warn for results we don't know about.
            if not IsNotFoundCOMException(details):
                print "WARNING: Unexpected MAPI error opening folder"
                print GetCOMExceptionString(details)
            return None
        # Ensure we have a long-term ID.
        rc, props = folder.GetProps( (PR_ENTRYID, PR_DISPLAY_NAME_A), 0)
        folder_id = folder_id[0], props[0][1]
        return MAPIMsgStoreFolder(self, folder_id, props[1][1],
                                  table.GetRowCount(0))

    def GetMessage(self, message_id):
        # Return a single message given either the ID, or an Outlook
        # message representing the object.
        try:
            eid = mapi.BinFromHex(message_id.EntryID)
            sid = mapi.BinFromHex(message_id.Parent.StoreID)
            message_id = sid, eid
        except AttributeError:
            # No 'EntryID'/'StoreID' properties - a 'normal' ID
            message_id = self.NormalizeID(message_id)
        except pythoncom.com_error, details:
            if IsNotFoundCOMException(details):
                print "Unable to open message '%r'" \
                      "- the message was not found" % message_id
            else:
                print "Unexpected MAPI error opening message"
                print GetCOMExceptionString(details)
            return None
        mapi_object = self._OpenEntry(message_id)
        hr, data = mapi_object.GetProps(MAPIMsgStoreMsg.message_init_props,0)
        return MAPIMsgStoreMsg(self, data)

_MapiTypeMap = {
    type(0.0): PT_DOUBLE,
    type(0): PT_I4,
    type(''): PT_STRING8,
    type(u''): PT_UNICODE,
    # In Python 2.2.2, bool isn't a distinct type (type(1==1) is type(0)).
#    type(1==1): PT_BOOLEAN,
}

def GetPropFromStream(mapi_object, prop_id):
    try:
        stream = mapi_object.OpenProperty(prop_id,
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

def GetPotentiallyLargeStringProp(mapi_object, prop_id, row):
    got_tag, got_val = row
    if PROP_TYPE(got_tag) == PT_ERROR:
        ret = ""
        if got_val == mapi.MAPI_E_NOT_FOUND:
            pass # No property for this message.
        elif got_val == mapi.MAPI_E_NOT_ENOUGH_MEMORY:
            # Too big for simple properties - get via a stream
            ret = GetPropFromStream(mapi_object, prop_id)
        else:
            tag_name = mapiutil.GetPropTagName(prop_id)
            err_string = mapiutil.GetScodeString(got_val)
            print "Warning - failed to get property %s: %s" % (tag_name,
                                                                err_string)
    else:
        ret = got_val
    return ret

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

    def GetParent(self):
        # return a folder object with the parent, or None
        folder = self.msgstore._OpenEntry(self.id)
        prop_ids = PR_PARENT_ENTRYID,
        hr, data = folder.GetProps(prop_ids,0)
        # Put parent ids together
        parent_eid = data[0][1]
        parent_id = self.id[0], parent_eid
        if hr != 0 or \
           self.msgstore.session.CompareEntryIDs(parent_eid, self.id[1]):
            # No parent EID, or EID same as ours.
            return None
        parent = self.msgstore._OpenEntry(parent_id)
        # Finally get the display name.
        hr, data = folder.GetProps((PR_DISPLAY_NAME_A,), 0)
        name = data[0][1]
        count = parent.GetContentsTable(0).GetRowCount(0)
        return MAPIMsgStoreFolder(self.msgstore, parent_id, name, count)

    def OpenEntry(self, iid = None, flags = None):
        return self.msgstore._OpenEntry(self.id, iid, flags)

    def GetOutlookItem(self):
        hex_item_id = mapi.HexFromBin(self.id[1])
        hex_store_id = mapi.HexFromBin(self.id[0])
        return self.msgstore.outlook.Session.GetFolderFromID(hex_item_id, hex_store_id)

    def GetMessageGenerator(self, only_filter_candidates = True):
        folder = self.OpenEntry()
        table = folder.GetContentsTable(0)
        if only_filter_candidates:
            # Limit ourselves to IPM.Note objects - ie, messages.
            restriction = (mapi.RES_PROPERTY,   # a property restriction
                           (mapi.RELOP_GE,      # >=
                            PR_MESSAGE_CLASS_A,   # of the this prop
                            (PR_MESSAGE_CLASS_A, "IPM.Note"))) # with this value
            table.Restrict(restriction, 0)
        table.SetColumns(MAPIMsgStoreMsg.message_init_props, 0)
        while 1:
            # Getting 70 at a time was the random number that gave best
            # perf for me ;)
            rows = table.QueryRows(70, 0)
            if len(rows) == 0:
                break
            for row in rows:
                # Our restriction helped, but may not have filtered
                # every message we don't want to touch.
                msg = MAPIMsgStoreMsg(self.msgstore, row)
                if not only_filter_candidates or msg.IsFilterCandidate():
                    yield msg

    def GetNewUnscoredMessageGenerator(self, scoreFieldName):
        folder = self.msgstore._OpenEntry(self.id)
        table = folder.GetContentsTable(0)
        # Resolve the field name
        resolve_props = ( (mapi.PS_PUBLIC_STRINGS, scoreFieldName), )
        resolve_ids = folder.GetIDsFromNames(resolve_props, 0)
        field_id = PROP_TAG( PT_DOUBLE, PROP_ID(resolve_ids[0]))
        # Setup the properties we want to read.
        table.SetColumns(MAPIMsgStoreMsg.message_init_props, 0)
        # Set up the restriction
        # Need to check message-flags
        # (PR_CONTENT_UNREAD is optional, and somewhat unreliable
        # PR_MESSAGE_FLAGS & MSGFLAG_READ is the official way)
        prop_restriction = (mapi.RES_BITMASK,   # a bitmask restriction
                               (mapi.BMR_EQZ,      # when bit is clear
                                PR_MESSAGE_FLAGS,
                                MSGFLAG_READ))
        exist_restriction = mapi.RES_EXIST, (field_id,)
        not_exist_restriction = mapi.RES_NOT, (exist_restriction,)
        # A restriction for the message class
        class_restriction = (mapi.RES_PROPERTY,   # a property restriction
                             (mapi.RELOP_GE,      # >=
                              PR_MESSAGE_CLASS_A,   # of the this prop
                              (PR_MESSAGE_CLASS_A, "IPM.Note"))) # with this value
        # Put the final restriction together
        restriction = (mapi.RES_AND, (prop_restriction,
                                      not_exist_restriction,
                                      class_restriction))
        table.Restrict(restriction, 0)
        while 1:
            rows = table.QueryRows(70, 0)
            if len(rows) == 0:
                break
            for row in rows:
                msg = MAPIMsgStoreMsg(self.msgstore, row)
                if msg.IsFilterCandidate():
                    yield msg

    def IsReceiveFolder(self, msg_class = "IPM.Note"):
        # Is this folder the nominated "receive folder" for its store?
        mapi_store = self.msgstore._GetMessageStore(self.id[0])
        eid, ret_class = mapi_store.GetReceiveFolder(msg_class, 0)
        return mapi_store.CompareEntryIDs(eid, self.id[1])

class MAPIMsgStoreMsg(MsgStoreMsg):
    # All the properties we must initialize a message with.
    # These include all the IDs we need, parent IDs, any properties needed
    # to determine if this is a "filterable" message, etc
    message_init_props = (PR_ENTRYID, PR_STORE_ENTRYID, PR_SEARCH_KEY,
                          PR_PARENT_ENTRYID, # folder ID
                          PR_MESSAGE_CLASS_A, # 'IPM.Note' etc
                          PR_RECEIVED_BY_ENTRYID, # who received it
                          ) 

    def __init__(self, msgstore, prop_row):
        self.msgstore = msgstore
        self.mapi_object = None

        # prop_row is a single mapi property row, with fields as above.
        tag, eid = prop_row[0] # ID
        tag, store_eid = prop_row[1]
        tag, searchkey = prop_row[2]
        tag, parent_eid = prop_row[3]
        tag, msgclass = prop_row[4]
        recby_tag, recby = prop_row[5]

        self.id = store_eid, eid
        self.folder_id = store_eid, parent_eid
        self.msgclass = msgclass
        self.subject = None
        # Search key is the only reliable thing after a move/copy operation
        # only problem is that it can potentially be changed - however, the
        # Outlook client provides no such (easy/obvious) way
        # (ie, someone would need to really want to change it <wink>)
        # Thus, searchkey is our long-lived message key.
        self.searchkey = searchkey
        # To check if a message has ever been received, we check the
        # PR_RECEIVED_BY_ENTRYID flag.  Tim wrote in an old comment that
        # An article on the web said the distinction can't be made with 100%
        # certainty, but that a good heuristic is to believe that a
        # msg has been received iff at least one of these properties
        # has a sensible value: RECEIVED_BY_EMAIL_ADDRESS, RECEIVED_BY_NAME,
        # RECEIVED_BY_ENTRYID PR_TRANSPORT_MESSAGE_HEADERS
        # But MarkH can't find it, and believes and tests that
        # PR_RECEIVED_BY_ENTRYID is all we need.
        # This also means we don't need to check the 'unsent' flag - unsent
        # messages never have the PR_RECEIVED_ properties either.
        self.was_received = PROP_TYPE(recby_tag) == PT_BINARY
        self.dirty = False

    def __repr__(self):
        if self.id is None:
            id_str = "(deleted/moved)"
        else:
            id_str = mapi.HexFromBin(self.id[0]), mapi.HexFromBin(self.id[1])
        return "<%s, '%s' id=%s>" % (self.__class__.__name__,
                                     self.GetSubject(),
                                     id_str)

    def __eq__(self, other):
        if other is None: return False
        ceid = self.msgstore.session.CompareEntryIDs
        return ceid(self.id[0], other.id[0]) and \
               ceid(self.id[1], other.id[1])

    def __ne__(self, other):
        return not self.__eq__(other)

    def GetID(self):
        return mapi.HexFromBin(self.id[0]), mapi.HexFromBin(self.id[1])

    def GetSubject(self):
        if self.subject is None:
            self.subject = self.GetField(PR_SUBJECT_A,)
        return self.subject

    def GetOutlookItem(self):
        hex_item_id = mapi.HexFromBin(self.id[1])
        hex_store_id = mapi.HexFromBin(self.id[0])
        return self.msgstore.outlook.Session.GetItemFromID(hex_item_id, hex_store_id)

    def IsFilterCandidate(self):
        # We don't attempt to filter:
        # * Non-mail items
        # * Messages that weren't actually received - this generally means user
        #   composed messages yet to be sent, or copies of "sent items".
        # It does *not* exclude messages that were user composed, but still
        # actually received by the user (ie, when you mail yourself)
        return self.msgclass.lower().startswith("ipm.note") and \
               (self.was_received or test_suite_running)

    def _GetPotentiallyLargeStringProp(self, prop_id, row):
        return GetPotentiallyLargeStringProp(self.mapi_object, prop_id, row)

    def _GetMessageText(self):
        # This is finally reliable.  The only messages this now fails for
        # are for "forwarded" messages, where the forwards are actually
        # in an attachment.  Later.
        # Note we *dont* look in plain text attachments, which we arguably
        # should.
        from spambayes import mboxutils

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

        # Some Outlooks deliver a strange notion of headers, including
        # interior MIME armor.  To prevent later errors, try to get rid
        # of stuff now that can't possibly be parsed as "real" (SMTP)
        # headers.
        headers = mboxutils.extract_headers(headers)

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
            # Find all attachments with
            # PR_ATTACH_MIME_TAG_A=multipart/signed
            table = self.mapi_object.GetAttachmentTable(0)
            restriction = (mapi.RES_PROPERTY,   # a property restriction
                           (mapi.RELOP_EQ,      # check for equality
                            PR_ATTACH_MIME_TAG_A,   # of the given prop
                            (PR_ATTACH_MIME_TAG_A, "multipart/signed")))
            try:
                rows = mapi.HrQueryAllRows(table,
                                           (PR_ATTACH_NUM,), # columns to get
                                           restriction,    # only these rows
                                           None,    # any sort order is fine
                                           0)       # any # of results is fine
            except pythoncom.com_error:
                # For some reason there are no rows we can get
                rows = []
            if len(rows) == 0:
                pass # Nothing we can fetch :(
            else:
                if len(rows) > 1:
                    print "WARNING: Found %d rows with multipart/signed" \
                          "- using first only" % len(rows)
                row = rows[0]
                (attach_num_tag, attach_num), = row
                assert attach_num_tag != PT_ERROR, \
                       "Error fetching attach_num prop"
                # Open the attachment
                attach = self.mapi_object.OpenAttach(attach_num,
                                                   None,
                                                   mapi.MAPI_DEFERRED_ERRORS)
                prop_ids = (PR_ATTACH_DATA_BIN,)
                hr, data = attach.GetProps(prop_ids, 0)
                attach_body = GetPotentiallyLargeStringProp(attach, prop_ids[0], data[0])
                # What we seem to have here now is a *complete* multi-part
                # mime message - that Outlook must have re-constituted on
                # the fly immediately after pulling it apart! - not unlike
                # exactly what we are doing ourselves right here - putting
                # it into a message object, so we can extract the text, so
                # we can stick it back into another one.  Ahhhhh.
                import email
                msg = email.message_from_string(attach_body)
                assert msg.is_multipart(), "Should be multi-part: %r" % attach_body
                # reduce down all sub messages, collecting all text/ subtypes.
                # (we could make a distinction between text and html, but
                # it is all joined together by this method anyway.)
                def collect_text_parts(msg):
                    collected = ''
                    if msg.is_multipart():
                        for sub in msg.get_payload():
                            collected += collect_text_parts(sub)
                    else:
                        if msg.get_content_maintype()=='text':
                            collected += msg.get_payload()
                        else:
                            #print "skipping content type", msg.get_content_type()
                            pass
                    return collected
                body = collect_text_parts(msg)

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
        # Return an email.Message object.
        #
        # strip_mime_headers is a hack, and should be left True unless you're
        # trying to display all the headers for diagnostic purposes.  If we
        # figure out something better to do, it should go away entirely.
        #
        # Problem #1:  suppose a msg is multipart/alternative, with
        # text/plain and text/html sections.  The latter MIME decorations
        # are plain missing in what _GetMessageText() returns.  If we leave
        # the multipart/alternative in the headers anyway, the email
        # package's "lax parsing" won't complain about not finding any
        # sections, but since the type *is* multipart/alternative then
        # anyway, the tokenizer finds no text/* parts at all to tokenize.
        # As a result, only the headers get tokenized.  By stripping
        # Content-Type from the headers (if present), the email pkg
        # considers the body to be text/plain (the default), and so it
        # does get tokenized.
        #
        # Problem #2:  Outlook decodes quoted-printable and base64 on its
        # own, but leaves any Content-Transfer-Encoding line in the headers.
        # This can cause the email pkg to try to decode the text again,
        # with unpleasant (but rarely fatal) results.  If we strip that
        # header too, no problem -- although the fact that a msg was
        # encoded in base64 is usually a good spam clue, and we miss that.
        #
        # Short course:  we either have to synthesize non-insane MIME
        # structure, or eliminate all evidence of original MIME structure.
        # Since we don't have a way to the former, by default this function
        # does the latter.
        import email
        text = self._GetMessageText()
        try:
            try:
                msg = email.message_from_string(text)
            except email.Errors.BoundaryError:
                # In case this is the
                #    "No terminating boundary and no trailing empty line"
                # flavor of BoundaryError, we can supply a trailing empty
                # line to shut it up.  It's certainly ill-formed MIME, and
                # probably spam.  We don't care about the exact MIME
                # structure, just the words it contains, so no harm and
                # much good in trying to suppress this error.
                try:
                    msg = email.message_from_string(text + "\n\n")
                except email.Errors.BoundaryError:
                    # But even this doesn't get *everything*.  We can still see:
                    #  "multipart message with no defined boundary"
                    # so now it is time to turn into a butcher - hack out
                    # the Content-Type header, so we see it as plain text.
                    butcher_pos = text.lower().find("\ncontent-type: ")
                    if butcher_pos < 0:
                        # This error just just gunna get caught below anyway
                        raise RuntimeError(
                            "email package croaked with boundary error, but "
                            "there appears to be no 'Content-Type' header")
                    # Put it back together, skipping the original "\n" but
                    # leaving the header leaving "\nSpamBayes-Content-Type: "
                    butchered = text[:butcher_pos] + "\nSpamBayes-" + \
                                text[butcher_pos+1:] + "\n\n"
                    msg = email.message_from_string(butchered)
        except:
            print "FAILED to create email.message from: ", `text`
            raise

        if strip_mime_headers:
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
        # [MarkH: MAPIUID objects are supported and hashable]

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

    def GetReadState(self):
        val = self.GetField(PR_MESSAGE_FLAGS)
        return (val&MSGFLAG_READ) != 0

    def SetReadState(self, is_read):
        self._EnsureObject()
        # always try and clear any pending delivery reports of read/unread
        if is_read:
            self.mapi_object.SetReadFlag(USE_DEFERRED_ERRORS|SUPPRESS_RECEIPT)
        else:
            self.mapi_object.SetReadFlag(USE_DEFERRED_ERRORS|CLEAR_READ_FLAG)
        if __debug__:
            if self.GetReadState() != is_read:
                print "MAPI SetReadState appears to have failed to change the message state"
                print "Requested set to %s but the MAPI field after was %r" % \
                      (is_read, self.GetField(PR_MESSAGE_FLAGS))

    def Save(self):
        assert self.dirty, "asking me to save a clean message!"
        # There are some known exceptions that can be raised by IMAP and hotmail
        # For now, we just let the caller handle all errors, and manually
        # reset the dirty flag.  Only current caller is filter.py
        # There are also some issues with the "unread flag" that fiddling this
        # save code may fix.
        # It seems that *not* specifying mapi.MAPI_DEFERRED_ERRORS solves alot
        # of said problems though!  So we don't!
        self.mapi_object.SaveChanges(mapi.KEEP_OPEN_READWRITE)
        self.dirty = False

    def _DoCopyMove(self, folder, isMove):
        assert not self.dirty, \
               "asking me to move a dirty message - later saves will fail!"
        dest_folder = self.msgstore._OpenEntry(folder.id)
        source_folder = self.msgstore._OpenEntry(self.folder_id)
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
        self.folder_id = None

    def MoveTo(self, folder):
        self._DoCopyMove(folder, True)

    def CopyTo(self, folder):
        self._DoCopyMove(folder, False)
    def GetFolder(self):
        # return a folder object with the parent, or None
        folder_id = (mapi.HexFromBin(self.folder_id[0]),
                     mapi.HexFromBin(self.folder_id[1]))
        return self.msgstore.GetFolder(folder_id)

    def RememberMessageCurrentFolder(self):
        self._EnsureObject()
        folder = self.GetFolder()
        props = ( (mapi.PS_PUBLIC_STRINGS, "SpamBayesOriginalFolderStoreID"),
                  (mapi.PS_PUBLIC_STRINGS, "SpamBayesOriginalFolderID")
                  )
        resolve_ids = self.mapi_object.GetIDsFromNames(props, mapi.MAPI_CREATE)
        prop_ids = PROP_TAG( PT_BINARY, PROP_ID(resolve_ids[0])), \
                   PROP_TAG( PT_BINARY, PROP_ID(resolve_ids[1]))

        prop_tuples = (prop_ids[0],folder.id[0]), (prop_ids[1],folder.id[1])
        self.mapi_object.SetProps(prop_tuples)
        self.dirty = True

    def GetRememberedFolder(self):
        props = ( (mapi.PS_PUBLIC_STRINGS, "SpamBayesOriginalFolderStoreID"),
                  (mapi.PS_PUBLIC_STRINGS, "SpamBayesOriginalFolderID")
                  )
        try:
            self._EnsureObject()
            resolve_ids = self.mapi_object.GetIDsFromNames(props, mapi.MAPI_CREATE)
            prop_ids = PROP_TAG( PT_BINARY, PROP_ID(resolve_ids[0])), \
                       PROP_TAG( PT_BINARY, PROP_ID(resolve_ids[1]))
            hr, data = self.mapi_object.GetProps(prop_ids,0)
            if hr != 0:
                return None
            (store_tag, store_id), (eid_tag, eid) = data
            folder_id = mapi.HexFromBin(store_id), mapi.HexFromBin(eid)
            return self.msgstore.GetFolder(folder_id)
        except:
            print "Error locating origin of message", self
            return None

def test():
    from win32com.client import Dispatch
    outlook = Dispatch("Outlook.Application")
    inbox = outlook.Session.GetDefaultFolder(constants.olFolderInbox)
    folder_id = inbox.Parent.StoreID, inbox.EntryID
    store = MAPIMsgStore()
    for folder in store.GetFolderGenerator([folder_id,], True):
        print folder
        for msg in folder.GetMessageGenerator():
            print msg
    store.Close()

if __name__=='__main__':
    test()
