from __future__ import generators

from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api

from DialogGlobals import *

# Helpers for building the folder list
class FolderSpec:
    def __init__(self, folder_id, name):
        self.folder_id = folder_id
        self.name = name
        self.children = []

    def dump(self, level=0):
        prefix = "  " * level
        print prefix + self.name
        for c in self.children:
            c.dump(level+1)

#########################################################################
## CDO version of a folder walker.
#########################################################################
def _BuildFoldersCDO(folders):
    children = []
    folder = folders.GetFirst()
    while folder:
        spec = FolderSpec(folder.ID, folder.Name.encode("mbcs", "replace"))
        spec.children = _BuildFoldersCDO(folder.Folders)
        children.append(spec)
        folder = folders.GetNext()
    return children

def BuildFolderTreeCDO(session):
    infostores = session.InfoStores
    root = FolderSpec(None, "root")
    for i in range(infostores.Count):
        infostore = infostores[i+1]
        rootFolder = infostore.RootFolder
        folders = rootFolder.Folders
        spec = FolderSpec(rootFolder.ID, infostore.Name.encode("mbcs", "replace"))
        spec.children = _BuildFoldersCDO(folders)
        root.children.append(spec)
    return root

#########################################################################
## An extended MAPI version
#########################################################################
from win32com.mapi import mapi
from win32com.mapi.mapitags import *

def _BuildFoldersMAPI(msgstore, folder):
    # Get the hierarchy table for it.
    table = folder.GetHierarchyTable(0)
    children = []
    rows = mapi.HrQueryAllRows(table, (PR_ENTRYID,PR_DISPLAY_NAME_A), None, None, 0)
    for (eid_tag, eid),(name_tag, name) in rows:
        spec = FolderSpec(mapi.HexFromBin(eid), name)
        child_folder = msgstore.OpenEntry(eid, None, mapi.MAPI_DEFERRED_ERRORS)
        spec.children = _BuildFoldersMAPI(msgstore, child_folder)
        children.append(spec)
    return children

def BuildFolderTreeMAPI(session):
    root = FolderSpec(None, "root")
    tab = session.GetMsgStoresTable(0)
    rows = mapi.HrQueryAllRows(tab, (PR_ENTRYID, PR_DISPLAY_NAME_A), None, None, 0)
    for row in rows:
        (eid_tag, eid), (name_tag, name) = row
        msgstore = session.OpenMsgStore(0, eid, None, mapi.MDB_NO_MAIL | mapi.MAPI_DEFERRED_ERRORS)
        hr, data = msgstore.GetProps( ( PR_IPM_SUBTREE_ENTRYID,), 0)
        subtree_eid = data[0][1]
        folder = msgstore.OpenEntry(subtree_eid, None, mapi.MAPI_DEFERRED_ERRORS)
        spec = FolderSpec(mapi.HexFromBin(subtree_eid), name)
        spec.children = _BuildFoldersMAPI(msgstore, folder)
        root.children.append(spec)
    return root


#########################################################################
## The dialog itself
#########################################################################

# IDs for controls we use.
IDC_STATUS1 = win32ui.IDC_PROMPT1
IDC_STATUS2 = win32ui.IDC_PROMPT2
IDC_BUTTON_SEARCHSUB = win32ui.IDC_BUTTON1
IDC_BUTTON_CLEARALL = win32ui.IDC_BUTTON2
IDC_LIST_FOLDERS = win32ui.IDC_LIST1

