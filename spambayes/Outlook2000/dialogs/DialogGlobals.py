# General helpers for out dialogs
def INDEXTOSTATEIMAGEMASK(i): # from new commctrl.h
    return i << 12

IIL_UNCHECKED = 1
IIL_CHECKED = 2

#these are the atom numbers defined by Windows for basic dialog controls
BUTTON    = 0x80
EDIT      = 0x81
STATIC    = 0x82
LISTBOX   = 0x83
SCROLLBAR = 0x84
COMBOBOX  = 0x85
