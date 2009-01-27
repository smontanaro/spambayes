from __future__ import generators

import sys, os, re
import locale
from time import timezone

import email
from email.MIMEImage import MIMEImage
from email.Message import Message
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.Parser import HeaderParser
from email.Utils import formatdate

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

# MAPI imports etc.
from win32com.client import Dispatch, constants
from win32com.mapi import mapi, mapiutil
from win32com.mapi.mapitags import *
import pythoncom
import winerror

# Additional MAPI constants we dont have in Python
MESSAGE_MOVE = 0x1 # from MAPIdefs.h
MSGFLAG_READ = 0x1 # from MAPIdefs.h
MSGFLAG_UNSENT = 0x00000008

MYPR_BODY_HTML_A = 0x1013001e # magic <wink>
MYPR_BODY_HTML_W = 0x1013001f # ditto
MYPR_MESSAGE_ID_A = 0x1035001E # more magic (message id field used for Exchange)

CLEAR_READ_FLAG = 0x00000004
CLEAR_RN_PENDING = 0x00000020
CLEAR_NRN_PENDING = 0x00000040
SUPPRESS_RECEIPT = 0x1

FOLDER_DIALOG = 0x00000002

USE_DEFERRED_ERRORS = mapi.MAPI_DEFERRED_ERRORS # or set to zero to see what changes <wink>

#import warnings
#if sys.version_info >= (2, 3):
#    # sick off the new hex() warnings!
#    warnings.filterwarnings("ignore", category=FutureWarning, append=1)

# Nod to our automated test suite.  Currently supports a hack so our test
# message is filtered, and also for raising exceptions at key times.
# see tester.py for more details.
test_suite_running = False
test_suite_failure_request = None
test_suite_failure = None
# Set to the number of times we should fail, or None for all times.
test_suite_failure_count = None
# Sometimes the test suite will request that we simulate MAPI errors.
def help_test_suite(checkpoint_name):
    global test_suite_failure_request, test_suite_failure_count
    if test_suite_running and \
       test_suite_failure_request == checkpoint_name:
        if test_suite_failure_count:
            test_suite_failure_count -= 1
            if test_suite_failure_count==0:
                test_suite_failure_request = None
        raise test_suite_failure[0], test_suite_failure[1]

# Exceptions raised by this module.  Raw MAPI exceptions should never
# be raised to the caller.
class MsgStoreException(Exception):
    def __init__(self, mapi_exception, extra_msg = None):
        self.mapi_exception = mapi_exception
        self.extra_msg = extra_msg
        Exception.__init__(self, mapi_exception, extra_msg)
    def __str__(self):
        try:
            if self.mapi_exception is not None:
                err_str = GetCOMExceptionString(self.mapi_exception)
            else:
                err_str = self.extra_msg or ''
            return "%s: %s" % (self.__class__.__name__, err_str)
         # Python silently consumes exceptions here, and uses
         # <unprintable object>
        except:
            print "FAILED to str() a MsgStore exception!"
            import traceback
            traceback.print_exc()

# Exception raised when you attempt to get a message or folder that doesn't
# exist.  Usually means you are querying an ID that *was* valid, but has
# since been moved or deleted.
# Note you may get this exception "getting" objects (such as messages or
# folders), or accessing properties once the object was created (the message
# may be moved under us at any time)
class NotFoundException(MsgStoreException):
    pass

# Exception raised when you try and modify a "read only" object.
# Only currently examples are Hotmail and IMAP folders.
class ReadOnlyException(MsgStoreException):
    pass

# The object has changed since it was opened.
class ObjectChangedException(MsgStoreException):
    pass

# Utility functions for exceptions.  Convert a COM exception to the best
# manager exception.
def MsgStoreExceptionFromCOMException(com_exc):
    if IsNotFoundCOMException(com_exc):
        return NotFoundException(com_exc)
    if IsReadOnlyCOMException(com_exc):
        return ReadOnlyException(com_exc)
    scode = NormalizeCOMException(com_exc)[0]
    # And simple scode based ones.
    if scode == mapi.MAPI_E_OBJECT_CHANGED:
        return ObjectChangedException(com_exc)
    return MsgStoreException(com_exc)

def NormalizeCOMException(exc_val):
    hr, msg, exc, arg_err = exc_val
    if hr == winerror.DISP_E_EXCEPTION and exc:
        # 'client' exception - unpack 'exception object'
        wcode, source, msg, help1, help2, hr = exc
    return hr, msg, exc, arg_err

# Build a reasonable string from a COM exception tuple
def GetCOMExceptionString(exc_val):
    hr, msg, exc, arg_err = NormalizeCOMException(exc_val)
    err_string = mapiutil.GetScodeString(hr)
    return "Exception 0x%x (%s): %s" % (hr, err_string, msg)

# Does this exception probably mean "object not found"?
def IsNotFoundCOMException(exc_val):
    hr, msg, exc, arg_err = NormalizeCOMException(exc_val)
    return hr in [mapi.MAPI_E_OBJECT_DELETED, mapi.MAPI_E_NOT_FOUND]

# Does this exception probably mean "object not available 'cos you ain't logged
# in, or 'cos the server is down"?
def IsNotAvailableCOMException(exc_val):
    hr, msg, exc, arg_err = NormalizeCOMException(exc_val)
    return hr == mapi.MAPI_E_FAILONEPROVIDER

