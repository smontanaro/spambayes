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
    ShowDialog(0, mgr, idd)
