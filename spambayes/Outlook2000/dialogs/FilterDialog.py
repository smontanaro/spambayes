from __future__ import generators
import copy

from pywin.mfc import dialog
import win32con
import commctrl
import win32ui
import win32api
import pythoncom

from DialogGlobals import *
import RuleDialog

class RuleList:
    def __init__(self, parent, idc, rules, rule_factory,
                 idc_add = None, idc_copy = None, idc_edit = None, idc_remove = None,
                 idc_moveup = None, idc_movedown = None):
        self.parent = parent
        self.list = parent.GetDlgItem(idc)
        self.rules = rules
        self.rule_factory = rule_factory

        bitmapID = win32ui.IDB_HIERFOLDERS
        bitmapMask = win32api.RGB(0,0,255)
        self.imageList = win32ui.CreateImageList(bitmapID, 16, 0, bitmapMask)
        self.list.SetImageList(self.imageList, commctrl.LVSIL_NORMAL)

        parent.HookNotify(self.OnTreeItemSelChanged, commctrl.TVN_SELCHANGED)
        parent.HookNotify(self.OnTreeItemDoubleClick, commctrl.NM_DBLCLK)

        self._HookButton(idc_add, "butAdd", self.OnButAdd)
        self._HookButton(idc_copy, "butCopy", self.OnButCopy)
        self._HookButton(idc_edit, "butEdit", self.OnButEdit)
        self._HookButton(idc_remove, "butRemove", self.OnButRemove)
        self._HookButton(idc_moveup, "butMoveUp", self.OnButMoveUp)
        self._HookButton(idc_movedown, "butMoveDown", self.OnButMoveDown)
        self.Refresh()

    def _HookButton(self, idc, attr, func):
        if idc is None:
            setattr(self, attr, None)
        else:
            self.parent.HookCommand(func, idc)
            setattr(self, attr, self.parent.GetDlgItem(idc))

    def PushEnabledStates(self):
        self.pushed_state = {}
        for rule in self.rules:
            self.pushed_state[rule] = rule.enabled

    def PopEnabledStates(self):
        for rule in self.rules:
            old_state = self.pushed_state.get(rule)
            if old_state is not None:
                rule.enabled = old_state

    def Refresh(self, selIndex = None):
        if selIndex is None:
            selIndex = self.GetSelectedRuleIndex()
        self.SyncEnabledStates()
        self.list.DeleteAllItems()
        index = 0
        for rule in self.rules:
            if rule.enabled:
                state = INDEXTOSTATEIMAGEMASK(IIL_CHECKED)
            else:
                state = INDEXTOSTATEIMAGEMASK(IIL_UNCHECKED)
            mask = commctrl.TVIS_STATEIMAGEMASK
            bitmapCol = bitmapSel = 5
            hItem = self.list.InsertItem(commctrl.TVI_ROOT, 0, (None, state, mask, rule.name, bitmapCol, bitmapSel, 0, index))
            if index == selIndex:
                self.list.SelectItem(hItem)
            index += 1

    def _YieldItems(self):
        try:
            h = self.list.GetNextItem(commctrl.TVI_ROOT, commctrl.TVGN_CHILD)
        except win32ui.error:
            h = None
        index = 0
        while h is not None:
            yield h, index, self.rules[index]
            index += 1
            try:
                h = self.list.GetNextItem(h, commctrl.TVGN_NEXT)
            except win32ui.error:
                h = None

    # No reliable way to get notified of checkbox state - so
    # when we need to know, this will set rule.enabled to the
    # current state of the checkbox.
    def SyncEnabledStates(self):
        mask = INDEXTOSTATEIMAGEMASK(IIL_UNCHECKED) | INDEXTOSTATEIMAGEMASK(IIL_CHECKED)
        for h, index, rule in self._YieldItems():
            state = self.list.GetItemState(h, mask)
            checked = (state >> 12) - 1
            rule.enabled = checked

    def GetSelectedRuleIndex(self):
        try:
            hitem = self.list.GetSelectedItem()
        except win32ui.error:
            return None

        for h, index, rule in self._YieldItems():
            if hitem == h:
                return index

    def OnTreeItemSelChanged(self,(hwndFrom, idFrom, code), extra):
        #if idFrom != IDC_LIST_FOLDERS: return None
        action, itemOld, itemNew, pt = extra

        if self.butRemove is not None: self.butRemove.EnableWindow(itemNew != 0)
        if self.butEdit is not None: self.butEdit.EnableWindow(itemNew != 0)
        if self.butCopy is not None: self.butCopy.EnableWindow(itemNew != 0)
        if itemNew:
            index = self.GetSelectedRuleIndex()
            if self.butMoveUp is not None:
                self.butMoveUp.EnableWindow(index > 0)
            if self.butMoveDown is not None:
                self.butMoveDown.EnableWindow(index < len(self.rules)-1)
        else:
            self.butMoveUp.EnableWindow(False)
            self.butMoveDown.EnableWindow(False)
        return 1

    def OnTreeItemDoubleClick(self,(hwndFrom, idFrom, code), extra):
        if self.butEdit is not None:
            self.OnButEdit(idFrom, win32con.BN_CLICKED)

    def OnButRemove(self, id, code):
        if code == win32con.BN_CLICKED:
            self.SyncEnabledStates()
            index = self.GetSelectedRuleIndex()
            hitem = self.list.GetSelectedItem()
            name = self.rules[index].name
            result = self.parent.MessageBox("Are you sure you wish to delete rule '%s'?" % (name,), "Delete confirmation", win32con.MB_YESNO)
            if result==win32con.IDYES:
                self.list.DeleteItem(hitem)
                del self.rules[index]
                self.Refresh()

    def OnButAdd(self, id, code):
        if code == win32con.BN_CLICKED:
            new_rule = self.rule_factory()
            d = RuleDialog.RuleDialog(new_rule, self.parent.mgr)
            if d.DoModal()==win32con.IDOK:
                self.rules.append(new_rule)
                self.Refresh(len(self.rules)-1)

    def OnButEdit(self, id, code):
        if code == win32con.BN_CLICKED:
            self.SyncEnabledStates()
            index = self.GetSelectedRuleIndex()

            rule = copy.copy(self.rules[index])
            d = RuleDialog.RuleDialog(rule, self.parent.mgr)
            if d.DoModal()==win32con.IDOK:
                self.rules[index] = rule
                self.Refresh()

    def OnButCopy(self, id, code):
        if code == win32con.BN_CLICKED:
            self.SyncEnabledStates()
            index = self.GetSelectedRuleIndex()

            rule = copy.copy(self.rules[index])
            rule.name = "Copy of " + rule.name
            d = RuleDialog.RuleDialog(rule, self.parent.mgr)
            if d.DoModal()==win32con.IDOK:
                self.rules.append(rule)
                self.Refresh(len(self.rules)-1)

    def OnButMoveUp(self, id, code):
        if code == win32con.BN_CLICKED:
            self.SyncEnabledStates()
            index = self.GetSelectedRuleIndex()
            assert index > 0, "Can't move index zero up!"
            old = self.rules[index]
            self.rules[index] = self.rules[index-1]
            self.rules[index-1] = old
            self.Refresh(index-1)

    def OnButMoveDown(self, id, code):
        if code == win32con.BN_CLICKED:
            self.SyncEnabledStates()
            index = self.GetSelectedRuleIndex()
            num = len(self.rules)
            assert index < num-1, "Can't move last index down!"
            old = self.rules[index]
            self.rules[index] = self.rules[index+1]
            self.rules[index+1] = old
            self.Refresh(index+1)