def IsReadOnlyCOMException(exc_val):
    # This seems to happen for IMAP mails (0x800cccd3)
    # and also for hotmail messages (0x8004dff7)
    known_failure_codes = -2146644781, -2147164169
    exc_val = NormalizeCOMException(exc_val)
    return exc_val[0] in known_failure_codes

def ReportMAPIError(manager, what, exc_val):
    hr, exc_msg, exc, arg_err = exc_val
    if hr == mapi.MAPI_E_TABLE_TOO_BIG:
        err_msg = what + _(" failed as one of your\r\n" \
                    "Outlook folders is full.  Futher operations are\r\n" \
                    "likely to fail until you clean up this folder.\r\n\r\n" \
                    "This message will not be reported again until SpamBayes\r\n"\
                    "is restarted.")
    else:
        err_msg = what + _(" failed due to an unexpected Outlook error.\r\n") \
                  + GetCOMExceptionString(exc_val) + "\r\n\r\n" + \
                  _("It is recommended you restart Outlook at the earliest opportunity\r\n\r\n" \
                    "This message will not be reported again until SpamBayes\r\n"\
                    "is restarted.")
    manager.ReportErrorOnce(err_msg)

# Our objects.
class MAPIMsgStore:
    # Stash exceptions in the class for ease of use by consumers.
    MsgStoreException = MsgStoreException
    NotFoundException = NotFoundException
    ReadOnlyException = ReadOnlyException
    ObjectChangedException = ObjectChangedException

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
        # I can't convince MAPI to give me the Unicode name, so we assume
        # encoded as MBCS.
        return val.decode("mbcs", "ignore")

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

    def GetRootFolder(self, store_id = None):
        # if storeID is None, gets the root folder from the default store.
        store = self._GetMessageStore(store_id)
        hr, data = store.GetProps((PR_ENTRYID, PR_IPM_SUBTREE_ENTRYID), 0)
        store_eid = data[0][1]
        subtree_eid = data[1][1]
        eid = mapi.HexFromBin(store_eid), mapi.HexFromBin(subtree_eid)
        return self.GetFolder(eid)

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
        try:
            store_id, entry_id = item_id
            return mapi.BinFromHex(store_id), mapi.BinFromHex(entry_id)
        except ValueError:
            raise MsgStoreException(None, "The specified ID '%s' is invalid" % (item_id,))

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
            try:
                folder_id = self.NormalizeID(folder_id)
            except MsgStoreException, details:
                print "NOTE: Skipping invalid folder", details
                continue
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
        try: # catch all MAPI errors
            try:
                # See if this is an Outlook folder item
                sid = mapi.BinFromHex(folder_id.StoreID)
                eid = mapi.BinFromHex(folder_id.EntryID)
                folder_id = sid, eid
            except AttributeError:
                # No 'EntryID'/'StoreID' properties - a 'normal' ID
                folder_id = self.NormalizeID(folder_id)
            folder = self._OpenEntry(folder_id)
            table = folder.GetContentsTable(0)
            # Ensure we have a long-term ID.
            rc, props = folder.GetProps( (PR_ENTRYID, PR_DISPLAY_NAME_A), 0)
            folder_id = folder_id[0], props[0][1]
            return MAPIMsgStoreFolder(self, folder_id, props[1][1],
                                  table.GetRowCount(0))
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def GetMessage(self, message_id):
        # Return a single message given either the ID, or an Outlook
        # message representing the object.
        try: # catch all MAPI exceptions.
            try:
                eid = mapi.BinFromHex(message_id.EntryID)
                sid = mapi.BinFromHex(message_id.Parent.StoreID)
                message_id = sid, eid
            except AttributeError:
                # No 'EntryID'/'StoreID' properties - a 'normal' ID
                message_id = self.NormalizeID(message_id)
            mapi_object = self._OpenEntry(message_id)
            hr, data = mapi_object.GetProps(MAPIMsgStoreMsg.message_init_props,0)
            return MAPIMsgStoreMsg(self, data)
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def YieldReceiveFolders(self, msg_class = "IPM.Note"):
        # Get the main receive folder for each message store.
        tab = self.session.GetMsgStoresTable(0)
        rows = mapi.HrQueryAllRows(tab,
                                    (PR_ENTRYID,),   # columns to retrieve
                                    None,            # all rows
                                    None,            # any sort order is fine
                                    0)               # any # of results is fine
        for row in rows:
            # get first entry, a (property_tag, value) pair, for PR_ENTRYID
            eid_tag, store_eid = row[0]
            try:
                store = self._GetMessageStore(store_eid)
                folder_eid, ret_class = store.GetReceiveFolder(msg_class, 0)
                hex_folder_eid = mapi.HexFromBin(folder_eid)
                hex_store_eid = mapi.HexFromBin(store_eid)
            except pythoncom.com_error, details:
                if not IsNotAvailableCOMException(details):
                    print "ERROR enumerating a receive folder -", details
                continue
            try:
                folder = self.GetFolder((hex_store_eid, hex_folder_eid))
                # For 'unconfigured' stores, or "stand-alone" PST files,
                # this is a root folder - so not what we wan't.  Only return
                # folders with a parent.
                if folder.GetParent() is not None:
                    yield folder
            except MsgStoreException, details:
                print "ERROR opening receive folder -", details
                # but we just continue
                continue

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
        print "Error getting property", mapiutil.GetPropTagName(prop_id), \
              "from stream:", d
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

