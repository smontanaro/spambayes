# not sure where this should go yet.
import config
import copy

wizard_defaults = {
    "Wizard" : (
        ("preparation", "How prepared? radio on welcome", 0,
            """""",
        config.INTEGER, config.RESTORE),
        (config.FolderIDOption,
            "watch_folder_ids", "Folders to watch for new messages", [],
            """The list of folders SpamBayes will watch for new messages,
            processing messages as defined by the filters.""",
            config.FOLDER_ID, config.DO_NOT_RESTORE),
        # Spam
        ("spam_folder_name", "Name of spam folder - ignored if ID set", "Spam",
            """""",
            "", config.RESTORE),
        (config.FolderIDOption,
            "spam_folder_id", "", None,
            """""",
            config.FOLDER_ID, config.DO_NOT_RESTORE),
        # unsure
        ("unsure_folder_name", "Name of unsure folder - ignored if ID set", "Maybe Spam",
            """""",
            "", config.RESTORE),
        (config.FolderIDOption,
            "unsure_folder_id", "", None,
            """""",
            config.FOLDER_ID, config.DO_NOT_RESTORE),
        (config.FolderIDOption,
            "train_ham_ids", "", [],
            """""",
            config.FOLDER_ID, config.DO_NOT_RESTORE),
        (config.FolderIDOption,
            "train_spam_ids", "", [],
            """""",
            config.FOLDER_ID, config.DO_NOT_RESTORE),
        ),
    }

def InitWizardConfig(manager, new_config, from_existing = True):
    wc = new_config.wizard
    wc.watch_folder_ids = []
    if from_existing:
        ids = copy.copy(manager.config.filter.watch_folder_ids)
        for id in ids:
            if manager.message_store.GetFolder(id) is not None:
                wc.watch_folder_ids.append(id)
    if not wc.watch_folder_ids:
        for folder in manager.message_store.YieldReceiveFolders():
            wc.watch_folder_ids.append(folder.GetID())
    if from_existing:
        fc = manager.config.filter
        if fc.spam_folder_id:
            folder = manager.message_store.GetFolder(fc.spam_folder_id)
            if folder is not None:
                wc.spam_folder_id = folder.GetID()
                wc.spam_folder_name = ""
        if fc.unsure_folder_id:
            folder = manager.message_store.GetFolder(fc.unsure_folder_id)
            if folder is not None:
                wc.unsure_folder_id = folder.GetID()
                wc.unsure_folder_name = ""
        tc = manager.config.training
        print "Ham are", tc.ham_folder_ids
        if tc.ham_folder_ids:
            wc.train_ham_ids = tc.ham_folder_ids
        if tc.spam_folder_ids:
            wc.train_spam_ids = tc.spam_folder_ids
    if wc.train_ham_ids or wc.train_spam_ids:
        wc.preparation = 1 # "already prepared"

def CommitWizardConfig(manager, wc):
    pass

def CreateWizardConfig(manager):
    import config
    defaults = wizard_defaults.copy()
    defaults.update(config.defaults)
    options = config.CreateConfig(defaults)
    cfg = config.OptionsContainer(options)
    InitWizardConfig(manager, cfg)
    return options, cfg
 