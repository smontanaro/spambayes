# Test code for the SpamBayes dialogs.
import sys, os
if __name__=='__main__':
    # Hack for testing - setup sys.path
    try:
        import spambayes.Version
    except ImportError:
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), "..", "..")))
    try:
        import manager
    except ImportError:
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), "..")))
    
    import manager
    mgr = manager.GetManager()
    from dialogs import ShowDialog
    idd = "IDD_MANAGER"
    if len(sys.argv)>1:
        idd = sys.argv[1]
    if idd=='IDD_WIZARD':
        # not sure where this should go yet.
        import config
        extra_defaults = {
            "Wizard" : (
                ("preparation", "How prepared? radio on welcome", 0,
                 """""",
                config.INTEGER, config.RESTORE),
                (config.FolderIDOption,
                   "watch_folder_ids", "Folders to watch for new messages", [],
                    """The list of folders SpamBayes will watch for new messages,
                    processing messages as defined by the filters.""",
                    config.FOLDER_ID, config.DO_NOT_RESTORE),
                )
            }
        extra_defaults.update(config.defaults)
        # This is evil and wont look like this at all
        c = config.CreateConfig(extra_defaults)
        mgr.options = c
        mgr.config = config.OptionsContainer(c)


    ShowDialog(0, mgr, idd)