IDC_FOLDER_NAMES=1024
IDC_BROWSE=1025
IDC_BUT_DELETE=1026
IDC_BUT_NEW=1027
IDC_BUT_EDIT=1028
IDC_LIST_RULES=1029
IDC_BUT_FILTERNOW=1030
IDC_BUT_UNREAD=1031
IDC_BUT_COPY=1032
IDC_BUT_MOVEUP=1033
IDC_BUT_MOVEDOWN=1034


class FilterArrivalsDialog(dialog.Dialog):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    csts = cs | win32con.WS_TABSTOP
    treestyle = csts | win32con.WS_BORDER | commctrl.TVS_CHECKBOXES | commctrl.TVS_DISABLEDRAGDROP | commctrl.TVS_SHOWSELALWAYS
    filter_msg = "Filter the following folders as messages arrive"
    dt = [
        # Dialog itself.
        ["Filters", (0, 0, 249, 195), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          filter_msg,           -1,                  (  8,   9, 168,  11), cs],
        [STATIC,          "",                   IDC_FOLDER_NAMES,    (  7,  20, 175,  12), cs   | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],
        [BUTTON,          '&Browse',            IDC_BROWSE,          (190,  19,  50,  14), csts | win32con.BS_PUSHBUTTON],
        [BUTTON,          "Enabled Rules",      -1,                  (  7,  40, 237, 130), cs   | win32con.BS_GROUPBOX],
        ["SysTreeView32", None,                 IDC_LIST_RULES,      ( 18,  52, 164,  95), treestyle],

        [BUTTON,          "&New...",            IDC_BUT_NEW,         (190,  52,  50,  14), csts ],
        [BUTTON,          "&Copy..",            IDC_BUT_COPY,        (190,  72,  50,  14), csts ],
        [BUTTON,          "&Modify...",         IDC_BUT_EDIT,        (190,  92,  50,  14), csts | win32con.WS_DISABLED],
        [BUTTON,          "&Delete",            IDC_BUT_DELETE,      (190, 112,  50,  14), csts | win32con.WS_DISABLED],

        [BUTTON,          "Move &Up",           IDC_BUT_MOVEUP,      ( 15, 150,  73,  14), csts | win32con.WS_DISABLED],
        [BUTTON,          "Move &Down",         IDC_BUT_MOVEDOWN,    (109, 150,  73,  14), csts | win32con.WS_DISABLED],

        [BUTTON,         '&Filter Now...',      IDC_BUT_FILTERNOW,   ( 15, 175,  50,  14), csts | win32con.BS_PUSHBUTTON],
        [BUTTON,         'Close',               win32con.IDOK,       (190, 175,  50,  14), csts | win32con.BS_DEFPUSHBUTTON],
    ]

    def __init__(self, mgr, rule_factory, filterer):
        self.mgr = mgr
        self.rule_factory = rule_factory
        self.filterer = filterer
        dialog.Dialog.__init__(self, self.dt)

    def OnInitDialog(self):
        self.list = RuleList(self, IDC_LIST_RULES, self.mgr.config.rules, self.rule_factory, IDC_BUT_NEW, IDC_BUT_COPY, IDC_BUT_EDIT, IDC_BUT_DELETE, IDC_BUT_MOVEUP, IDC_BUT_MOVEDOWN)
        self.HookCommand(self.OnButBrowse, IDC_BROWSE)
        self.HookCommand(self.OnButFilterNow, IDC_BUT_FILTERNOW)
        self.UpdateFolderNames()
        return dialog.Dialog.OnInitDialog(self)

    def OnOK(self):
        self.list.SyncEnabledStates()
        return dialog.Dialog.OnOK(self)

    def OnDestroy(self,msg):
        dialog.Dialog.OnDestroy(self, msg)
        self.list = None
        self.mgr = None

    def UpdateFolderNames(self):
        names = []
        folder_ids = self.mgr.config.filter.folder_ids
        for eid in folder_ids:
            try:
                name = self.mgr.message_store.GetFolder(eid).name
            except pythoncom.com_error:
                name = "<unknown folder>"
            names.append(name)
        self.SetDlgItemText(IDC_FOLDER_NAMES, "; ".join(names))

    def OnButBrowse(self, id, code):
        if code == win32con.BN_CLICKED:
            import FolderSelector
            filter = self.mgr.config.filter
            d = FolderSelector.FolderSelector(self.mgr.message_store.session, filter.folder_ids,checkbox_state=filter.include_sub)
            if d.DoModal()==win32con.IDOK:
                filter.folder_ids, filter.include_sub = d.GetSelectedIDs()
                self.UpdateFolderNames()

    def OnButFilterNow(self, id, code):
        if code == win32con.BN_CLICKED:
            self.list.SyncEnabledStates()
            self.list.PushEnabledStates()
            d = FilterNowDialog(self.mgr, self.rule_factory, self.filterer)
            d.DoModal()
            self.list.PopEnabledStates()
            self.list.Refresh()

