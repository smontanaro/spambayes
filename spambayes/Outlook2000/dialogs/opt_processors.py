# Option Control Processors for our dialog.
# These are extensions to basic Control Processors that are linked with 
# SpamBayes options.

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

import win32gui, win32api, win32con
import commctrl
import struct, array
from dlgutils import *

import processors

# A ControlProcessor that is linked up with options.  These get a bit smarter.
class OptionControlProcessor(processors.ControlProcessor):
    def __init__(self, window, control_ids, option):
        processors.ControlProcessor.__init__(self, window, control_ids)
        if option:
            sect_name, option_name = option.split(".")
            self.option = window.options.get_option(sect_name, option_name)
        else:
            self.option = None

    def GetPopupHelpText(self, idFrom):
        return " ".join(self.option.doc().split())

    # We override Init, and break it into 2 steps.
    def Init(self):
        self.UpdateControl_FromValue()

    def Done(self):
        self.UpdateValue_FromControl()

    def NotifyOptionChanged(self, option = None):
        if option is None:
            option = self.option
        self.window.OnOptionChanged(self, option)

    def SetOptionValue(self, value, option = None):
        if option is None:
            option = self.option
        print "Setting option '%s' (%s) -> %s" % \
              (option.display_name(), option.name, value)
        option.set(value)
        self.NotifyOptionChanged(option)

    # Only sub-classes know how to update their controls from the value.
    def UpdateControl_FromValue(self):
        raise NotImplementedError
    def UpdateValue_FromControl(self):
        raise NotImplementedError

# "Bool" buttons are simple - just toggle the value on the click.
# (Little more complex to handle "radio buttons" that are also boolean
# where we must "uncheck" the other button.
class BoolButtonProcessor(OptionControlProcessor):
    def OnCommand(self, wparam, lparam):
        code = win32api.HIWORD(wparam)
        if code == win32con.BN_CLICKED:
            self.UpdateValue_FromControl()
    def UpdateControl_FromValue(self):
        value = self.option.get()
        win32gui.SendMessage(self.GetControl(), win32con.BM_SETCHECK, value)
        for other in self.other_ids:
            win32gui.SendMessage(self.GetControl(other), win32con.BM_SETCHECK, not value)
    def UpdateValue_FromControl(self):
        check = win32gui.SendMessage(self.GetControl(), win32con.BM_GETCHECK)
        check = not not check # force bool!
        self.SetOptionValue(check)

# A "Combo" processor, that loads valid strings from the option.
class ComboProcessor(OptionControlProcessor):
    def OnCommand(self, wparam, lparam):
        code = win32api.HIWORD(wparam)
        if code == win32con.CBN_SELCHANGE:
            self.UpdateValue_FromControl()
    def UpdateControl_FromValue(self):
        # First load the combo options.
        combo = self.GetControl()
        index = sel_index = 0
        value = self.option.get()
        for s in self.option.valid_input():
            win32gui.SendMessage(combo, win32con.CB_ADDSTRING, 0, s)
            if value.startswith(s):
                sel_index = index
            index += 1
        win32gui.SendMessage(combo, win32con.CB_SETCURSEL, sel_index, 0)

    def UpdateValue_FromControl(self):
        combo = self.GetControl()
        sel = win32gui.SendMessage(combo, win32con.CB_GETCURSEL)
        len = win32gui.SendMessage(combo, win32con.CB_GETLBTEXTLEN, sel)
        buffer = array.array("c", "\0" * (len + 1))
        win32gui.SendMessage(combo, win32con.CB_GETLBTEXT, sel, buffer)
        # Trim the \0 from the end.
        self.SetOptionValue(buffer.tostring()[:-1])