# Some nasty stuff for getting RTF out of the message
def GetHTMLFromRTFProperty(mapi_object, prop_tag = PR_RTF_COMPRESSED):
    try:
        rtf_stream = mapi_object.OpenProperty(prop_tag, pythoncom.IID_IStream,
                                              0, 0)
        html_stream = mapi.WrapCompressedRTFStream(rtf_stream, 0)
        html = mapi.RTFStreamToHTML(html_stream)
    except pythoncom.com_error, details:
        if not IsNotFoundCOMException(details):
            print "ERROR getting RTF body", details
        return ""
    # html may be None if RTF not originally from HTML, but here we
    # always want a string
    return html or ''

class MAPIMsgStoreFolder:
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

    def GetFQName(self):
        parts = []
        parent = self
        while parent is not None:
            parts.insert(0, parent.name)
            try:
                # Ignore errors fetching parents - the caller just wants the
                # name - it may not be correctly 'fully qualified', but at
                # least we get something.
                parent = parent.GetParent()
            except MsgStoreException:
                break
        # We now end up with [0] being an empty string??, [1] being the
        # information store root folder name, etc.  Outlook etc all just
        # use the information store name here.
        if parts and not parts[0]:
            del parts[0]
        # Don't catch exceptions on the item itself - that is fatal,
        # and should be caught by the caller.
        # Replace the "root" folder name with the information store name
        # as Outlook, our Folder selector etc do.
        mapi_store = self.msgstore._GetMessageStore(self.id[0])
        hr, data = mapi_store.GetProps((PR_DISPLAY_NAME_A,), 0)
        name = data[0][1]
        if parts:
            # and replace with new name
            parts[0] = name
        else:
            # This can happen for the very root folder (ie, parent of the
            # top-level folder shown by Outlook.  This folder should *never*
            # be used directly.
            parts = [name]
            print "WARNING: It appears you are using the top-level root of " \
                  "the information store as a folder.  You probably don't "\
                  "want to do that"
        return "/".join(parts)

    def _FolderFromMAPIFolder(self, mapifolder):
        # Finally get the display name.
        hr, data = mapifolder.GetProps((PR_ENTRYID, PR_DISPLAY_NAME_A,), 0)
        eid = self.id[0], data[0][1]
        name = data[1][1]
        count = mapifolder.GetContentsTable(0).GetRowCount(0)
        return MAPIMsgStoreFolder(self.msgstore, eid, name, count)

    def GetParent(self):
        # return a folder object with the parent, or None if there is no
        # parent (ie, a top-level folder).  Raises an exception if there is
        # an error fetching the parent (which implies something wrong with the
        # item itself, rather than this being top-level)
        try:
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
            # Finally get the item itself
            return self._FolderFromMAPIFolder(parent)
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def OpenEntry(self, iid = None, flags = None):
        return self.msgstore._OpenEntry(self.id, iid, flags)

    def GetOutlookItem(self):
        try:
            hex_item_id = mapi.HexFromBin(self.id[1])
            hex_store_id = mapi.HexFromBin(self.id[0])
            return self.msgstore.outlook.Session.GetFolderFromID(hex_item_id, hex_store_id)
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def GetMessageGenerator(self, only_filter_candidates = True):
        folder = self.OpenEntry()
        table = folder.GetContentsTable(0)
        table.SetColumns(MAPIMsgStoreMsg.message_init_props, 0)
        if only_filter_candidates:
            # Limit ourselves to IPM.* objects - ie, messages.
            restriction = (mapi.RES_PROPERTY,   # a property restriction
                           (mapi.RELOP_GE,      # >=
                            PR_MESSAGE_CLASS_A,   # of the this prop
                            (PR_MESSAGE_CLASS_A, "IPM."))) # with this value
            table.Restrict(restriction, 0)
        while 1:
            # Getting 70 at a time was the random number that gave best
            # perf for me ;)
            rows = table.QueryRows(70, 0)
            if len(rows) == 0:
                break
            for row in rows:
                # Our restriction helped, but may not have filtered
                # every message we don't want to touch.
                # Note no exception will be raised below if the message is
                # moved under us, as we don't need to access any properties.
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
                              (PR_MESSAGE_CLASS_A, "IPM."))) # with this value
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
                # Note no exception will be raised below if the message is
                # moved under us, as we don't need to access any properties.
                msg = MAPIMsgStoreMsg(self.msgstore, row)
                if msg.IsFilterCandidate():
                    yield msg

    def IsReceiveFolder(self, msg_class = "IPM.Note"):
        # Is this folder the nominated "receive folder" for its store?
        try:
            mapi_store = self.msgstore._GetMessageStore(self.id[0])
            eid, ret_class = mapi_store.GetReceiveFolder(msg_class, 0)
            return mapi_store.CompareEntryIDs(eid, self.id[1])
        except pythoncom.com_error:
            # Error getting the receive folder from the store (or maybe  our
            # store - but that would be insane!).  Either way, we can't be it!
            return False

    def CreateFolder(self, name, comments = None, type = None,
                     open_if_exists = False, flags = None):
        if type is None: type = mapi.FOLDER_GENERIC
        if flags is None: flags = 0
        if open_if_exists: flags |= mapi.OPEN_IF_EXISTS
        folder = self.OpenEntry()
        ret = folder.CreateFolder(type, name, comments, None, flags)
        return self._FolderFromMAPIFolder(ret)

    def GetItemCount(self):
        try:
            folder = self.OpenEntry()
            return folder.GetContentsTable(0).GetRowCount(0)
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)
        
    # EmptyFolder() *permanently* deletes ALL messages and subfolders from
    # this folder without deleting the folder itself.
    #
    # WORD OF WARNING:  This is a *very dangerous* function that has the
    # potential to destroy a user's mail.  Don't even *think* about calling
    # this function on anything but the Certain Spam folder!
    def EmptyFolder(self, parentWindow):
        try:
            folder = self.OpenEntry()
            folder.EmptyFolder(parentWindow, None, FOLDER_DIALOG)
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def DoesFolderHaveOutlookField(self, field_name):
        # Returns True if the specified folder has an *Outlook* field with
        # the given name, False if the folder does not have it, or None
        # if we can't tell, or there was an error, etc.
        # We have discovered that Outlook stores 'Fields' for a folder as a
        # PR_USERFIELDS field in the hidden, 'associated' message with
        # message class IPC.MS.REN.USERFIELDS.  This is a binary property
        # which is undocumented, but probably could be reverse-engineered
        # with a little effort (see 'dump_props --dump-folder-user-props' for
        # an example of the raw data.  For now, the simplest thing appears
        # to be to check for a \0 character, followed by the property name
        # as an ascii string.
        try:
            folder = self.msgstore._OpenEntry(self.id)
            table = folder.GetContentsTable(mapi.MAPI_ASSOCIATED)
            restriction = (mapi.RES_PROPERTY,
                          (mapi.RELOP_EQ,
                           PR_MESSAGE_CLASS_A,
                           (PR_MESSAGE_CLASS_A, 'IPC.MS.REN.USERFIELDS')))
            cols = (PR_USERFIELDS,)
            table.SetColumns(cols, 0)
            rows = mapi.HrQueryAllRows(table, cols, restriction, None, 0)
            if len(rows)>1:
                print "Eeek - only expecting one row from IPC.MS.REN.USERFIELDS"
                print "got", repr(rows)
                return None
            if len(rows)==0:
                # New folders with no userdefined fields do not have such a row,
                # but this is a clear indication it does not exist.
                return False
            row = rows[0]
            val = GetPotentiallyLargeStringProp(folder, cols[0], row[0])
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)
        if type(val) != type(''):
            print "Value type incorrect - expected string, got", repr(val)
            return None
        return val.find("\0" + field_name) >= 0

    def DeleteMessages(self, message_things):
        # A *permanent* delete - MAPI has no concept of 'Deleted Items',
        # only Outlook does.  If you want a "soft" delete, you must locate
        # deleted item (via a special ID) and move it to there yourself
        # message_things may be ID tuples, or MAPIMsgStoreMsg instances.
        real_ids = []
        for thing in message_things:
            if isinstance(thing, MAPIMsgStoreMsg):
                real_ids.append( thing.id[1] )
                thing.mapi_object = thing.id = thing.folder_id = None
            else:
                real_ids.append(self.msgstore.NormalizeID(thing)[1])
        try:
            folder = self.msgstore._OpenEntry(self.id)
            # Nuke my MAPI reference, and set my ID to None
            folder.DeleteMessages(real_ids, 0, None, 0)
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def CreateTemporaryMessage(self, msg_flags = None):
        # Create a message designed to be used temporarily.  It is your
        # responsibility to delete when you are done with it.
        # If msg_flags is not None, it should be an integer for the
        # PR_MESSAGE_FLAGS property.  Note that Outlook appears to refuse
        # to set user properties on a message marked as 'unsent', which
        # is the default.  Setting to, eg, 1 marks it as a "not unsent, read"
        # message, which works fine with user properties.
        try:
            folder = self.msgstore._OpenEntry(self.id)
            imsg = folder.CreateMessage(None, 0)
            if msg_flags is not None:
                props = (PR_MESSAGE_FLAGS,msg_flags),
                imsg.SetProps(props)
            imsg.SaveChanges(0)
            hr, data = imsg.GetProps((PR_ENTRYID, PR_STORE_ENTRYID), 0)
            eid = data[0][1]
            storeid = data[1][1]
            msg_id = mapi.HexFromBin(storeid), mapi.HexFromBin(eid)
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)
        return self.msgstore.GetMessage(msg_id)

