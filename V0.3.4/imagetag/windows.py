"""Windows single-instance activation, tray integration."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as W
import os
import threading

MUTEX_NAME = "Local\\Shitu.ImageTagManager.Application"
EVENT_NAME = "Local\\Shitu.ImageTagManager.Activate"


def clip_child_paint(widget):
    """Keep a container's native background from painting over its children."""
    if os.name != "nt":
        return
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowLongW.argtypes = [W.HWND, ctypes.c_int]
    user.GetWindowLongW.restype = W.LONG
    user.SetWindowLongW.argtypes = [W.HWND, ctypes.c_int, W.LONG]
    user.SetWindowLongW.restype = W.LONG
    hwnd = widget.winfo_id()
    style = user.GetWindowLongW(hwnd, -16)
    user.SetWindowLongW(hwnd, -16, style | 0x02000000)  # WS_CLIPCHILDREN


class SingleInstance:
    def __init__(self, suffix="", detect_legacy=True):
        self.mutex = self.event = None
        self.data_mutexes = []
        self.data_identities = set()
        self.already_running = False
        if os.name != "nt":
            return
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, W.BOOL, W.LPCWSTR]
        self.kernel.CreateMutexW.restype = W.HANDLE
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR]
        self.kernel.CreateEventW.restype = W.HANDLE
        self.kernel.SetEvent.argtypes = [W.HANDLE]
        self.kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.mutex = self.kernel.CreateMutexW(None, False, MUTEX_NAME + suffix)
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        self.already_running = ctypes.get_last_error() == 183
        self.event = self.kernel.CreateEventW(None, False, False, EVENT_NAME + suffix)
        if not self.event:
            raise ctypes.WinError(ctypes.get_last_error())
        if self.already_running:
            self.kernel.SetEvent(self.event)
        # v0.2 used a database-specific mutex. Also recognize its visible main window.
        if not self.already_running and detect_legacy:
            callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
            self.user.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
            self.user.ShowWindow.argtypes = [W.HWND, ctypes.c_int]
            self.user.SetForegroundWindow.argtypes = [W.HWND]
            def visit(hwnd, _):
                title = ctypes.create_unicode_buffer(512)
                self.user.GetWindowTextW(hwnd, title, 512)
                if title.value.startswith("拾图 · ImageTagManager "):
                    self.already_running = True
                    self.user.ShowWindow(hwnd, 9)
                    self.user.SetForegroundWindow(hwnd)
                    return False
                return True
            self.user.EnumWindows(callback_type(visit), 0)

    def activation_requested(self):
        return self.event is not None and self.kernel.WaitForSingleObject(self.event, 0) == 0

    def protect_legacy_data(self, data_dir):
        """Hold the v0.2 mutex too, so old EXEs cannot open the active DB."""
        if os.name != "nt":
            return
        import hashlib
        identity = hashlib.sha256(str(data_dir.resolve()).casefold().encode()).hexdigest()[:24]
        if identity in self.data_identities:
            return
        handle = self.kernel.CreateMutexW(None, False, "Local\\ImageTagManager-" + identity)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            self.kernel.CloseHandle(handle)
            raise ValueError("该数据目录已被旧版本拾图打开，请退出旧版本后重试。")
        self.data_mutexes.append(handle)
        self.data_identities.add(identity)

    def close(self):
        for handle in (self.event, self.mutex, *self.data_mutexes):
            if handle:
                self.kernel.CloseHandle(handle)
        self.mutex = self.event = None
        self.data_mutexes.clear()
        self.data_identities.clear()