class EditNumberProcessor(OptionControlProcessor):
    def __init__(self, window, control_ids, option):
        self.slider_id = control_ids and control_ids[1]
        OptionControlProcessor.__init__(self, window, control_ids, option)

    def GetPopupHelpText(self, id):
        if id == self.slider_id:
            return "As you drag this slider, the value to the right will " \
                   "automatically adjust"
        return OptionControlProcessor.GetPopupHelpText(self, id)
                      
    def GetMessages(self):
        return [win32con.WM_HSCROLL]

    def OnMessage(self, msg, wparam, lparam):
        slider = self.GetControl(self.slider_id)
        if slider == lparam:
            slider_pos = win32gui.SendMessage(slider, commctrl.TBM_GETPOS, 0, 0)
            slider_pos = float(slider_pos)
            str_val = str(slider_pos)
            edit = self.GetControl()
            win32gui.SendMessage(edit, win32con.WM_SETTEXT, 0, str_val)

    def OnCommand(self, wparam, lparam):
        code = win32api.HIWORD(wparam)
        if code==win32con.EN_CHANGE:
            try:
                self.UpdateValue_FromControl()
                self.UpdateSlider_FromEdit()
            except ValueError:
                # They are typing - value may be currently invalid
                pass
        
    def Init(self):
        OptionControlProcessor.Init(self)
        if self.slider_id:
            self.InitSlider()

    def InitSlider(self):
        slider = self.GetControl(self.slider_id)
        win32gui.SendMessage(slider, commctrl.TBM_SETRANGE, 0, MAKELONG(0, 100))
        win32gui.SendMessage(slider, commctrl.TBM_SETLINESIZE, 0, 1)
        win32gui.SendMessage(slider, commctrl.TBM_SETPAGESIZE, 0, 5)
        win32gui.SendMessage(slider, commctrl.TBM_SETTICFREQ, 10, 0)

    def UpdateControl_FromValue(self):
        win32gui.SendMessage(self.GetControl(), win32con.WM_SETTEXT, 0, str(self.option.get()))
        self.UpdateSlider_FromEdit()

    def UpdateSlider_FromEdit(self):
        slider = self.GetControl(self.slider_id)
        try:
            # Get as float so we dont fail should the .0 be there, but
            # then convert to int as the slider only works with ints
            val = int(float(self.option.get()))
        except ValueError:
            return
        win32gui.SendMessage(slider, commctrl.TBM_SETPOS, 1, val)

    def UpdateValue_FromControl(self):
        buf_size = 100
        buf = win32gui.PyMakeBuffer(buf_size)
        nchars = win32gui.SendMessage(self.GetControl(), win32con.WM_GETTEXT,
                                      buf_size, buf)
        str_val = buf[:nchars]
        val = float(str_val)
        if val < 0 or val > 100:
            raise ValueError, "Value must be between 0 and 100"
        self.SetOptionValue(val)
    
# Folder IDs, and the "include_sub" option, if applicable.
class FolderIDProcessor(OptionControlProcessor):
    def __init__(self, window, control_ids, option, option_include_sub = None):
        self.button_id = control_ids[1]

        if option_include_sub:
            incl_sub_sect_name, incl_sub_option_name = \
                                option_include_sub.split(".")
            self.option_include_sub = \
                            window.options.get_option(incl_sub_sect_name,
                                                      incl_sub_option_name)
        else:
            self.option_include_sub = None
        OptionControlProcessor.__init__(self, window, control_ids, option)

    def OnCommand(self, wparam, lparam):
        mgr = self.window.manager
        id = win32api.LOWORD(wparam)
        if id == self.button_id:
            is_multi = self.option.multiple_values_allowed()
            if is_multi:
                ids = self.option.get()
            else:
                ids = [self.option.get()]
            from dialogs import FolderSelector
            if self.option_include_sub:
                cb_state = self.option_include_sub.get()
            else:
                cb_state = None # don't show it.
            d = FolderSelector.FolderSelector(self.window.hwnd,
                                              mgr,
                                              ids,
                                              single_select=not is_multi,
                                              checkbox_state=cb_state)
            if d.DoModal() == win32con.IDOK:
                ids, include_sub = d.GetSelectedIDs()
                if is_multi:
                    self.SetOptionValue(ids)
                else:
                    self.SetOptionValue(ids[0])
                if self.option_include_sub:
                    self.SetOptionValue(include_sub, self.option_include_sub)
                self.UpdateControl_FromValue()

    def GetPopupHelpText(self, idFrom):
        if idFrom == self.button_id:
            return "Displays a list from which you can select folders."
        return OptionControlProcessor.GetPopupHelpText(self, idFrom)

    def UpdateControl_FromValue(self):
        # Set the static to folder names
        mgr = self.window.manager
        if self.option.multiple_values_allowed():
            ids = self.option.get()
        else:
            ids = [self.option.get()]
        names = []
        for eid in ids:
            if eid is not None:
                folder = mgr.message_store.GetFolder(eid)
                if folder is None:
                    name = "<unknown folder>"
                else:
                    name = folder.name
                names.append(name)
        win32gui.SetWindowText(self.GetControl(), "; ".join(names))

    def UpdateValue_FromControl(self):
        pass