class FolderSelector(dialog.Dialog):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    treestyle = cs | win32con.WS_BORDER | commctrl.TVS_HASLINES | commctrl.TVS_LINESATROOT | \
                commctrl.TVS_CHECKBOXES | commctrl.TVS_HASBUTTONS | \
                commctrl.TVS_DISABLEDRAGDROP | commctrl.TVS_SHOWSELALWAYS
    dt = [
        # Dialog itself.
        ["", (0, 0, 247, 215), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          "&Folders:",          -1,                   (7,   7,  47,  9), cs ],
        ["SysTreeView32", None,                 IDC_LIST_FOLDERS,     (7,  21, 172, 140), treestyle | win32con.WS_TABSTOP],
        [BUTTON,          '',                   IDC_BUTTON_SEARCHSUB, (7,  167, 126,  9), cs | win32con.BS_AUTOCHECKBOX | win32con.WS_TABSTOP],
        [STATIC,          "",                   IDC_STATUS1,          (7,  180, 220,  9), cs ],
        [STATIC,          "",                   IDC_STATUS2,          (7,  194, 220,  9), cs ],
        [BUTTON,         'OK',                  win32con.IDOK,        (190, 21,  50, 14), cs | win32con.BS_DEFPUSHBUTTON | win32con.WS_TABSTOP],
        [BUTTON,         'Cancel',              win32con.IDCANCEL,    (190, 39,  50, 14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],
        [BUTTON,         'C&lear All',          IDC_BUTTON_CLEARALL,  (190, 58,  50, 14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],
    ]

    def __init__ (self, mapi, selected_ids = None, single_select = False, checkbox_state = False, checkbox_text = None, desc_noun = "Select", desc_noun_suffix = "ed"):
        assert single_select == False or selected_ids is None or len(selected_ids)<=1
        dialog.Dialog.__init__ (self, self.dt)
        self.single_select = single_select
        self.next_item_id = 1
        self.item_map = {}

        self.select_desc_noun = desc_noun
        self.select_desc_noun_suffix = desc_noun_suffix
        self.selected_ids = selected_ids
        self.mapi = mapi
        self.checkbox_state = checkbox_state
        self.checkbox_text = checkbox_text or "Include &subfolders"

    def _MakeItemParam(self, item):
        item_id = self.next_item_id
        self.next_item_id += 1
        self.item_map[item_id] = item
        return item_id

    def _InsertSubFolders(self, hParent, folderSpec):
        num_children_selected = 0
        for child in folderSpec.children:
            text = child.name
            cItems = len(child.children)
            if cItems==0:
                bitmapCol = bitmapSel = 5 # blank doc
            else:
                bitmapCol = bitmapSel = 0 # folder
            if self.single_select:
                mask = state = 0
            else:
                if self.selected_ids and child.folder_id in self.selected_ids:
                    state = INDEXTOSTATEIMAGEMASK(IIL_CHECKED)
                    num_children_selected += 1
                else:
                    state = INDEXTOSTATEIMAGEMASK(IIL_UNCHECKED)
                mask = commctrl.TVIS_STATEIMAGEMASK
            item_id = self._MakeItemParam(child)
            hitem = self.list.InsertItem(hParent, 0, (None, state, mask, text, bitmapCol, bitmapSel, cItems, item_id))
            if self.single_select and self.selected_ids and child.folder_id in self.selected_ids:
                self.list.SelectItem(hitem)

            num_children_selected += self._InsertSubFolders(hitem, child)
        if num_children_selected and hParent:
            self.list.Expand(hParent, commctrl.TVE_EXPAND)
        return num_children_selected

    def _YieldChildren(self, h):
        try:
            h = self.list.GetNextItem(h, commctrl.TVGN_CHILD)
        except win32ui.error:
            h = None
        while h is not None:
            info = self.list.GetItem(h)
            spec = self.item_map[info[7]]
            yield info, spec
            # Check children
            for info, spec in self._YieldChildren(h):
                yield info, spec
            try:
                h = self.list.GetNextItem(h, commctrl.TVGN_NEXT)
            except win32ui.error:
                h = None

    def _YieldAllChildren(self):
        return self._YieldChildren(commctrl.TVI_ROOT)

    def _YieldCheckedChildren(self):
        if self.single_select:
            # If single-select, the checked state is not used, just the selected state.
            try:
                h = self.list.GetSelectedItem()
            except win32ui.error:
                return
            info = self.list.GetItem(h)
            spec = self.item_map[info[7]]
            yield info, spec
            return # single-hit yield.

        for info, spec in self._YieldAllChildren():
            checked = (info[1] >> 12) - 1
            if checked:
                yield info, spec

    def OnInitDialog (self):
        caption = "%s folder" % (self.select_desc_noun,)
        if not self.single_select:
            caption += "(s)"
        self.SetWindowText(caption)
        self.SetDlgItemText(IDC_BUTTON_SEARCHSUB, self.checkbox_text)
        if self.checkbox_state is None:
            self.GetDlgItem(IDC_BUTTON_SEARCHSUB).ShowWindow(win32con.SW_HIDE)
        else:
            self.GetDlgItem(IDC_BUTTON_SEARCHSUB).SetCheck(self.checkbox_state)
        self.list = self.GetDlgItem(win32ui.IDC_LIST1)

        self.HookNotify(self.OnTreeItemExpanding, commctrl.TVN_ITEMEXPANDING)
        self.HookNotify(self.OnTreeItemSelChanged, commctrl.TVN_SELCHANGED)
        self.HookNotify(self.OnTreeItemClick, commctrl.NM_CLICK)
        self.HookNotify(self.OnTreeItemDoubleClick, commctrl.NM_DBLCLK)
        self.HookCommand(self.OnClearAll, IDC_BUTTON_CLEARALL)

        bitmapID = win32ui.IDB_HIERFOLDERS
        bitmapMask = win32api.RGB(0,0,255)
        self.imageList = win32ui.CreateImageList(bitmapID, 16, 0, bitmapMask)
        self.list.SetImageList(self.imageList, commctrl.LVSIL_NORMAL)
        if self.single_select:
            # Remove the checkbox style from the list for single-selection
            style = win32api.GetWindowLong(self.list.GetSafeHwnd(), win32con.GWL_STYLE)
            style = style & ~commctrl.TVS_CHECKBOXES
            win32api.SetWindowLong(self.list.GetSafeHwnd(), win32con.GWL_STYLE, style)
            # Hide "clear all"
            self.GetDlgItem(IDC_BUTTON_CLEARALL).ShowWindow(win32con.SW_HIDE)

        if hasattr(self.mapi, "_oleobj_"): # Dispatch COM object
            # CDO
            tree = BuildFolderTreeCDO(self.mapi)
        else:
            # Extended MAPI.
            tree = BuildFolderTreeMAPI(self.mapi)
        self._InsertSubFolders(0, tree)
        self.selected_ids = [] # wipe this out while we are alive.
        self._UpdateStatus()

        return dialog.Dialog.OnInitDialog (self)

    def OnDestroy(self, msg):
        self.item_map = None
        return dialog.Dialog.OnDestroy(self, msg)

    def OnClearAll(self, id, code):
        if code == win32con.BN_CLICKED:
            for info, spec in self._YieldCheckedChildren():
                state = INDEXTOSTATEIMAGEMASK(IIL_UNCHECKED)
                mask = commctrl.TVIS_STATEIMAGEMASK
                self.list.SetItemState(info[0], state, mask)
            self._UpdateStatus()

    def _DoUpdateStatus(self, id, timeval):
        try:
            names = []
            num_checked = 0
            for info, spec in self._YieldCheckedChildren():
                num_checked += 1
                if len(names) < 20:
                    names.append(info[3])

            status_string = "%s%s %d folder" % (self.select_desc_noun, self.select_desc_noun_suffix, num_checked)
            if num_checked != 1:
                status_string += "s"
            self.SetDlgItemText(IDC_STATUS1, status_string)
            self.SetDlgItemText(IDC_STATUS2, "; ".join(names))
        finally:
            import timer
            timer.kill_timer(id)

    def _UpdateStatus(self):
        import timer
        timer.set_timer (0, self._DoUpdateStatus)

    def OnOK(self):
        self.selected_ids, self.checkbox_state = self.GetSelectedIDs()
        return self._obj_.OnOK()
    def OnCancel(self):
        return self._obj_.OnCancel()

    def OnTreeItemDoubleClick(self,(hwndFrom, idFrom, code), extra):
        if idFrom != IDC_LIST_FOLDERS: return None
        if self.single_select: # Only close on double-click for single-select
            self.OnOK()
        return 0

    def OnTreeItemClick(self,(hwndFrom, idFrom, code), extra):
        if idFrom != IDC_LIST_FOLDERS: return None
        self._UpdateStatus()
        return 0

    def OnTreeItemExpanding(self,(hwndFrom, idFrom, code), extra):
        if idFrom != IDC_LIST_FOLDERS: return None
        action, itemOld, itemNew, pt = extra
        return 0

    def OnTreeItemSelChanged(self,(hwndFrom, idFrom, code), extra):
        if idFrom != IDC_LIST_FOLDERS: return None
        action, itemOld, itemNew, pt = extra
        self._UpdateStatus()
        return 1

    def GetSelectedIDs(self):
        try:
            self.GetDlgItem(IDC_LIST_FOLDERS)
        except win32ui.error: # dialog dead!
            return self.selected_ids, self.checkbox_state
        ret = []
        for info, spec in self._YieldCheckedChildren():
            ret.append(spec.folder_id)
        return ret, self.GetDlgItem(IDC_BUTTON_SEARCHSUB).GetCheck() != 0

def TestWithCDO():
    from win32com.client import Dispatch
    mapi = Dispatch("MAPI.Session")
    mapi.Logon("", "", False, False)
    ids = [u'0000000071C4408983B0B24F8863EE66A8F79AFF82800000']
    d=FolderSelector(mapi, ids, single_select = False)
    d.DoModal()
    print d.GetSelectedIDs()

def TestWithMAPI():
    mapi.MAPIInitialize(None)
    logonFlags = mapi.MAPI_NO_MAIL | mapi.MAPI_EXTENDED | mapi.MAPI_USE_DEFAULT
    session = mapi.MAPILogonEx(0, None, None, logonFlags)
    ids = [u'0000000071C4408983B0B24F8863EE66A8F79AFF82800000']
    d=FolderSelector(session, ids, single_select = False)
    d.DoModal()
    print d.GetSelectedIDs()

if __name__=='__main__':
    TestWithMAPI()
