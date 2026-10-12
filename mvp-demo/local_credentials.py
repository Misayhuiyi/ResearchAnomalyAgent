"""Windows current-user DPAPI; encrypted local credentials are not portable."""
import base64
import ctypes
import os
from ctypes import wintypes


class CredentialError(ValueError):
    pass


def _crypt(data, decrypt=False):
    if os.name != 'nt':
        raise CredentialError('本机加密配置仅支持 Windows，请使用服务进程的密钥环境配置。')

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    try:
        # UI_FORBIDDEN, without LOCAL_MACHINE: bound to the current Windows user.
        if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
            raise CredentialError('本机密钥无法解密，请使用原 Windows 账号或重新配置。')
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.memset(buffer, 0, len(data))
        if target.data:
            ctypes.memset(target.data, 0, target.size)
            kernel.LocalFree(target.data)


def protect_secret(secret):
    if not isinstance(secret, str) or not 1 <= len(secret) <= 1024 or any(
            ord(c) < 33 or ord(c) > 126 for c in secret):
        raise CredentialError('密钥格式无效。')
    return base64.b64encode(_crypt(secret.encode('ascii'))).decode('ascii')


def unprotect_secret(protected):
    try:
        if not isinstance(protected, str) or not 1 <= len(protected) <= 8192:
            raise ValueError()
        return _crypt(base64.b64decode(protected, validate=True), decrypt=True).decode('ascii')
    except (ValueError, OSError, UnicodeError):
        raise CredentialError('本机密钥无法读取，请重新配置。') from None
