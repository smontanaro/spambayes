# not sure where this should go yet.
import config
import copy

# NOTE: The Wizard works from a *complete* copy of the standard options
# but with an extra "Wizard" section to maintain state etc for the wizard.
# This initial option set may or may not have had values copied from the
# real runtime config - this allows either a "re-configure" or a
# "clean configure".
# Thus, the Wizard still uses standard config option where suitable - eg
# filter.watch_folder_ids
wizard_defaults = {
    "Wizard" : (
        ("preparation", "How prepared? radio on welcome", 0,
            """""",
        config.INTEGER, config.RESTORE),
        ("need_train", "Will moving to the train page actually train?", True,
            """""",
        config.BOOLEAN, config.RESTORE),
        ("can_go_next", "Is the Forward wizard button enabled?", True,
            """""",
        config.BOOLEAN, config.RESTORE),
        # Spam
        ("spam_folder_name", "Name of spam folder - ignored if ID set", "Spam",
            """""",
            "", config.RESTORE),
        # unsure
        ("unsure_folder_name", "Name of unsure folder - ignored if ID set", "Maybe Spam",
            """""",
            "", config.RESTORE),
    ),
}

def InitWizardConfig(manager, new_config, from_existing = True):
    new_config.filter.watch_folder_ids = []
    new_config.filter.watch_include_sub = False
    
    wc = new_config.wizard
    if from_existing:
        ids = copy.copy(manager.config.filter.watch_folder_ids)
        for id in ids:
            # Only get the folders that actually exist.
            if manager.message_store.GetFolder(id) is not None:
                new_config.filter.watch_folder_ids.append(id)
    if not new_config.filter.watch_folder_ids:
        for folder in manager.message_store.YieldReceiveFolders():
            new_config.train.watch_folder_ids.append(folder.GetID())
    if from_existing:
        fc = manager.config.filter
        if fc.spam_folder_id:
            folder = manager.message_store.GetFolder(fc.spam_folder_id)
            if folder is not None:
                new_config.filter.spam_folder_id = folder.GetID()
                wc.spam_folder_name = ""
        if fc.unsure_folder_id:
            folder = manager.message_store.GetFolder(fc.unsure_folder_id)
            if folder is not None:
                new_config.filter.unsure_folder_id = folder.GetID()
                wc.unsure_folder_name = ""
        tc = manager.config.training
        print "Ham are", tc.ham_folder_ids
        if tc.ham_folder_ids:
            new_config.training.ham_folder_ids = tc.ham_folder_ids
        if tc.spam_folder_ids:
            new_config.training.spam_folder_ids = tc.spam_folder_ids
    if new_config.training.ham_folder_ids or new_config.training.spam_folder_ids:
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
 