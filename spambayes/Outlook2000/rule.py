import pythoncom
from win32com.client import constants
import time

class Rule:
    def __init__(self):
        self.name = "New Rule"
        self.enabled = True
        self.min = 0.0
        self.max = 0.9
        self.action = "None"
        self.flag_message = True
        self.write_field = True
        self.write_field_name = "SpamScore"
        self.folder_id = ""

    def __repr__(self):
        bits = ["Rule at 0x%x:\n" % (id(self),)]
        for name, ob in self.__dict__.items():
            bits.append(" rule.%s: %r\n" % (name, ob))
        return "".join(bits)

    def GetProblem(self, mgr):
        if self.min > self.max:
            return "The maximum value must be greater than the minimum"
        if self.action != "None":
            if not self.folder_id:
                return "You must specify a folder for 'Move' or 'Copy'"
            if self._GetFolder(mgr) is None:
                return "Can not locate the destination folder"
        if self.write_field and not self.write_field_name:
            return "You must specify the field name to create"

    def Act(self, mgr, msg, prob):
        if mgr.verbose > 1:
            print "Rule '%s': %.2f->%.2f (%.2f) (%s)" % (self.name, self.min, self.max, prob, repr(msg))
        if prob < self.min or prob > self.max:
            return False

##        if self.flag_message:
##            outlook_message.FlagRequest = "Check Spam"
##            outlook_message.FlagStatus = constants.olFlagMarked
##            dirty = True

        if self.write_field:
            msg.SetField(self.write_field_name, prob)
            msg.Save()

        if self.action == "None":
            pass
        elif self.action == "Copy":
            dest_folder = mgr.message_store.GetFolder(self.folder_id)
            msg.CopyTo(dest_folder)
        elif self.action == "Move":
            dest_folder = mgr.message_store.GetFolder(self.folder_id)
            msg.MoveTo(dest_folder)
        else:
            assert 0, "Eeek - bad action '%r'" % (self.action,)

        return True
