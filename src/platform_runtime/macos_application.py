"""macOS process metadata needed by the native application menu."""

from __future__ import annotations

import ctypes
import platform


_PROGRAM_NAME_BYTES: bytes | None = None


def _objc_send(restype, *argtypes):
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
    return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(
        address
    )


def _set_cocoa_process_name(encoded: bytes) -> None:
    ctypes.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p

    process_class = objc.objc_getClass(b"NSProcessInfo")
    string_class = objc.objc_getClass(b"NSString")
    process = _objc_send(ctypes.c_void_p)(
        process_class, objc.sel_registerName(b"processInfo")
    )
    cocoa_name = _objc_send(ctypes.c_void_p, ctypes.c_char_p)(
        string_class, objc.sel_registerName(b"stringWithUTF8String:"), encoded
    )
    _objc_send(None, ctypes.c_void_p)(
        process, objc.sel_registerName(b"setProcessName:"), cocoa_name
    )


def set_macos_program_name(name: str) -> bool:
    """Set the native process name before QApplication creates the menu bar."""
    if platform.system() != "Darwin":
        return False
    global _PROGRAM_NAME_BYTES
    encoded = name.encode("utf-8")
    if not encoded or b"\0" in encoded:
        raise ValueError("Application name is invalid")
    libc = ctypes.CDLL(None)
    setter = libc.setprogname
    setter.argtypes = [ctypes.c_char_p]
    setter.restype = None
    _PROGRAM_NAME_BYTES = encoded
    setter(_PROGRAM_NAME_BYTES)
    _set_cocoa_process_name(_PROGRAM_NAME_BYTES)
    return True


def set_macos_application_menu_name(name: str) -> bool:
    """Rename Cocoa's application-menu item after Qt creates the native menu."""
    if platform.system() != "Darwin":
        return False
    encoded = name.encode("utf-8")
    if not encoded or b"\0" in encoded:
        raise ValueError("Application name is invalid")
    ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    selector = objc.sel_registerName
    application = _objc_send(ctypes.c_void_p)(
        objc.objc_getClass(b"NSApplication"), selector(b"sharedApplication")
    )
    main_menu = _objc_send(ctypes.c_void_p)(application, selector(b"mainMenu"))
    if not main_menu:
        return False
    application_item = _objc_send(ctypes.c_void_p, ctypes.c_ulong)(
        main_menu, selector(b"itemAtIndex:"), 0
    )
    if not application_item:
        return False
    cocoa_name = _objc_send(ctypes.c_void_p, ctypes.c_char_p)(
        objc.objc_getClass(b"NSString"),
        selector(b"stringWithUTF8String:"),
        encoded,
    )
    _objc_send(None, ctypes.c_void_p)(
        application_item, selector(b"setTitle:"), cocoa_name
    )
    return True


def macos_cocoa_process_name() -> str | None:
    if platform.system() != "Darwin":
        return None
    ctypes.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    process = _objc_send(ctypes.c_void_p)(
        objc.objc_getClass(b"NSProcessInfo"), objc.sel_registerName(b"processInfo")
    )
    name = _objc_send(ctypes.c_void_p)(
        process, objc.sel_registerName(b"processName")
    )
    value = _objc_send(ctypes.c_char_p)(
        name, objc.sel_registerName(b"UTF8String")
    )
    return value.decode("utf-8")
