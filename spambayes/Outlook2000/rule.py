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
        self.write_field_name = "SpamProb"
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

    def _GetFolder(self, mgr):
        try:
            return mgr.mapi.GetFolder(self.folder_id)
        except pythoncom.com_error:
            return None

    def Act(self, mgr, msg, prob):
        if mgr.verbose > 1:
            print "Rule '%s': %.2f->%.2f (%.2f) (%s)" % (self.name, self.min, self.max, prob, msg.Subject[:20].encode("ascii", "replace"))
        if prob < self.min or prob > self.max:
            return False
        # Do mods before we move.
        outlook_ns = mgr.GetOutlookForCurrentThread().GetNamespace("MAPI")
        outlook_message = outlook_ns.GetItemFromID(msg.ID)
        if self.flag_message:
            outlook_message.FlagRequest = "Check Spam"
            outlook_message.FlagStatus = constants.olFlagMarked
            outlook_message.Save()
        if self.write_field:            
            format = 4 # 4=2 decimal, 3=1 decimal - index in "field chooser" combo when type=Number.
            prop = outlook_message.UserProperties.Add(self.write_field_name, constants.olNumber, True, format)
            prop.Value = prob
            outlook_message.Save()
        
        if self.action == "None":
            pass
        elif self.action == "Copy":
            outlook_message.Copy(outlook_ns.GetFolderFromID(self.folder_id))
        elif self.action == "Move":
            print "moving", self.flag_message
            outlook_message.Move(outlook_ns.GetFolderFromID(self.folder_id))
        else:
            print "Eeek - bad action", self.action

        return True

