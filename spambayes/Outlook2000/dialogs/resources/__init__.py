# Package that manages and defines dialog resources

def GetImageParamsFromBitmapID(rc_parser, bmpid):
    import os, sys
    import win32gui, win32con, win32api
    if type(bmpid)==type(0):
        bmpid = rc_parser.names[bmpid]
    # For both binary and source versions, we currently load from files.
    # In future py2exe built binary versions we will be able to load the
    # bitmaps directly from our DLL.
    filename = rc_parser.bitmaps[bmpid]
    if hasattr(sys, "frozen"):
        # bitmap in the app/images directory
        # dont have manager available :(
        dll_filename = win32api.GetModuleFileName(sys.frozendllhandle)
        app_dir = os.path.dirname(dll_filename)
        filename = os.path.join(app_dir, "images", filename)
    else:
        if not os.path.isabs(filename):
            # In this directory
            filename = os.path.join( os.path.dirname( __file__ ), filename)
    return 0, filename, win32con.LR_LOADFROMFILE