class Tray:
    """A message-only native integration. All Tk work is queued to its UI thread."""
    def __init__(self, icon_path, events):
        self.icon_path = str(icon_path)
        self.events = events
        self.ready = threading.Event()
        self.ok = False
        self.hwnd = None

    def start(self):
        if os.name != "nt":
            return False
        self.thread = threading.Thread(target=self.run, name="tray", daemon=True)
        self.thread.start()
        self.ready.wait(3)
        return self.ok

    def stop(self):
        if self.hwnd:
            ctypes.windll.user32.PostMessageW(W.HWND(self.hwnd), 0x0010, 0, 0)

    def run(self):
        user = ctypes.WinDLL("user32", use_last_error=True)
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
        class WindowClass(ctypes.Structure):
            _fields_ = [("style", W.UINT), ("proc", callback_type), ("cls_extra", ctypes.c_int),
                        ("wnd_extra", ctypes.c_int), ("instance", W.HINSTANCE), ("icon", W.HICON),
                        ("cursor", W.HANDLE), ("background", W.HBRUSH), ("menu", W.LPCWSTR), ("name", W.LPCWSTR)]
        class NotifyData(ctypes.Structure):
            _fields_ = [("size", W.DWORD), ("hwnd", W.HWND), ("id", W.UINT), ("flags", W.UINT),
                        ("callback", W.UINT), ("icon", W.HICON), ("tip", W.WCHAR * 128),
                        ("state", W.DWORD), ("state_mask", W.DWORD), ("info", W.WCHAR * 256),
                        ("version", W.UINT), ("title", W.WCHAR * 64), ("info_flags", W.DWORD),
                        ("guid", ctypes.c_byte * 16), ("balloon_icon", W.HICON)]
        user.DefWindowProcW.restype = ctypes.c_ssize_t
        user.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        user.CreateWindowExW.restype = W.HWND
        user.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, ctypes.c_void_p]
        user.LoadImageW.restype = W.HANDLE
        user.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT]
        user.CreatePopupMenu.restype = W.HMENU
        user.AppendMenuW.argtypes = [W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR]
        user.TrackPopupMenu.argtypes = [W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, ctypes.c_void_p]
        user.DestroyMenu.argtypes = [W.HMENU]
        user.SetForegroundWindow.argtypes = [W.HWND]
        user.DestroyWindow.argtypes = [W.HWND]
        user.DestroyIcon.argtypes = [W.HICON]
        shell.Shell_NotifyIconW.argtypes = [W.DWORD, ctypes.POINTER(NotifyData)]
        kernel.GetModuleHandleW.restype = W.HMODULE
        taskbar_created = user.RegisterWindowMessageW("TaskbarCreated")
        notify = NotifyData()
        def menu(hwnd):
            point = W.POINT()
            user.GetCursorPos(ctypes.byref(point))
            popup = user.CreatePopupMenu()
            try:
                user.AppendMenuW(popup, 0, 1, "显示主窗口")
                user.AppendMenuW(popup, 0, 2, "退出拾图")
                user.SetForegroundWindow(hwnd)
                choice = user.TrackPopupMenu(popup, 0x0100 | 0x0002, point.x, point.y, 0, hwnd, None)
                if choice:
                    self.events.put(("tray", "show" if choice == 1 else "exit"))
            finally:
                user.DestroyMenu(popup)
        def procedure(hwnd, message, wparam, lparam):
            if message == 0x8001:
                if lparam in (0x0202, 0x0203):
                    self.events.put(("tray", "show"))
                elif lparam == 0x0205:
                    menu(hwnd)
                return 0
            if message == taskbar_created:
                self.ok = bool(shell.Shell_NotifyIconW(0, ctypes.byref(notify)))
                return 0
            if message == 0x0010:
                shell.Shell_NotifyIconW(2, ctypes.byref(notify))
                self.ok = False
                user.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:
                user.PostQuitMessage(0)
                return 0
            return user.DefWindowProcW(hwnd, message, wparam, lparam)
        self.callback = callback_type(procedure)
        name = "ShituTray-" + str(os.getpid())
        instance = kernel.GetModuleHandleW(None)
        window_class = WindowClass(0, self.callback, 0, 0, instance, None, None, None, None, name)
        try:
            if not user.RegisterClassW(ctypes.byref(window_class)):
                return
            self.hwnd = user.CreateWindowExW(0, name, "拾图托盘", 0, 0, 0, 0, 0, None, None, instance, None)
            if not self.hwnd:
                return
            icon = user.LoadImageW(None, self.icon_path, 1, 32, 32, 0x0010)
            notify.size = ctypes.sizeof(NotifyData)
            notify.hwnd, notify.id, notify.flags, notify.callback, notify.icon = self.hwnd, 1, 7, 0x8001, icon
            notify.tip = "拾图 · ImageTagManager — 点击恢复窗口"
            self.ok = bool(shell.Shell_NotifyIconW(0, ctypes.byref(notify)))
            self.ready.set()
            if self.ok:
                msg = W.MSG()
                while user.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    user.TranslateMessage(ctypes.byref(msg))
                    user.DispatchMessageW(ctypes.byref(msg))
            if icon:
                user.DestroyIcon(icon)
        finally:
            self.ok = False
            self.ready.set()
