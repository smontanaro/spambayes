# This package defines dialog boxes used by the main
# SpamBayes Outlook 2k integration code.

def LoadDialogs(rc_file = "dialogs.rc"):
    import os
    from resources import rcparser
    if not os.path.isabs(rc_file):
        rc_file = os.path.join( os.path.dirname( rcparser.__file__ ), rc_file)
    return rcparser.ParseDialogs(rc_file)

def ShowDialog(parent, manager, config, idd):
    """Displays another dialog"""
    if manager.dialog_parser is None:
        manager.dialog_parser = LoadDialogs()
    import dialog_map
    commands = dialog_map.dialog_map[idd]
    if not parent:
        import win32gui
        try:
            parent = win32gui.GetActiveWindow()
        except win32gui.error:
            pass
        
    import dlgcore
    dlg = dlgcore.ProcessorDialog(parent, manager, config, idd, commands)
    return dlg.DoModal()

def ShowWizard(parent, manager, idd = "IDD_WIZARD", use_existing_config = True):
    import config_wizard, win32con
    config = config_wizard.CreateWizardConfig(manager, use_existing_config)
    if ShowDialog(parent, manager, config, idd) == win32con.IDOK:
        print "Saving wizard changes"
        config_wizard.CommitWizardConfig(manager, config)
        manager.SaveConfig()
    else:
        print "Cancelling wizard"
        config_wizard.CancelWizardConfig(manager, config)
    
def MakePropertyPage(parent, manager, config, idd, yoffset=24):
    """Creates a child dialog box to use as property page in a tab control"""
    if manager.dialog_parser is None:
        manager.dialog_parser = LoadDialogs()
    import dialog_map
    commands = dialog_map.dialog_map[idd]
    if not parent:
        raise "Parent must be the tab control"
        
    import dlgcore
    dlg = dlgcore.ProcessorPage(parent, manager, config, idd, commands, yoffset)
    return dlg
    
import dlgutils
SetWaitCursor = dlgutils.SetWaitCursor
