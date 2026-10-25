"""Current-Windows-user DPAPI. No plaintext or machine-wide fallback."""
import base64
import ctypes
import os
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _transform(data: bytes, decrypt: bool) -> bytes:
    if os.name != 'nt':
        raise ValueError('密钥保护需要 Windows，请在支持的电脑上设置')
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    release = ctypes.WinDLL('kernel32', use_last_error=True).LocalFree
    release.argtypes, release.restype = [ctypes.c_void_p], ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('无法保护或读取密钥，请在当前 Windows 账户重新保存')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        release(target.data)


def protect(key: str) -> str:
    return base64.b64encode(_transform(key.encode('utf-8'), False)).decode('ascii')


def unprotect(value: str) -> str:
    try:
        return _transform(base64.b64decode(value, validate=True), True).decode('utf-8')
    except (ValueError, UnicodeError) as exc:
        raise ValueError('无法读取保存的密钥，请重新填写') from exc