class MAPIMsgStoreMsg:
    # All the properties we must initialize a message with.
    # These include all the IDs we need, parent IDs, any properties needed
    # to determine if this is a "filterable" message, etc
    message_init_props = (PR_ENTRYID, PR_STORE_ENTRYID, PR_SEARCH_KEY,
                          PR_PARENT_ENTRYID, # folder ID
                          PR_MESSAGE_CLASS_A, # 'IPM.Note' etc
                          PR_RECEIVED_BY_ENTRYID, # who received it
                          PR_SUBJECT_A,
                          PR_TRANSPORT_MESSAGE_HEADERS_A,
                          )

    def __init__(self, msgstore, prop_row):
        self.msgstore = msgstore
        self.mapi_object = None

        # prop_row is a single mapi property row, with fields as above.
        # NOTE: We can't trust these properties for "large" values
        # (ie, strings, PT_BINARY, objects etc.), as they sometimes come
        # from the IMAPITable (which has a 255 limit on property values)
        # and sometimes from the object itself (which has no restriction).
        # This limitation is documented by MAPI.
        # Thus, we don't trust "PR_TRANSPORT_MESSAGE_HEADERS_A" more than
        # to ask "does the property exist?"
        tag, eid = prop_row[0] # ID
        tag, store_eid = prop_row[1]
        tag, searchkey = prop_row[2]
        tag, parent_eid = prop_row[3]
        tag, msgclass = prop_row[4]
        recby_tag, recby = prop_row[5]
        tag, subject = prop_row[6]
        headers_tag, headers = prop_row[7]

        self.id = store_eid, eid
        self.folder_id = store_eid, parent_eid
        self.msgclass = msgclass
        self.subject = subject
        has_headers = PROP_TYPE(headers_tag)==PT_STRING8
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
        # PR_RECEIVED_BY_ENTRYID is all we need (but has since discovered a
        # couple of messages without any PR_RECEIVED_BY properties - but *with*
        # PR_TRANSPORT_MESSAGE_HEADERS - *sigh*)
        self.was_received = PROP_TYPE(recby_tag) == PT_BINARY or has_headers
        self.dirty = False

        # For use with the spambayes.message messageinfo database.
        self.stored_attributes = ['c', 't', 'original_folder',
                                  'date_modified']
        self.t = None
        self.c = None
        self.date_modified = None
        self.original_folder = None

    def getDBKey(self):
        # Long lived search key.
        return self.searchkey

    def __repr__(self):
        if self.id is None:
            id_str = "(deleted/moved)"
        else:
            id_str = mapi.HexFromBin(self.id[0]), mapi.HexFromBin(self.id[1])
        return "<%s, '%s' id=%s>" % (self.__class__.__name__,
                                     self.GetSubject(),
                                     id_str)

    # as per search-key comments above, we also "enforce" this at the Python
    # level.  2 different messages, but one copied from the other, will
    # return "==".
    # Not being consistent could cause subtle bugs, especially in interactions
    # with various test tools.
    # Compare the GetID() results if you need to know different messages.
    def __hash__(self):
        return hash(self.searchkey)

    def __eq__(self, other):
        ceid = self.msgstore.session.CompareEntryIDs
        return ceid(self.searchkey, other.searchkey)

    def __ne__(self, other):
        return not self.__eq__(other)

    def GetID(self):
        return mapi.HexFromBin(self.id[0]), mapi.HexFromBin(self.id[1])

    def GetSubject(self):
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
        # GroupWise generates IPM.Anti-Virus.Report.45 (but I'm not sure how
        # it manages given it is an external server, and as far as I can tell,
        # this does not appear in the headers.
        if test_suite_running:
            # While the test suite is running, we *only* filter test msgs.
            return self.subject == "SpamBayes addin auto-generated test message"
        class_check = self.msgclass.lower()
        for check in "ipm.note", "ipm.anti-virus":
            if class_check.startswith(check):
                break
        else:
            # Not matching class - no good
            return False
        # Must match msg class to get here.
        return self.was_received

    def _GetPotentiallyLargeStringProp(self, prop_id, row):
        return GetPotentiallyLargeStringProp(self.mapi_object, prop_id, row)

    def _GetMessageText(self):
        parts = self._GetMessageTextParts()
        # parts is (headers, body, html) - which needs more formalizing -
        # GetMessageText should become deprecated - it makes no sense in the
        # face of multi-part messages.
        return "\n".join(parts)

    def _GetMessageTextParts(self):
        # This is almost reliable :).  The only messages this now fails for
        # are for "forwarded" messages, where the forwards are actually
        # in an attachment.  Later.
        # Note we *dont* look in plain text attachments, which we arguably
        # should.
        # This should be refactored into a function that returns the headers,
        # plus a list of email package sub-objects suitable for sending to
        # the classifier.
        from spambayes import mboxutils

        self._EnsureObject()
        prop_ids = (PR_BODY_A,
                    MYPR_BODY_HTML_A,
                    PR_TRANSPORT_MESSAGE_HEADERS_A)
        hr, data = self.mapi_object.GetProps(prop_ids,0)
        body = self._GetPotentiallyLargeStringProp(prop_ids[0], data[0])
        html = self._GetPotentiallyLargeStringProp(prop_ids[1], data[1])
        headers = self._GetPotentiallyLargeStringProp(prop_ids[2], data[2])
        # xxx - not sure what to do if we have both.
        if not html:
            html = GetHTMLFromRTFProperty(self.mapi_object)

        # Some Outlooks deliver a strange notion of headers, including
        # interior MIME armor.  To prevent later errors, try to get rid
        # of stuff now that can't possibly be parsed as "real" (SMTP)
        # headers.
        headers = mboxutils.extract_headers(headers)

        # Mail delivered internally via Exchange Server etc may not have
        # headers - fake some up.
        if not headers:
            headers = self._GetFakeHeaders()
        # Mail delivered via the Exchange Internet Mail MTA may have
        # gibberish at the start of the headers - fix this.
        elif headers.startswith("Microsoft Mail"):
            headers = "X-MS-Mail-Gibberish: " + headers
            # This mail typically doesn't have a Received header, which
            # is a real PITA for running the incremental testing setup.
            # To make life easier, we add in the fake one that the message
            # would have got if it had had no headers at all.
            if headers.find("Received:") == -1:
                prop_ids = PR_MESSAGE_DELIVERY_TIME
                hr, data = self.mapi_object.GetProps(prop_ids, 0)
                value = self._format_received(data[0][1])
                headers = "Received: %s\n%s" % (value, headers)

        if not html and not body:
            # Only ever seen this for "multipart/signed" messages, so
            # without any better clues, just handle this.
            # Find all attachments with
            # PR_ATTACH_MIME_TAG_A=multipart/signed
            # XXX - see also self._GetAttachmentsToInclude(), which
            # scans the attachment table - we should consolidate!
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

        return headers, body, html

    def _GetFakeHeaders(self):
        # This is designed to fake up some SMTP headers for messages
        # on an exchange server that do not have such headers of their own.
        prop_ids = PR_SUBJECT_A, PR_SENDER_NAME_A, PR_DISPLAY_TO_A, \
                   PR_DISPLAY_CC_A, PR_MESSAGE_DELIVERY_TIME, \
                   MYPR_MESSAGE_ID_A, PR_IMPORTANCE, PR_CLIENT_SUBMIT_TIME,
        hr, data = self.mapi_object.GetProps(prop_ids, 0)
        headers = ["X-Exchange-Message: true"]
        for header, index, potentially_large, format_func in (\
            ("Subject", 0, True, None),
            ("From", 1, True, self._format_address),
            ("To", 2, True, self._format_address),
            ("CC", 3, True, self._format_address),
            ("Received", 4, False, self._format_received),
            ("Message-ID", 5, True, None),
            ("Importance", 6, False, self._format_importance),
            ("Date", 7, False, self._format_time),
            ("X-Mailer", 7, False, self._format_version),
            ):
            if potentially_large:
                value = self._GetPotentiallyLargeStringProp(prop_ids[index],
                                                            data[index])
            else:
                value = data[index][1]
            if value:
                if format_func:
                    value = format_func(value)
                headers.append("%s: %s" % (header, value))
        return "\n".join(headers) + "\n"

    def _format_received(self, raw):
        # Fake up a 'received' header.  It's important that the date
        # is right, so that sort+group.py will work.  The rest is just more
        # clues for the tokenizer to find.
        return "(via local Exchange server); %s" % (self._format_time(raw),)

    def _format_time(self, raw):
        return formatdate(int(raw)-timezone, True)

    def _format_importance(self, raw):
        # olImportanceHigh = 2, olImportanceLow = 0, olImportanceNormal = 1
        return {0 : "low", 1 : "normal", 2 : "high"}[raw]

    def _format_version(self, unused):
        return "Microsoft Exchange Client"

    _address_re = re.compile(r"[()<>,:@!/=; ]")
    def _format_address(self, raw):
        # Fudge up something that's in the appropriate form.  We don't
        # have enough information available to get an actual working
        # email address.
        addresses = raw.split(";")
        formattedAddresses = []
        for address in addresses:
            address = address.strip()
            if address.find("@") >= 0:
                formattedAddress = address
            else:
                formattedAddress = "\"%s\" <%s>" % \
                        (address, self._address_re.sub('.', address))
            formattedAddresses.append(formattedAddress)
        return "; ".join(formattedAddresses)

    def _EnsureObject(self):
        if self.mapi_object is None:
            try:
                help_test_suite("MAPIMsgStoreMsg._EnsureObject")
                self.mapi_object = self.msgstore._OpenEntry(self.id)
            except pythoncom.com_error, details:
                raise MsgStoreExceptionFromCOMException(details)

    def _GetAttachmentsToInclude(self):
        # Get the list of attachments to include in the email package
        # Message object. Currently only images (BUT - consider consolidating
        # with the attachment handling above for signed messages!)
        from spambayes.Options import options
        from spambayes.ImageStripper import image_large_size_attribute

        # For now, we know these are the only 2 options that need attachments.
        if not options['Tokenizer', 'crack_images'] and \
           not options['Tokenizer', 'image_size']:
            return []
        try:
            table = self.mapi_object.GetAttachmentTable(0)
            tags = PR_ATTACH_NUM,PR_ATTACH_MIME_TAG_A,PR_ATTACH_SIZE,PR_ATTACH_DATA_BIN
            attach_rows = mapi.HrQueryAllRows(table, tags, None, None, 0)
        except pythoncom.com_error, why:
            attach_rows = []

        attachments = []
        # Create a new attachment for each image.
        for row in attach_rows:
            attach_num = row[0][1]
            # mime-tag may not exist - eg, seen on bounce messages
            mime_tag = None
            if PROP_TYPE(row[1][0]) != PT_ERROR:
                mime_tag = row[1][1]
            # oh - what is the library for this!?
            if mime_tag:
                typ, subtyp = mime_tag.split('/', 1)
                if typ == 'image':
                    size = row[2][1]
                    # If it is too big, just write the size.  ImageStripper.py
                    # checks this attribute.
                    if size > options["Tokenizer", "max_image_size"]:
                        sub = MIMEImage(None, subtyp)
                        setattr(sub, image_large_size_attribute, size)
                    else:
                        attach = self.mapi_object.OpenAttach(attach_num,
                                        None, mapi.MAPI_DEFERRED_ERRORS)
                        data = GetPotentiallyLargeStringProp(attach,
                                    PR_ATTACH_DATA_BIN, row[3])
                        sub = MIMEImage(data, subtyp)
                    attachments.append(sub)
        return attachments

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
        # We used to do the latter - but now that we must give valid
        # multipart messages which include attached images, we are forced
        # to try and do the former (but actually the 2 options are not
        # mutually exclusive - first we eliminate all evidence of original
        # MIME structure, before allowing the email package to synthesize
        # non-insane MIME structure.

        # We still jump through hoops though - if we have no interesting
        # attachments we attempt to return as close as possible as what
        # we always returned in the past - a "single-part" message with the
        # text and HTML as a simple text body.
        header_text, body, html = self._GetMessageTextParts()

        try: # catch all exceptions!
            # Try and decide early if we want multipart or not.
            # We originally just looked at the content-type - but Outlook
            # is unreliable WRT that header!  Also, consider a message multipart message
            # with only text and html sections and no additional attachments.
            # Outlook will generally have copied the HTML and Text sections
            # into the relevant properties and they will *not* appear as
            # attachments. We should return the 'single' message here to keep
            # as close to possible to what we used to return.  We can change
            # this policy in the future - but we would probably need to insist
            # on a full re-train as the training tokens will have changed for
            # many messages.
            attachments = self._GetAttachmentsToInclude()
            new_content_type = None
            if attachments:
                _class = MIMEMultipart
                payload = []
                if body:
                    payload.append(MIMEText(body))
                if html:
                    payload.append(MIMEText(html, 'html'))
                payload += attachments
                new_content_type = "multipart/mixed"
            else:
                # Single message part with both text and HTML.
                _class = Message
                payload = body + '\n' + html

            try:
                root_msg = HeaderParser(_class=_class).parsestr(header_text)
            except email.Errors.HeaderParseError:
                raise # sob
                # ack - it is about here we need to do what the old code did
                # below:  But - the fact the code below is dealing only
                # with content-type (and the fact we handle that above) makes
                # it less obvious....

                ## But even this doesn't get *everything*.  We can still see:
                ##  "multipart message with no defined boundary" or the
                ## HeaderParseError above.  Time to get brutal - hack out
                ## the Content-Type header, so we see it as plain text.
                #if msg is None:
                #    butcher_pos = text.lower().find("\ncontent-type: ")
                #    if butcher_pos < 0:
                #        # This error just just gunna get caught below anyway
                #        raise RuntimeError(
                #            "email package croaked with a MIME related error, but "
                #            "there appears to be no 'Content-Type' header")
                #    # Put it back together, skipping the original "\n" but
                #    # leaving the header leaving "\nSpamBayes-Content-Type: "
                #    butchered = text[:butcher_pos] + "\nSpamBayes-" + \
                #                text[butcher_pos+1:] + "\n\n"
                #    msg = email.message_from_string(butchered)
    
            # patch up mime stuff - these headers will confuse the email
            # package as it walks the attachments.
            if strip_mime_headers:
                for h, new_val in (('content-type', new_content_type),
                                   ('content-transfer-encoding', None)):
                    try:
                        root_msg['X-SpamBayes-Original-' + h] = root_msg[h]
                        del root_msg[h]
                    except KeyError:
                        pass
                    if new_val is not None:
                        root_msg[h] = new_val

            root_msg.set_payload(payload)

            # We used to call email.message_from_string(text) and catch:
            # email.Errors.BoundaryError: should no longer happen - we no longer
            # ask the email package to parse anything beyond headers.
            # email.Errors.HeaderParseError: caught above
        except:
            text = '\r\n'.join([header_text, body, html])
            print "FAILED to create email.message from: ", `text`
            raise

        return root_msg

    # XXX - this is the OLD version of GetEmailPackageObject() - it
    # temporarily remains as a testing aid, to ensure that the different
    # mime structure we now generate has no negative affects.
    # Use 'sandbox/export.py -o' to export to the testdata directory
    # in the old format, then run the cross-validation tests.
    def OldGetEmailPackageObject(self, strip_mime_headers=True):
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
                    msg = None
            except email.Errors.HeaderParseError:
                # This exception can come from parsing the header *or* the
                # body of a mime message.
                msg = None
            # But even this doesn't get *everything*.  We can still see:
            #  "multipart message with no defined boundary" or the
            # HeaderParseError above.  Time to get brutal - hack out
            # the Content-Type header, so we see it as plain text.
            if msg is None:
                butcher_pos = text.lower().find("\ncontent-type: ")
                if butcher_pos < 0:
                    # This error just just gunna get caught below anyway
                    raise RuntimeError(
                        "email package croaked with a MIME related error, but "
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
    # end of OLD GetEmailPackageObject
    
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
        try:
            if type(prop) != type(0):
                props = ( (mapi.PS_PUBLIC_STRINGS, prop), )
                propIds = self.mapi_object.GetIDsFromNames(props, mapi.MAPI_CREATE)
                type_tag = _MapiTypeMap.get(type(val))
                if type_tag is None:
                    raise ValueError, "Don't know what to do with '%r' ('%s')" % (
                                         val, type(val))
                prop = PROP_TAG(type_tag, PROP_ID(propIds[0]))
            help_test_suite("MAPIMsgStoreMsg.SetField")
            if val is None:
                # Delete the property
                self.mapi_object.DeleteProps((prop,))
            else:
                self.mapi_object.SetProps(((prop,val),))
            self.dirty = True
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def GetField(self, prop):
        # xxx - still raise_errors?
        self._EnsureObject()
        if type(prop) != type(0):
            props = ( (mapi.PS_PUBLIC_STRINGS, prop), )
            prop = self.mapi_object.GetIDsFromNames(props, 0)[0]
            if PROP_TYPE(prop) == PT_ERROR: # No such property
                return None
            prop = PROP_TAG( PT_UNSPECIFIED, PROP_ID(prop))
        try:
            hr, props = self.mapi_object.GetProps((prop,), 0)
            ((tag, val), ) = props
            if PROP_TYPE(tag) == PT_ERROR:
                if val == mapi.MAPI_E_NOT_ENOUGH_MEMORY:
                    # Too big for simple properties - get via a stream
                    return GetPropFromStream(self.mapi_object, prop)
                return None
            return val
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def GetReadState(self):
        val = self.GetField(PR_MESSAGE_FLAGS)
        return (val&MSGFLAG_READ) != 0

    def SetReadState(self, is_read):
        try:
            self._EnsureObject()
            # always try and clear any pending delivery reports of read/unread
            help_test_suite("MAPIMsgStoreMsg.SetReadState")
            if is_read:
                self.mapi_object.SetReadFlag(USE_DEFERRED_ERRORS|SUPPRESS_RECEIPT)
            else:
                self.mapi_object.SetReadFlag(USE_DEFERRED_ERRORS|CLEAR_READ_FLAG)
            if __debug__:
                if self.GetReadState() != is_read:
                    print "MAPI SetReadState appears to have failed to change the message state"
                    print "Requested set to %s but the MAPI field after was %r" % \
                          (is_read, self.GetField(PR_MESSAGE_FLAGS))
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def Save(self):
        assert self.dirty, "asking me to save a clean message!"
        # It seems that *not* specifying mapi.MAPI_DEFERRED_ERRORS solves a lot
        # problems!  So we don't!
        try:
            help_test_suite("MAPIMsgStoreMsg.Save")
            self.mapi_object.SaveChanges(mapi.KEEP_OPEN_READWRITE)
            self.dirty = False
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def _DoCopyMove(self, folder, isMove):
        assert not self.dirty, \
               "asking me to move a dirty message - later saves will fail!"
        try:
            dest_folder = self.msgstore._OpenEntry(folder.id)
            source_folder = self.msgstore._OpenEntry(self.folder_id)
            flags = 0
            if isMove: flags |= MESSAGE_MOVE
            eid = self.id[1]
            help_test_suite("MAPIMsgStoreMsg._DoCopyMove")
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
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

    def MoveTo(self, folder):
        self._DoCopyMove(folder, True)

    def CopyTo(self, folder):
        self._DoCopyMove(folder, False)

    # Functions to perform operations, but report the error (ONCE!) to the
    # user.  Any errors are re-raised so the caller can degrade gracefully if
    # necessary.
    # XXX - not too happy with these - they should go, and the caller should
    # handle (especially now that we work exclusively with exceptions from
    # this module.
    def MoveToReportingError(self, manager, folder):
        try:
            self.MoveTo(folder)
        except MsgStoreException, details:
            ReportMAPIError(manager, _("Moving a message"),
                            details.mapi_exception)
    def CopyToReportingError(self, manager, folder):
        try:
            self.MoveTo(folder)
        except MsgStoreException, details:
            ReportMAPIError(manager, _("Copying a message"),
                            details.mapi_exception)

    def GetFolder(self):
        # return a folder object with the parent, or None
        folder_id = (mapi.HexFromBin(self.folder_id[0]),
                     mapi.HexFromBin(self.folder_id[1]))
        return self.msgstore.GetFolder(folder_id)

    def RememberMessageCurrentFolder(self):
        self._EnsureObject()
        try:
            folder = self.GetFolder()
            # Also save this information in our messageinfo database, which
            # means that restoring should work even with IMAP.
            self.original_folder = folder.id[0], folder.id[1]
            props = ( (mapi.PS_PUBLIC_STRINGS, "SpamBayesOriginalFolderStoreID"),
                      (mapi.PS_PUBLIC_STRINGS, "SpamBayesOriginalFolderID")
                      )
            resolve_ids = self.mapi_object.GetIDsFromNames(props, mapi.MAPI_CREATE)
            prop_ids = PROP_TAG( PT_BINARY, PROP_ID(resolve_ids[0])), \
                       PROP_TAG( PT_BINARY, PROP_ID(resolve_ids[1]))

            prop_tuples = (prop_ids[0],folder.id[0]), (prop_ids[1],folder.id[1])
            self.mapi_object.SetProps(prop_tuples)
            self.dirty = True
        except pythoncom.com_error, details:
            raise MsgStoreExceptionFromCOMException(details)

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
            help_test_suite("MAPIMsgStoreMsg.GetRememberedFolder")
            return self.msgstore.GetFolder(folder_id)
        except:
            # Try to get it from the message info database, if possible
            if self.original_folder:
                return self.msgstore.GetFolder(self.original_folder)
            print "Error locating origin of message", self
            return None

def test():
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