from AsyncDialog import *

class FilterNowDialog(AsyncDialogBase):
    style = win32con.DS_MODALFRAME | win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.DS_SETFONT
    cs = win32con.WS_CHILD | win32con.WS_VISIBLE
    treestyle = cs | win32con.WS_BORDER | commctrl.TVS_CHECKBOXES | commctrl.TVS_DISABLEDRAGDROP | commctrl.TVS_SHOWSELALWAYS
    only_unread = "Only apply the filter to unread mail"
    process_start_text = "&Start filtering"
    process_stop_text = "&Stop filtering"
    dt = [
        # Dialog itself.
        ["Filter Now", (0, 0, 244, 221), style, None, (8, "MS Sans Serif")],
        # Children
        [STATIC,          "Filter the following folders", -1,        (  8,   9, 168,  11), cs],
        [STATIC,          "",                   IDC_FOLDER_NAMES,    (  7,  20, 172,  12), cs | win32con.SS_LEFTNOWORDWRAP | win32con.SS_CENTERIMAGE | win32con.SS_SUNKEN],
        [BUTTON,          '&Browse',            IDC_BROWSE,          (187,  19,  50,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],
        [BUTTON,          "Run the following rules", -1,             (  7,  40, 230, 113), cs | win32con.BS_GROUPBOX],
        ["SysTreeView32", None,                 IDC_LIST_RULES,      ( 14,  52, 216,  95), treestyle | win32con.WS_TABSTOP],
        [BUTTON,          only_unread,          IDC_BUT_UNREAD,      ( 15, 157, 149,   9), cs | win32con.BS_AUTOCHECKBOX | win32con.WS_TABSTOP],

        ["msctls_progress32", '',               IDC_PROGRESS,        ( 10, 170, 227,  11), cs | win32con.WS_BORDER],
        [STATIC,          '',                   IDC_PROGRESS_TEXT,   ( 10, 186, 227,  10), cs ],

        [BUTTON,         process_start_text,    IDC_START,           (  7, 200,  60,  14), cs | win32con.BS_PUSHBUTTON | win32con.WS_TABSTOP],
        [BUTTON,         'Close',               win32con.IDOK,       (187, 200,  50,  14), cs | win32con.BS_DEFPUSHBUTTON | win32con.WS_TABSTOP],
    ]
    disable_while_running_ids = [IDC_LIST_RULES, IDC_BUT_UNREAD, IDC_BROWSE, win32con.IDOK]

    def __init__(self, mgr, rule_factory, filterer):
        self.mgr = mgr
        self.filterer = filterer
        self.rule_factory = rule_factory
        AsyncDialogBase.__init__ (self, self.dt)

    def OnInitDialog(self):
        self.list = RuleList(self, IDC_LIST_RULES, self.mgr.config.rules, self.rule_factory)
        self.HookCommand(self.OnButBrowse, IDC_BROWSE)
        self.HookCommand(self.OnButUnread, IDC_BUT_UNREAD)
        if self.mgr.config.filter_now.only_unread:
            self.GetDlgItem(IDC_BUT_UNREAD).SetCheck(1)
        else:
            self.GetDlgItem(IDC_BUT_UNREAD).SetCheck(0)
        self.UpdateFolderNames()
        return AsyncDialogBase.OnInitDialog(self)

    def UpdateFolderNames(self):
        names = []
        for eid in self.mgr.config.filter_now.folder_ids:
            try:
                name = self.mgr.message_store.GetFolder(eid).name
            except pythoncom.com_error:
                name = "<unknown folder>"
            names.append(name)
        self.SetDlgItemText(IDC_FOLDER_NAMES, "; ".join(names))

    def OnButBrowse(self, id, code):
        if code == win32con.BN_CLICKED:
            import FolderSelector
            filter = self.mgr.config.filter_now
            d = FolderSelector.FolderSelector(self.mgr.message_store.session, filter.folder_ids,checkbox_state=filter.include_sub)
            if d.DoModal()==win32con.IDOK:
                filter.folder_ids, filter.include_sub = d.GetSelectedIDs()
                self.UpdateFolderNames()

    def OnButUnread(self, id, code):
        if code == win32con.BN_CLICKED:
            self.mgr.config.filter_now.only_unread = self.GetDlgItem(IDC_BUT_UNREAD).GetCheck() != 0

    def StartProcess(self):
        self.list.SyncEnabledStates()
        return AsyncDialogBase.StartProcess(self)

    def _DoProcess(self):
        if self.filterer is None:
            print "Testing, testing, 1...2...3..."
        else:
            self.mgr.WorkerThreadStarting()
            try:
                self.filterer(self.mgr, self.progress, self.mgr.config.filter_now)
            finally:
                self.mgr.WorkerThreadEnding()

if __name__=='__main__':
    # This doesnt work - still uses CDO.
    from win32com.client import Dispatch
    import pythoncom
    mapi = Dispatch("MAPI.Session")
    mapi.Logon()

    class Config: pass
    class Manager: pass
    mgr = Manager()
    mgr.mapi = mapi
    mgr.config = config = Config()
    config.filter = Config()
    config.filter.folder_ids = [mapi.Inbox.ID]
    config.filter.include_sub = True
    config.filter_now=Config()
    config.filter_now.folder_ids = [mapi.Inbox.ID]
    config.filter_now.include_sub = True
    config.filter_now.only_unread= True

    class Rule:
        def __init__(self):
            self.enabled = True
            self.name = "My Rule"
            self.min = 0.1
            self.max = 0.9
            self.action = "Move"
            self.flag_message = True
            self.write_field = True
            self.write_field_name = "SpamProb"
            self.folder_id = ""
        def GetProblem(self, mgr):
            if self.min > self.max:
                return "max must be > min"

    config.rules = [Rule()]

    tester = FilterArrivalsDialog
    #tester = FilterNowDialog
    d = tester(mgr, Rule, None)
    d.DoModal()
