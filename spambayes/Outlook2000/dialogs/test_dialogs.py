# Test code for the SpamBayes dialogs.
if __name__=='__main__':
    # Hack for testing - setup sys.path
    try:
        import spambayes.Options
    except ImportError:
        import sys, os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), "..", "..")))
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), "..")))
    
    import manager
    mgr = manager.GetManager()
    from dialogs import ShowDialog
    ShowDialog(0, mgr, "IDD_MANAGER")
