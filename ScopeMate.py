# -*- coding: utf-8 -*-
"""ScopeMate 1.0

连接福禄克（Fluke）ScopeMeter 120B 系列的 WiFi 网络，直接从仪器内置 FTP
下载波形 / 录制文件，无需安装 FlukeView 即可导出 CSV 并绘制示波器曲线。

- 仪器连接：FTP 匿名登录（FlukeView 2 同款通道，默认地址 192.168.80.1）
- 文件下载：浏览仪器 FTP 目录，批量下载到本地
- CSV 导出：CSV 直接绘图；.fvr 录制文件以启发式方式解析（实验性）
- 曲线绘制：浅色示波器风格图表，支持十字光标读值、滚轮缩放、拖拽平移

Copyright (c) 2026 陈科雄 <kexiongchen@gmail.com>
SPDX-License-Identifier: MIT
Project: https://github.com/maomaodashetou/ScopeMate
"""

import io
import math
import os
import queue
import re
import socket
import struct
import sys
import threading
import time
import tkinter.font as tkfont
from ftplib import FTP, all_errors
from tkinter import messagebox, ttk

import tkinter as tk

APP_NAME = "ScopeMate"
APP_VERSION = "1.0"
APP_AUTHOR = "陈科雄"
APP_EMAIL = "kexiongchen@gmail.com"
APP_REPO = "https://github.com/maomaodashetou/ScopeMate"

DEFAULT_HOST = "192.168.80.1"   # ScopeMeter WiFi 直连时仪器的默认地址
DEFAULT_PORT = 21
FTP_USER = "anonymous"
FTP_PASS = "scope@local"

# 便携式设计：下载文件与设置都放在软件所在目录（打包后为 exe 旁边），
# 换电脑 / U 盘携带时数据跟着软件走，不写用户目录
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "waveforms")

# 仪器记录文件不存储采样周期；ScopeMeter 记录模式默认 20 ms 一个样本，
# 与 FlukeView 导出 CSV 的时间轴一致
DEFAULT_PERIOD = 0.02

# --------------------------------------------------------------------------- 多语言
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

_TEXTS = {
    "zh": {
        "subtitle": "连接 ScopeMeter 的 WiFi，直接导出波形 CSV 并绘制曲线（无需 FlukeView）",
        "lang_btn": "EN",
        "conn_card": "仪器连接（FTP）",
        "addr": "地址", "port": "端口",
        "connect": "连接仪器", "disconnect": "断开",
        "wifi_hint": "电脑需先接入示波器的 WiFi 网络",
        "remote_card": "示波器文件",
        "up": "返回上级",
        "path_off": "（未连接）",
        "status_off": "未连接仪器",
        "conn_off": "未连接",
        "conn_on": "已连接：%s",
        "refresh": "刷新",
        "dbl_hint": "单击条目即可进入或下载 · 记录下载后自动预览",
        "root_label": "根目录",
        "sub_storage": "存储区 · 单击进入",
        "sub_enter": "文件夹 · 单击进入",
        "sub_record": "记录 · 单击下载并在下方预览",
        "sub_file": "%s · %s",
        "reading_into": "正在读取「%s」...",
        "no_curve_data": "「%s」没有曲线数据",
        "not_connected_row": "未连接仪器，请先连接",
        "folder_start": "正在下载文件夹「%s」...",
        "folder_done_msg": "「%s」已下载（%d 个文件），已存到 %s",
        "busy_now": "正在处理，请稍候 ...",
        "aborted_log": "操作已取消",
        "col_type": "类型",
        "type_folder": "文件夹", "type_wave": "曲线数据",
        "type_cfg": "仪器设置", "type_info": "通道信息",
        "type_env": "包络数据", "type_index": "目录索引",
        "type_meter": "仪表记录",
        "storage_internal": "示波器内部存储",
        "storage_external": "示波器外部存储",
        "curve_label": "曲线 %s",
        "curve_label_named": "曲线 %s · %s",
        "empty_dir": "该目录为空",
        "local_card": "本地分析（保存目录中的文件）",
        "local_hint": "单击文件或文件夹即可在下方预览",
        "export_csv": "导出为 CSV", "open_dir": "打开目录",
        "preview_hint": "单击上方文件夹或文件，在此预览曲线\n滚轮缩放 · 拖拽平移 · 双击复位",
        "col_name": "文件名", "col_size": "大小", "col_mtime": "修改时间",
        "time_axis": "时间 (s)",
        "volt_axis": "电压 (V)",
        "tick_error": "事件处理异常：%s",
        "err_prefix": "出错：%s",
        "disconnected_log": "已断开连接",
        "port_numeric": "端口应为数字",
        "need_host": "请输入仪器 IP 地址",
        "connecting": "正在连接 %s ...",
        "conn_failed": "连接失败：%s\n\n请确认：\n"
                       "1. 电脑已接入示波器的 WiFi 网络；\n"
                       "2. 仪器地址正确（WiFi 直连时通常为 %s）；\n"
                       "3. 仪器 FTP 服务可用。",
        "connected_log": "已连接 %s:%s（匿名 FTP）",
        "connect_first": "请先连接仪器",
        "reading_dir": "正在读取目录 ...",
        "dir_done": "目录读取完成，共 %d 项",
        "receiving": "已接收 %s ...",
        "downloading": "下载中 (%d/%d)：%s",
        "downloaded_log": "已下载：%s",
        "download_done": "下载完成，共 %d 个文件",
        "download_done_msg": "下载完成，共 %d 个文件\n\n已保存到本地分析目录：\n%s",
        "read_dir_failed": "读取目录失败：%s",
        "pick_export": "请先选择要导出的文件夹或记录文件（sr-* / mr-* / .fvr）",
        "parsing": "正在解析 %s ...",
        "exported_log": "已导出：%s",
        "export_done": "CSV 导出完成",
        "no_wave_folder": "该文件夹内没有曲线记录（sr-chA-* / mr-chA-*）",
        "unsupported": "不支持的文件类型",
        "read_wave_failed": "无法读取波形：\n%s\n\n%s",
        "no_traces": "没有可绘制的曲线",
        "dump_suffix": "_结构转储",
        "open_dir_failed": "无法打开目录：%s",
        "empty_file": "文件为空",
        "no_numeric_col": "未找到数值列",
        "only_time_col": "除时间列外没有其他数值列",
        "no_samples": "未能在文件中定位样本数据（格式未知，请用「结构转储」查看）",
    },
    "en": {
        "subtitle": "Connect to ScopeMeter WiFi, export waveform CSV and plot curves - no FlukeView needed",
        "lang_btn": "中文",
        "conn_card": "Device Connection (FTP)",
        "addr": "Host", "port": "Port",
        "connect": "Connect", "disconnect": "Disconnect",
        "wifi_hint": "Connect this PC to the scope's WiFi network first",
        "remote_card": "Scope Files",
        "up": "Up",
        "path_off": "(not connected)",
        "status_off": "Not connected",
        "conn_off": "Disconnected",
        "conn_on": "Connected: %s",
        "refresh": "Refresh",
        "dbl_hint": "Click an item to enter or download · records preview automatically",
        "root_label": "Root",
        "sub_storage": "Storage · click to enter",
        "sub_enter": "Folder · click to enter",
        "sub_record": "Record · click to download & preview",
        "sub_file": "%s · %s",
        "reading_into": "Reading \"%s\" ...",
        "no_curve_data": "No curve data in \"%s\"",
        "not_connected_row": "Not connected - connect to the scope first",
        "folder_start": "Downloading folder \"%s\" ...",
        "folder_done_msg": "\"%s\" downloaded (%d files) -> %s",
        "busy_now": "Busy, please wait ...",
        "aborted_log": "Operation cancelled",
        "col_type": "Type",
        "type_folder": "Folder", "type_wave": "Curve data",
        "type_cfg": "Instrument settings", "type_info": "Channel info",
        "type_env": "Envelope data", "type_index": "Directory index",
        "type_meter": "Meter record",
        "storage_internal": "Scope internal memory",
        "storage_external": "Scope external memory",
        "curve_label": "Curve %s",
        "curve_label_named": "Curve %s · %s",
        "empty_dir": "This folder is empty",
        "local_card": "Local Analysis (files in save folder)",
        "local_hint": "Click a file or folder to preview it below",
        "export_csv": "Export CSV", "open_dir": "Open Folder",
        "preview_hint": "Click a folder or file above to preview its curve\nWheel: zoom · Drag: pan · Double-click: reset",
        "col_name": "Name", "col_size": "Size", "col_mtime": "Modified",
        "time_axis": "Time (s)",
        "volt_axis": "Voltage (V)",
        "tick_error": "Event handler error: %s",
        "err_prefix": "Error: %s",
        "disconnected_log": "Disconnected",
        "port_numeric": "Port must be a number",
        "need_host": "Please enter the instrument IP address",
        "connecting": "Connecting to %s ...",
        "conn_failed": "Connection failed: %s\n\nCheck that:\n"
                       "1. This PC is on the scope's WiFi network;\n"
                       "2. The address is correct (usually %s for direct WiFi);\n"
                       "3. The instrument's FTP service is available.",
        "connected_log": "Connected %s:%s (anonymous FTP)",
        "connect_first": "Connect to the instrument first",
        "reading_dir": "Reading directory ...",
        "dir_done": "Directory loaded, %d items",
        "receiving": "Received %s ...",
        "downloading": "Downloading (%d/%d): %s",
        "downloaded_log": "Downloaded: %s",
        "download_done": "Download finished, %d files",
        "download_done_msg": "Download finished, %d files\n\nSaved to the local analysis folder:\n%s",
        "read_dir_failed": "Failed to read directory: %s",
        "pick_export": "Select a folder or record file to export first (sr-* / mr-* / .fvr)",
        "parsing": "Parsing %s ...",
        "exported_log": "Exported: %s",
        "export_done": "CSV export finished",
        "no_wave_folder": "No waveform record (sr-chA-* / mr-chA-*) in this folder",
        "unsupported": "Unsupported file type",
        "read_wave_failed": "Cannot read waveform:\n%s\n\n%s",
        "no_traces": "No curves to plot",
        "dump_suffix": "_dump",
        "open_dir_failed": "Cannot open folder: %s",
        "empty_file": "File is empty",
        "no_numeric_col": "No numeric column found",
        "only_time_col": "No numeric columns besides the time column",
        "no_samples": "Could not locate sample data (unknown format; use Dump Structure to inspect)",
    },
}

_LANG = "zh"


def _load_lang():
    global _LANG
    try:
        import json
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fp:
            _LANG = "en" if json.load(fp).get("lang") == "en" else "zh"
    except Exception:
        pass


def _save_lang():
    try:
        import json
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fp:
            json.dump({"lang": _LANG}, fp)
    except Exception:
        pass


_load_lang()


def tr(key):
    """取当前语言的文案模板；缺键时回退中文，再回退键名。"""
    text = _TEXTS.get(_LANG, _TEXTS["zh"])
    return text.get(key) or _TEXTS["zh"].get(key) or key


def _nat_key(text):
    """自然排序键：数字段按数值比较（1, 2, ... 10，而不是 1, 10, 2）。"""
    return [(1, int(p), "") if p.isdigit() else (0, 0, p.lower())
            for p in re.split(r"(\d+)", text)]


def remote_kind_key(name, is_dir):
    """按文件名推断仪器 FTP 条目的类型标注（文案键）；非波形/配置返回 None。"""
    if is_dir:
        return "type_folder"
    if _is_scope_record(name):
        return "type_wave"
    if _is_meter_record(name):
        return "type_meter"
    low = os.path.basename(name).lower()
    if low.endswith("srinfo") or low.endswith("mrinfo"):
        return "type_info"
    if low.endswith("srallin1") or low.endswith("mrallin1"):
        return "type_env"
    if low.endswith(".cfg"):
        return "type_cfg"
    if low.endswith("index.txt"):
        return "type_index"
    return None


def remote_display_name(parent_path, name, is_dir, index_names=None):
    """仪器文件列表的显示名：根目录两盘用中文名，曲线槽位用「曲线 N」。

    真实文件名仍存在 iid 里，显示名只影响界面文字，切换语言时按需重算。
    """
    if not is_dir:
        return name
    low = name.lower()
    parent = (parent_path or "").lower()
    if not parent:
        if low == "internal":
            return tr("storage_internal")
        if low == "external":
            return tr("storage_external")
        return name
    if parent in ("internal", "external") and name.isdigit():
        idx = int(name)
        label = tr("curve_label") % name
        names = index_names or []
        if 1 <= idx <= len(names):
            title = names[idx - 1].strip()
            if title and title.lower() != "default":
                # 仪器里给这条记录起过名字，就用「曲线 N · 名字」
                label = tr("curve_label_named") % (name, title)
        return label
    return name


def local_display_name(name):
    """本地文件夹名的显示别名：internal_3 → 示波器内部存储 · 曲线 3。"""
    m = re.match(r"^(internal|external)_(.+?)(?:\((\d+)\))?$", name,
                 re.IGNORECASE)
    if not m:
        return name
    storage = tr("storage_internal" if m.group(1).lower() == "internal"
                 else "storage_external")
    slot = m.group(2)
    slot = tr("curve_label") % slot if slot.isdigit() else slot
    if m.group(3):
        slot = "%s (%s)" % (slot, m.group(3))
    return "%s · %s" % (storage, slot)


def record_dir_name(remote_dir):
    """仪器目录 → 本地文件夹名；曲线槽位带上存储前缀，避免内外存储撞名。"""
    parts = [p for p in remote_dir.split("/") if p]
    if len(parts) >= 2 and parts[0].lower() in ("internal", "external"):
        return _safe_name(parts[0]) + "_" + _safe_name(parts[1])
    return _safe_name(parts[-1]) if parts else "record"


def read_dir_index(ftp, path, items):
    """读取目录里的 index.txt（每行一个记录名），取不到时返回空列表。"""
    for name, size, is_dir, _mt in items:
        if is_dir or name.lower() != "index.txt":
            continue
        try:
            buf = io.BytesIO()
            ftp.cwd("/")
            ftp.retrbinary("RETR " + (path + "/" + name if path else name),
                           buf.write)
            text = buf.getvalue().decode("utf-8", "replace")
            return [ln.strip() for ln in text.splitlines()]
        except Exception:
            return []
    return []

# --------------------------------------------------------------------------- 主题
def _safe_name(name):
    """把仪器目录名转成合法的 Windows 文件夹名。"""
    for ch in '<>:"\\|?*':
        name = name.replace(ch, "_")
    return name.strip() or "folder"


def _previewable(name):
    ext = os.path.splitext(name)[1].lower()
    return (ext in (".csv", ".fvr") or _is_scope_record(name)
            or _is_meter_record(name))


PAGE_BG = "#F5F5F7"
CARD_BG = "#FFFFFF"
BORDER = "#E5E5EA"
FIELD_BG = "#F2F2F7"
BTN_BG = "#FFFFFF"
BTN_LINE = "#D8D8DE"
BTN_HOVER = "#F7F7F9"
BTN_PRESS = "#EDEDF0"
BTN_DISABLED_LINE = "#EEEEF1"
TEXT_MAIN = "#1D1D1F"
TEXT_MUTED = "#86868B"
TEXT_DISABLED = "#C7C7CC"
GRID_LINE = "#ECECF0"
CROSS_LINE = "#7F7F7F"
SELECT_BG = "#E8F1FC"

# 曲线与坐标轴用 Origin 风格的深色系：白底、黑框、向内刻度、细线
AXIS_COLOR = "#262626"
AXIS_TEXT = "#1A1A1A"
GRID_MAJOR = "#EFEFF2"
LEGEND_LINE = "#C0C0C0"

TRACE_COLORS = ("#C00000", "#0050A0", "#1B5E20", "#6A1B9A",
                "#8D6E00", "#00695C", "#4E342E", "#7A7A7A")

FONT_TITLE = ("Microsoft YaHei", 17, "bold")
FONT_UI = ("Microsoft YaHei", 10)
FONT_SMALL = ("Microsoft YaHei", 9)
FONT_MONO = ("Consolas", 9)
FONT_READOUT = ("Consolas", 10)
FONT_TICK = ("Arial", 9)


def resource_dir():
    """资源目录：开发时在脚本同级 assets，PyInstaller 打包后位于解包目录。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets")


def enable_dpi_awareness():
    """高分屏下保持文字清晰。"""
    if os.name != "nt":
        return
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            from ctypes import windll

            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def human_size(n):
    units = ["B", "KB", "MB", "GB"]
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return "%d %s" % (value, unit)
            return "%.1f %s" % (value, unit)
        value /= 1024.0
    return "%.1f GB" % value


def time_str(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def unique_path(path):
    """路径被占用时追加序号，避免覆盖已有文件。"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = "%s(%d)%s" % (base, i, ext)
        if not os.path.exists(cand):
            return cand
        i += 1


# --------------------------------------------------------------------------- 圆角控件
def _rounded(canvas, x1, y1, x2, y2, r, **kw):
    """在 Canvas 上画圆角矩形。"""
    steps = 8
    pts = []
    corners = (
        (x1 + r, y1 + r, 180, 270),
        (x2 - r, y1 + r, 270, 360),
        (x2 - r, y2 - r, 0, 90),
        (x1 + r, y2 - r, 90, 180),
    )
    for cx, cy, a0, a1 in corners:
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / float(steps))
            pts.extend([cx + math.cos(a) * r, cy + math.sin(a) * r])
    return canvas.create_polygon(pts, smooth=False, **kw)


class RoundedButton(tk.Canvas):
    """圆角按钮：白底 + 浅色描边，悬停变浅灰。"""

    def __init__(self, parent, text, command, height=32, radius=8):
        self._font = tkfont.Font(font=FONT_UI)
        width = self._font.measure(text) + 36
        super().__init__(
            parent, width=width, height=height, bg=parent.cget("bg"),
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self._text = text
        self._cmd = command
        self._radius = radius
        self._enabled = True
        self._hover = False
        self._pressed = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _draw(self):
        self.delete("all")
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        if not self._enabled:
            fill, outline, color = "#FAFAFB", BTN_DISABLED_LINE, TEXT_DISABLED
        elif self._pressed:
            fill, outline, color = BTN_PRESS, BTN_LINE, TEXT_MAIN
        elif self._hover:
            fill, outline, color = BTN_HOVER, BTN_LINE, TEXT_MAIN
        else:
            fill, outline, color = BTN_BG, BTN_LINE, TEXT_MAIN
        _rounded(self, 1, 1, w - 1, h - 1, self._radius,
                 fill=fill, outline=outline, width=1)
        self.create_text(w / 2.0, h / 2.0, text=self._text,
                         font=self._font, fill=color)

    def set_text(self, text):
        self._text = text
        # 中英切换后文字长度不同，宽度按新文本重算，避免被裁剪
        self.configure(width=self._font.measure(text) + 36)
        self._draw()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _on_enter(self, _=None):
        if self._enabled:
            self._hover = True
            self._draw()

    def _on_leave(self, _=None):
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _=None):
        if self._enabled:
            self._pressed = True
            self._draw()

    def _on_release(self, _=None):
        if self._enabled and self._pressed:
            self._pressed = False
            self._draw()
            self._cmd()


class RoundedEntry(tk.Canvas):
    """圆角输入框：浅灰底。"""

    def __init__(self, parent, textvariable, font, height=34, radius=8,
                 readonly=False, width=120):
        super().__init__(
            parent, width=width, height=height, bg=parent.cget("bg"),
            highlightthickness=0, bd=0,
        )
        self._radius = radius
        self._entry = tk.Entry(
            self, textvariable=textvariable, font=font, bd=0, relief="flat",
            bg=FIELD_BG, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
            readonlybackground=FIELD_BG, disabledbackground=FIELD_BG,
            disabledforeground=TEXT_MUTED, highlightthickness=0,
        )
        if readonly:
            self._entry.configure(state="readonly")
        self._win = self.create_window(12, height / 2.0, anchor="w",
                                       window=self._entry)
        self.bind("<Configure>", self._layout)
        self.bind("<Button-1>", lambda e: self._entry.focus_set())

    def _layout(self, event):
        self.delete("bg")
        _rounded(self, 0, 0, event.width, event.height, self._radius,
                 fill=FIELD_BG, outline="", tags="bg")
        self.tag_lower("bg")
        self.coords(self._win, 12, event.height / 2.0)
        self.itemconfigure(self._win, width=max(20, event.width - 24))

    def set_enabled(self, enabled):
        self._entry.configure(state="normal" if enabled else "disabled")


class Card(tk.Canvas):
    """白色圆角卡片，内容放在 inner 里，高度随内容自适应。"""

    def __init__(self, parent, padding=18, radius=14):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self._padding = padding
        self._radius = radius
        self.inner = tk.Frame(self, bg=CARD_BG)
        self._win = self.create_window(padding, padding, anchor="nw",
                                       window=self.inner)
        self.inner.bind("<Configure>", self._on_inner)
        self.bind("<Configure>", self._on_canvas)

    def _on_inner(self, _=None):
        height = self.inner.winfo_reqheight() + 2 * self._padding
        if int(self.cget("height")) != height:
            self.configure(height=height)

    def _on_canvas(self, event):
        self.delete("bg")
        _rounded(self, 1, 1, event.width - 1, event.height - 1, self._radius,
                 fill=CARD_BG, outline=BORDER, width=1, tags="bg")
        self.tag_lower("bg")
        self.itemconfigure(self._win, width=max(60, event.width - 2 * self._padding))


class SlimScrollbar(tk.Canvas):
    """细圆角滚动条：无箭头、无凹槽，悬停加深，和浅色卡片风格一致。"""

    WIDTH = 10
    THUMB = 6

    def __init__(self, parent, command, bg=CARD_BG):
        super().__init__(parent, width=self.WIDTH, height=1, bg=bg,
                         highlightthickness=0, bd=0)
        self._command = command          # 目标 Canvas 的 yview
        self._first, self._last = 0.0, 1.0
        self._drag = None
        self._hover = False
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def set(self, first, last):
        self._first, self._last = float(first), float(last)
        self._redraw()

    def _span(self):
        h = max(1, self.winfo_height())
        y0, y1 = self._first * h, self._last * h
        if y1 - y0 < 26:                 # 内容很长时给滑块最小高度，便于抓取
            mid = (y0 + y1) / 2.0
            y0 = max(0.0, mid - 13.0)
            y1 = min(float(h), y0 + 26.0)
        return y0, y1

    def _redraw(self):
        self.delete("all")
        if self._first <= 0.0 and self._last >= 1.0:
            return                       # 不需要滚动时什么都不画
        y0, y1 = self._span()
        x = (self.WIDTH - self.THUMB) / 2.0
        _rounded(self, x, y0 + 2, x + self.THUMB, y1 - 2, self.THUMB / 2.0,
                 fill="#A8A8B0" if self._hover else "#C7C7CE", outline="")

    def _on_enter(self, _=None):
        self._hover = True
        self._redraw()

    def _on_leave(self, _=None):
        self._hover = False
        self._redraw()

    def _on_press(self, event):
        y0, y1 = self._span()
        if y0 <= event.y <= y1:
            self._drag = (event.y, self._first)
        else:
            self._command("scroll", 1 if event.y > y1 else -1, "pages")

    def _on_drag(self, event):
        if not self._drag:
            return
        h = max(1, self.winfo_height())
        start_y, start_first = self._drag
        first = start_first + (event.y - start_y) / float(h)
        first = max(0.0, min(first, 1.0 - (self._last - self._first)))
        self._command("moveto", first)


class ScrollArea(tk.Frame):
    """固定高度的可滚动容器。"""

    def __init__(self, parent, height=168, bg=CARD_BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0,
                                height=height)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.bar = SlimScrollbar(self, command=self.canvas.yview, bg=bg)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y", padx=(2, 0))
        self.inner.bind("<Configure>", self._sync)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<MouseWheel>", self._wheel)

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self._win, width=event.width)
        self._sync()

    def _sync(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._wheel)
        for child in widget.winfo_children():
            self.bind_wheel(child)

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)


class EntryRow(tk.Frame):
    """可点击的一行：主标题 + 说明 + 右侧箭头，用于「存储区 / 曲线」选择。"""

    def __init__(self, parent, title, subtitle, command, chevron="›"):
        super().__init__(parent, bg=CARD_BG, cursor="hand2")
        self._command = command
        self._title = tk.Label(self, text=title, font=FONT_UI, bg=CARD_BG,
                               fg=TEXT_MAIN, anchor="w", cursor="hand2")
        self._title.pack(side="left", padx=(10, 12), pady=7)
        self._sub = tk.Label(self, text=subtitle, font=FONT_SMALL, bg=CARD_BG,
                             fg=TEXT_MUTED, anchor="w", cursor="hand2")
        self._sub.pack(side="left")
        self._chev = tk.Label(self, text=chevron, font=FONT_UI, bg=CARD_BG,
                              fg=TEXT_DISABLED, cursor="hand2")
        self._chev.pack(side="right", padx=(0, 12))
        for widget in (self, self._title, self._sub, self._chev):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _paint(self, color):
        for widget in (self, self._title, self._sub, self._chev):
            widget.configure(bg=color)

    def _on_enter(self, _=None):
        self._paint(SELECT_BG)

    def _on_leave(self, _=None):
        self._paint(CARD_BG)

    def _on_click(self, _=None):
        self._command()

    def set_muted(self):
        """只作提示信息时使用：去掉箭头与手型光标。"""
        self._chev.pack_forget()
        self._title.configure(fg=TEXT_MUTED)
        for widget in (self, self._title, self._sub):
            widget.configure(cursor="arrow")

    def set_note(self, text):
        """把副标题换成提示文字（如「该曲线没有数据」）。"""
        self._sub.configure(text=text, fg="#C7472E")


# --------------------------------------------------------------------------- FTP
def ftp_connect(host, port=DEFAULT_PORT, timeout=6.0):
    """匿名登录仪器 FTP，返回 FTP 对象；失败抛出带原因的异常。"""
    ftp = FTP()
    ftp.connect(host, port, timeout=timeout)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.set_pasv(True)
    try:
        ftp.voidcmd("TYPE I")
    except all_errors:
        pass
    return ftp


def ftp_list(ftp, path=""):
    """列出目录内容（路径相对 FTP 根目录）。

    返回 [(名称, 大小或None, 是否目录, 修改时间或None)]，目录在前。
    """
    ftp.cwd("/")
    if path:
        ftp.cwd(path)
    base = "/" + path if path else "/"
    names = []
    ftp.retrlines("NLST", names.append)
    items = []
    for name in names:
        if name in (".", ".."):
            continue
        size = None
        is_dir = False
        mtime = None
        try:
            size = ftp.size(name)
        except all_errors:
            size = None
        if size is None:
            # SIZE 失败：尝试进入目录来判断是否为文件夹
            try:
                ftp.cwd(name)
                is_dir = True
                ftp.cwd(base)
            except all_errors:
                is_dir = False
        try:
            resp = ftp.voidcmd("MDTM " + name)
            if resp[:3] == "213":
                raw = resp[4:].strip()
                if len(raw) >= 12:
                    mtime = "%s-%s-%s %s:%s" % (
                        raw[0:4], raw[4:6], raw[6:8], raw[8:10], raw[10:12])
        except all_errors:
            mtime = None
        items.append((name, size, is_dir, mtime))
    items.sort(key=lambda it: (not it[2], _nat_key(it[0])))
    return items


def ftp_download(ftp, remote_name, local_path, progress=None, chunk=32 * 1024):
    """下载单个文件（二进制模式，路径相对 FTP 根目录），progress(已传字节)。"""
    ftp.cwd("/")
    with open(local_path, "wb") as fp:

        def cb(block):
            fp.write(block)
            if progress:
                progress(fp.tell())

        ftp.retrbinary("RETR " + remote_name, cb, blocksize=chunk)


# --------------------------------------------------------------------------- 波形模型
class Trace(object):
    """一条曲线：name 显示名，unit 纵轴单位，times/values 等长序列。"""

    def __init__(self, name, unit, times, values, color):
        self.name = name
        self.unit = unit
        self.times = times
        self.values = values
        self.color = color


_UNIT_HINTS = {
    "V": "V", "mV": "mV", "A": "A", "mA": "mA", "s": "s", "ms": "ms",
    "Hz": "Hz", "deg": "°", "ohm": "Ω",
}


def _col_label(raw):
    """把 CSV 列名整理成 (显示名, 单位)：ch_a_V -> ch_a / V。"""
    raw = raw.strip()
    unit = ""
    parts = raw.rsplit("_", 1)
    if len(parts) == 2 and 0 < len(parts[1]) <= 3 and parts[1] in _UNIT_HINTS:
        unit = _UNIT_HINTS[parts[1]]
        raw = parts[0]
    return (raw or "曲线"), unit


def load_traces_from_csv(path):
    """读取 CSV（支持 BOM / 逗号 / 分号 / Tab）。

    第一列数值视为时间轴，其余数值列各成一条曲线。返回 Trace 列表；
    解析失败抛 ValueError。
    """
    with open(path, "rb") as fp:
        raw = fp.read()
    if raw[:3] == b"\xef\xbb\xbf":
        text = raw[3:].decode("utf-8", "replace")
    else:
        text = raw.decode("utf-8", "replace")
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines:
        raise ValueError(tr("empty_file"))
    delim = ","
    for cand in (",", ";", "\t"):
        if cand in lines[0]:
            delim = cand
            break
    header = [c.strip().lstrip("\ufeff") for c in lines[0].split(delim)]

    def is_number(tok):
        try:
            float(tok)
            return True
        except ValueError:
            return False

    first = lines[1].split(delim) if len(lines) > 1 else []
    numeric_cols = [i for i in range(min(len(header), len(first)))
                    if i < len(first) and is_number(first[i].strip())]
    if not numeric_cols:
        raise ValueError(tr("no_numeric_col"))
    cols = dict((i, []) for i in numeric_cols)
    for ln in lines[1:]:
        cells = ln.split(delim)
        for i in numeric_cols:
            if i < len(cells):
                try:
                    cols[i].append(float(cells[i].strip()))
                except ValueError:
                    cols[i].append(float("nan"))
    times = cols[numeric_cols[0]]
    traces = []
    for n, i in enumerate(numeric_cols[1:]):
        disp, unit = _col_label(header[i] if i < len(header) else "ch%d" % n)
        traces.append(Trace(
            disp, unit, times, cols[i], TRACE_COLORS[n % len(TRACE_COLORS)]))
    if not traces:
        raise ValueError(tr("only_time_col"))
    return traces


# --------------------------------------------------------------------------- FVR 解析（实验性）
class FvrError(Exception):
    pass


def _finite(v):
    """排除 denormal（二进制头/整数被误读成浮点时的典型值）。"""
    return v == 0.0 or (1e-35 <= abs(v) < 1e7 and math.isfinite(v))


def _int16_plausible(data, off, cnt, probe=2000):
    """int16 块需通过相邻样本差值中位数检验（真实波形平滑，随机字节差异巨大）。"""
    n = min(cnt - 1, probe)
    if n <= 0:
        return False
    vals = struct.unpack_from("<%dh" % (n + 1), data, off)
    deltas = sorted(abs(vals[k + 1] - vals[k]) for k in range(n))
    return deltas[n // 2] < 8192


def _scan_numeric_blocks(data, fmt, step, min_pts=64):
    """扫描二进制数据中连续可解码的数值块，返回 [(字节偏移, 点数)]。

    按 step 个相位分别扫描（块起点未必对齐到 4/2 字节边界），
    再跨相位去重（长块优先，丢弃与已保留块重叠的碎片）。
    """
    unpack = struct.Struct(fmt).unpack_from
    n = len(data)
    blocks = []
    for phase in range(step):
        run_start = None
        i = phase
        while i + step <= n:
            try:
                ok = _finite(unpack(data, i)[0])
            except struct.error:
                ok = False
            if ok:
                if run_start is None:
                    run_start = i
                i += step
            else:
                if run_start is not None and (i - run_start) // step >= min_pts:
                    blocks.append((run_start, (i - run_start) // step))
                run_start = None
                i += step
        if run_start is not None and (i - run_start) // step >= min_pts:
            blocks.append((run_start, (i - run_start) // step))
    kept = []
    for off, cnt in sorted(blocks, key=lambda b: -b[1]):
        lo, hi = off, off + cnt * step
        if all(hi <= k_off or lo >= k_hi for k_off, k_hi in
               ((b[0], b[0] + b[1] * step) for b in kept)):
            kept.append((off, cnt))
    kept.sort()
    return kept


def parse_fvr(path, sample_period=0.02):
    """实验性 .fvr 解析：在文件中挖掘连续 float32 / int16 样本块。

    FlukeView 2 日志显示 .fvr 内部为 admin + samples（TraceDataBlock）结构，
    但块布局无公开文档，此处以启发式扫描还原样本值。返回 (块列表, 周期)，
    每个块为 float 列表。扫描失败抛 FvrError。
    """
    with open(path, "rb") as fp:
        data = fp.read()
    if not data:
        raise FvrError(tr("empty_file"))
    f_blocks = _scan_numeric_blocks(data, "<f", 4)
    i_blocks = [(off, cnt) for off, cnt in _scan_numeric_blocks(data, "<h", 2)
                if _int16_plausible(data, off, cnt)]
    if sum(b[1] for b in f_blocks) >= sum(b[1] for b in i_blocks) and f_blocks:
        chosen, fmt, step = f_blocks, "<f", 4
    elif i_blocks:
        chosen, fmt, step = i_blocks, "<h", 2
    else:
        raise FvrError(tr("no_samples"))
    unpack = struct.Struct(fmt).unpack_from
    out = []
    for off, count in chosen:
        out.append([unpack(data, off + k * step)[0] for k in range(count)])
    return out, float(sample_period)


def fvr_to_csv(path, out_dir, sample_period=0.02):
    """把 .fvr 导出为与 FlukeView 相同风格的 CSV：time_s,ch_a_V,ch_b_V..."""
    blocks, period = parse_fvr(path, sample_period)
    base = os.path.splitext(os.path.basename(path))[0]
    letters = "abcdefgh"
    out_path = unique_path(os.path.join(out_dir, base + ".csv"))
    n = max(len(b) for b in blocks)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write("time_s," + ",".join(
            "ch_%s_V" % letters[i] if i < len(letters) else "ch%d" % i
            for i in range(len(blocks))) + "\n")
        for row in range(n):
            cells = ["%.6f" % (row * period)]
            for b in blocks:
                cells.append("%.4f" % b[row] if row < len(b) else "")
            fp.write(",".join(cells) + "\n")
    return [out_path]


def fvr_structure_dump(path, out_dir):
    """把 .fvr 的结构线索转储为 txt（hex 头部 + 检测到的数据块），用于分析格式。"""
    with open(path, "rb") as fp:
        data = fp.read()
    base = os.path.splitext(os.path.basename(path))[0]
    out = unique_path(os.path.join(out_dir, base + tr("dump_suffix") + ".txt"))
    with open(out, "w", encoding="utf-8") as fp:
        fp.write("文件: %s\n大小: %d 字节\n\n-- 头部 512 字节 --\n" % (path, len(data)))
        head = data[:512]
        for row in range(0, len(head), 16):
            seg = head[row:row + 16]
            hexs = " ".join("%02X" % b for b in seg)
            text = "".join(chr(b) if 32 <= b < 127 else "." for b in seg)
            fp.write("%08X  %-47s  %s\n" % (row, hexs, text))
        fp.write("\n-- 检测到的 float32 块 --\n")
        for off, cnt in _scan_numeric_blocks(data, "<f", 4):
            vals = struct.unpack_from("<%df" % min(cnt, 8), data, off)
            fp.write("offset=0x%X(%d) points=%d head=%s\n"
                     % (off, off, cnt, ["%.5g" % v for v in vals]))
        fp.write("\n-- 检测到的 int16 块 --\n")
        for off, cnt in _scan_numeric_blocks(data, "<h", 2):
            fp.write("offset=0x%X(%d) points=%d\n" % (off, off, cnt))
    return out


# ------------------------------------------------------------------ 仪器原生记录文件
# 实测（Fluke 124B，FTP 下载 sr-chA-* 与 FlukeView 导出的 CSV 逐点比对，残差为 0）：
#   * sr-chA-* 文件为小端 int16 原始采样流，无头部，A/B 两路按 [A0,B0,A1,B1,...] 交织；
#     即使示波器屏幕只显示 A，交织流里的第二路也真实存在（B 输入悬空时拾取串扰/干扰）。
#   * 电压 = 原始值 × 0.0625 - 47.5 V。0.0625 V/LSB 与 FlukeView 的 YResolution 一致，
#     且不同档位下不变（前级增益固定，V/div 只是显示层概念）；零点 760 LSB 出现在
#     setup.cfg / chA-srInfo 的标定块中（f8 02 00 00）。
SCOPE_LSB_V = 0.0625
SCOPE_ZERO_LSB = 760

# 采样间隔的来源：记录文件本身不含时间轴，但同目录的 chA-srInfo 里保存了
# 记录的起止时刻（@1152 起始秒 + @1156 毫秒，@1168 结束秒 + @1172 毫秒）。
# 间隔 = (结束 - 起始) / (采样点数 - 1)，让首尾两个采样点正好落在起止时刻上；
# 直接使用实测值，不做档位归整（两条真实记录分别为 20.010 ms / 20.166 ms，
# 差异是记录本身的真实差异，归整会把 0.7% 的差别抹平）。
SR_INFO_FILE = "chA-srInfo"
SR_INFO_START = 1152
SR_INFO_START_MS = 1156
SR_INFO_END = 1168
SR_INFO_END_MS = 1172
_INFO_MIN_LEN = 1176
_UNIX_Y2000 = 946684800          # 仪器时钟基准（2000-01-01）
_UNIX_Y2100 = 4102444800


def read_record_span(path):
    """读取记录的总时长（秒）：来自同目录 chA-srInfo 的起止时刻。"""
    info = os.path.join(os.path.dirname(os.path.abspath(path)), SR_INFO_FILE)
    try:
        with open(info, "rb") as fp:
            data = fp.read(_INFO_MIN_LEN)
    except OSError:
        return None
    if len(data) < _INFO_MIN_LEN:
        return None
    start_s, start_ms = struct.unpack_from("<ii", data, SR_INFO_START)
    end_s, end_ms = struct.unpack_from("<ii", data, SR_INFO_END)
    start = start_s + start_ms / 1000.0
    end = end_s + end_ms / 1000.0
    if not (_UNIX_Y2000 < start < end < _UNIX_Y2100):
        return None
    return end - start


def scope_sample_period(path, n):
    """示波器记录的采样间隔（秒）：总时长 / (点数 - 1)，无元数据时用默认 20 ms。"""
    span = read_record_span(path) if n > 1 else None
    if span and span > 0:
        return span / (n - 1)
    return DEFAULT_PERIOD


def _is_scope_record(name):
    """判断是否仪器原生波形记录文件（sr-chA-*，无扩展名）。"""
    base = os.path.basename(name)
    return base.startswith("sr-") and not base.lower().endswith(
        (".csv", ".fvr", ".cfg", ".txt"))


def _is_meter_record(name):
    """判断是否仪器原生仪表记录文件（mr-chA-*，无扩展名）。

    仪表记录为 68 字节块结构（序号 / 时间戳 / min-max 类统计），
    与示波器记录的裸 int16 采样流完全不同。
    """
    base = os.path.basename(name)
    return base.startswith("mr-") and not base.lower().endswith(
        (".csv", ".fvr", ".cfg", ".txt"))


def parse_scope_record(path):
    """解析仪器原生 sr-chA-* 记录文件。

    返回 [(通道名, 电压值列表), ...]，按 A/B 拆交织并换算为伏特。
    """
    with open(path, "rb") as fp:
        data = fp.read()
    if not data:
        raise ValueError(tr("empty_file"))
    if len(data) % 2:
        data = data[:-1]
    n = len(data) // 2
    raw = struct.unpack("<%dh" % n, data)
    k = SCOPE_LSB_V
    z = SCOPE_ZERO_LSB
    out = []
    for ch in range(2):
        vals = [(raw[i] - z) * k for i in range(ch, n, 2)]
        if vals:
            out.append(("ch_a" if ch == 0 else "ch_b", vals))
    return out


def scope_record_to_csv(path, out_dir, sample_period=None):
    """把仪器 sr-chA-* 记录文件导出为 time_s,ch_a_V,ch_b_V 的 CSV。

    采样间隔优先由 chA-srInfo 的起止时刻推算，取不到时才用传入值/默认值。
    """
    chans = parse_scope_record(path)
    n = max(len(v) for _, v in chans)
    period = scope_sample_period(path, n) if sample_period is None \
        else sample_period
    base = os.path.splitext(os.path.basename(path))[0]
    out_path = unique_path(os.path.join(out_dir, base + ".csv"))
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write("time_s," + ",".join("%s_V" % name for name, _ in chans) + "\n")
        for row in range(n):
            cells = ["%.6f" % (row * period)]
            for _, vals in chans:
                cells.append("%.4f" % vals[row] if row < len(vals) else "")
            fp.write(",".join(cells) + "\n")
    return [out_path]


# 仪表记录（mr-*）换算参数：与上位机导出的数据逐点比对验证过
METER_Y_RES = 0.0001      # 1 LSB = 0.0001 V
METER_WINDOW_S = 0.5      # 每个统计单元代表 0.5 s 时间窗


def parse_meter_record(path):
    """解析仪表记录（mr-chA-*）。

    文件结构：80 字节头 + N 个 72 字节统计单元（4B 序号 + 64B 数据，
    末单元可能截断）。数据区 16 个 int32 中 [6]=max、[8]=avg、[11]=min
    （原始计数），电压 = raw × 0.0001；序号 seq 为统计窗口号，
    时间 = seq × 0.5 s。

    返回 {"min": [(t, V), ...], "avg": [...], "max": [...]}。
    """
    with open(path, "rb") as fp:
        data = fp.read()
    stats = {"min": [], "avg": [], "max": []}
    off = 80
    while off + 68 <= len(data):
        seq = struct.unpack_from("<i", data, off)[0]
        d = struct.unpack_from("<16i", data, off + 4)
        t = seq * METER_WINDOW_S
        stats["max"].append((t, d[6] * METER_Y_RES))
        stats["avg"].append((t, d[8] * METER_Y_RES))
        stats["min"].append((t, d[11] * METER_Y_RES))
        off += 72
    return stats


def meter_record_to_csv(path, out_dir):
    """把仪表记录导出为换算电压后的 CSV（time_s, min, avg, max）。"""
    stats = parse_meter_record(path)
    base = os.path.splitext(os.path.basename(path))[0]
    out_path = unique_path(os.path.join(out_dir, base + ".csv"))
    n = len(stats["avg"])
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fp:
        import csv

        writer = csv.writer(fp)
        writer.writerow(["time_s", "meter_min_V", "meter_avg_V",
                         "meter_max_V"])
        for i in range(n):
            writer.writerow([
                "%.3f" % stats["avg"][i][0],
                "%.6f" % stats["min"][i][1],
                "%.6f" % stats["avg"][i][1],
                "%.6f" % stats["max"][i][1],
            ])
    return [out_path]


# --------------------------------------------------------------------------- 绘图窗口
def _nice_step(span, target):
    """在 1/2/5×10^n 里挑一个接近 target 的刻度步长。"""
    if span <= 0:
        return 1.0
    raw = span / float(max(1, target))
    mag = 10.0 ** math.floor(math.log10(raw))
    for mult in (1.0, 2.0, 5.0, 10.0):
        if raw <= mult * mag * 1.0001:
            return mult * mag
    return 10.0 * mag


def _fmt_tick(v, step):
    if step <= 0:
        step = 1.0
    digits = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    if abs(v) >= 1e5 or (abs(v) < 1e-4 and v != 0):
        return "%.2e" % v
    return "%.*f" % (digits, v)


class PlotPanel(tk.Frame):
    """嵌入式曲线面板：Origin 风格白底黑框 + 向内刻度 + 图例框 + 十字光标。"""

    PAD_L, PAD_R, PAD_T, PAD_B = 78, 20, 12, 46

    def __init__(self, master):
        super().__init__(master, bg=CARD_BG)
        self.traces = []
        self.x0 = 0.0
        self.x1 = 1.0
        self._hover = None
        self._drag_x = None
        self.status = tk.StringVar(value="")

        bar = tk.Frame(self, bg=CARD_BG)
        bar.pack(fill="x", padx=14, pady=(8, 0))
        self.title_lbl = tk.Label(bar, text="", font=FONT_SMALL, bg=CARD_BG,
                                  fg=TEXT_MUTED)
        self.title_lbl.pack(side="left")
        tk.Label(bar, textvariable=self.status, font=FONT_READOUT, bg=CARD_BG,
                 fg=TEXT_MAIN).pack(side="right")

        self.canvas = tk.Canvas(self, bg=CARD_BG, highlightthickness=0, bd=0,
                                height=216)
        self.canvas.pack(fill="x", padx=14, pady=(0, 10))
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Motion>", self._on_move)
        self.canvas.bind("<Leave>", lambda e: self._clear_cross())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_x", None))
        self.canvas.bind("<Double-Button-1>", lambda e: self._reset())
        self.after(60, self.redraw)

    def set_traces(self, traces, title=""):
        self.traces = traces
        self.title_lbl.config(text=title)
        self._hover = None
        self.status.set("")
        if traces:
            self._init_range()
        self.redraw()

    # -- 视图 ----------------------------------------------------------------
    def _init_range(self):
        if not self.traces:
            self.x0, self.x1 = 0.0, 1.0
            return
        lo = min(min(t.times) for t in self.traces if t.times)
        hi = max(max(t.times) for t in self.traces if t.times)
        if hi <= lo:
            hi = lo + 1.0
        pad = (hi - lo) * 0.02
        self.x0, self.x1 = lo - pad, hi + pad

    def _reset(self):
        self._init_range()
        self.redraw()

    def _plot_rect(self):
        w = int(self.canvas.winfo_width())
        h = int(self.canvas.winfo_height())
        return (self.PAD_L, self.PAD_T, w - self.PAD_R, h - self.PAD_B)

    def _y_range(self):
        lo = hi = None
        for t in self.traces:
            for v, x in zip(t.values, t.times):
                if self.x0 <= x <= self.x1 and math.isfinite(v):
                    if lo is None or v < lo:
                        lo = v
                    if hi is None or v > hi:
                        hi = v
        if lo is None:
            return 0.0, 1.0
        if hi == lo:
            hi = lo + abs(lo) * 0.1 + 1e-9
        pad = (hi - lo) * 0.08
        return lo - pad, hi + pad

    def _time_of(self, px):
        rx0, _, rx1, _ = self._plot_rect()
        f = (px - rx0) / float(max(1, rx1 - rx0))
        return self.x0 + f * (self.x1 - self.x0)

    # -- 绘制 ----------------------------------------------------------------
    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        w = int(cv.winfo_width())
        h = int(cv.winfo_height())
        if w < 120 or h < 120:
            return
        if not self.traces:
            cv.create_text(w / 2.0, h / 2.0, text=tr("preview_hint"),
                           font=FONT_SMALL, fill=TEXT_DISABLED,
                           justify="center")
            return
        rx0, ry0, rx1, ry1 = self._plot_rect()
        ylo, yhi = self._y_range()
        xlo, xhi = self.x0, self.x1

        step_x = _nice_step(xhi - xlo, 7)
        step_y = _nice_step(yhi - ylo, 6)
        minor_x, minor_y = step_x / 5.0, step_y / 5.0

        def x_of(v):
            return rx0 + (v - xlo) / (xhi - xlo) * (rx1 - rx0)

        def y_of(v):
            return ry1 - (v - ylo) / (yhi - ylo) * (ry1 - ry0)

        # 主网格：极浅，保证专业感又不抢曲线
        for i in range(int(math.floor(xlo / step_x)),
                       int(math.ceil(xhi / step_x)) + 1):
            px = x_of(i * step_x)
            if rx0 - 0.5 <= px <= rx1 + 0.5:
                cv.create_line(px, ry0, px, ry1, fill=GRID_MAJOR)
        for i in range(int(math.floor(ylo / step_y)),
                       int(math.ceil(yhi / step_y)) + 1):
            py = y_of(i * step_y)
            if ry0 - 0.5 <= py <= ry1 + 0.5:
                cv.create_line(rx0, py, rx1, py, fill=GRID_MAJOR)

        # 刻度：向内，四边都有；主刻度带数字
        for i in range(int(math.floor(xlo / minor_x)),
                       int(math.ceil(xhi / minor_x)) + 1):
            v = i * minor_x
            if v < xlo - 1e-12 or v > xhi + 1e-12:
                continue
            px = x_of(v)
            length = 6 if i % 5 == 0 else 3
            cv.create_line(px, ry1, px, ry1 - length, fill=AXIS_COLOR)
            cv.create_line(px, ry0, px, ry0 + length, fill=AXIS_COLOR)
            if i % 5 == 0:
                cv.create_text(px, ry1 + 13, text=_fmt_tick(v, step_x),
                               font=FONT_TICK, fill=AXIS_TEXT)
        for i in range(int(math.floor(ylo / minor_y)),
                       int(math.ceil(yhi / minor_y)) + 1):
            v = i * minor_y
            if v < ylo - 1e-12 or v > yhi + 1e-12:
                continue
            py = y_of(v)
            length = 6 if i % 5 == 0 else 3
            cv.create_line(rx0, py, rx0 + length, py, fill=AXIS_COLOR)
            cv.create_line(rx1, py, rx1 - length, py, fill=AXIS_COLOR)
            if i % 5 == 0:
                cv.create_text(rx0 - 8, py, text=_fmt_tick(v, step_y),
                               font=FONT_TICK, fill=AXIS_TEXT, anchor="e")

        # 坐标框与轴标题
        cv.create_rectangle(rx0, ry0, rx1, ry1, outline=AXIS_COLOR)
        cv.create_text((rx0 + rx1) / 2.0, ry1 + 34, text=tr("time_axis"),
                       font=FONT_SMALL, fill=AXIS_TEXT)
        cv.create_text(16, (ry0 + ry1) / 2.0, text=tr("volt_axis"),
                       font=FONT_SMALL, fill=AXIS_TEXT, angle=90)

        for t in self.traces:
            self._draw_trace(cv, t, rx0, ry0, rx1, ry1, ylo, yhi)

        self._draw_legend(cv, rx0 + 12, ry0 + 12)

        if self._hover is not None:
            self._draw_cross(cv, rx0, ry0, rx1, ry1, ylo, yhi)

    def _draw_legend(self, cv, x, y):
        """Origin 风格图例框：细边框 + 线段样例 + 名称。"""
        measure = tkfont.Font(font=FONT_TICK)
        rows = []
        for t in self.traces:
            label = t.name + (" (%s)" % t.unit if t.unit else "")
            rows.append((label, t.color))
        width = max(measure.measure(lb) for lb, _ in rows) + 46
        height = len(rows) * 16 + 10
        cv.create_rectangle(x, y, x + width, y + height, fill=CARD_BG,
                            outline=LEGEND_LINE)
        for i, (label, color) in enumerate(rows):
            ly = y + 8 + i * 16
            cv.create_line(x + 8, ly, x + 28, ly, fill=color, width=2)
            cv.create_text(x + 34, ly, text=label, font=FONT_TICK,
                           fill=AXIS_TEXT, anchor="w")

    def _draw_trace(self, cv, t, rx0, ry0, rx1, ry1, ylo, yhi):
        times, values = t.times, t.values
        if not times:
            return
        span = self.x1 - self.x0
        cols = max(2, int(rx1 - rx0))
        visible = [i for i, x in enumerate(times) if self.x0 <= x <= self.x1]
        if not visible:
            return

        def to_py(v):
            py = ry1 - (v - ylo) / (yhi - ylo) * (ry1 - ry0)
            return max(ry0, min(ry1, py))

        if len(visible) <= cols * 2:
            pts = []
            for i in visible:
                px = rx0 + (times[i] - self.x0) / span * (rx1 - rx0)
                pts.extend((px, to_py(values[i])))
            if len(pts) >= 4:
                cv.create_line(pts, fill=t.color, width=2,
                               joinstyle="round", capstyle="round")
            return
        # 大数据：每像素列抽稀为 min/max 两笔
        buckets = {}
        for i in visible:
            c = int(rx0 + (times[i] - self.x0) / span * (rx1 - rx0))
            v = values[i]
            b = buckets.get(c)
            if b is None:
                buckets[c] = [v, v]
            elif v < b[0]:
                b[0] = v
            elif v > b[1]:
                b[1] = v
        pts_min, pts_max = [], []
        for c in sorted(buckets):
            lo, hi = buckets[c]
            px = c + 0.5
            pts_min.extend((px, to_py(lo)))
            pts_max.extend((px, to_py(hi)))
        for pts in (pts_min, pts_max):
            if len(pts) >= 4:
                cv.create_line(pts, fill=t.color, width=1)

    def _draw_cross(self, cv, rx0, ry0, rx1, ry1, ylo, yhi):
        t = self._hover
        px = rx0 + (t - self.x0) / (self.x1 - self.x0) * (rx1 - rx0)
        cv.create_line(px, ry0, px, ry1, fill=CROSS_LINE, dash=(4, 3))
        parts = ["t=%s s" % _fmt_tick(t, _nice_step(self.x1 - self.x0, 1000))]
        for tr in self.traces:
            v = self._value_at(tr, t)
            if v is None:
                continue
            py = ry1 - (v - ylo) / (yhi - ylo) * (ry1 - ry0)
            py = max(ry0, min(ry1, py))
            cv.create_oval(px - 3, py - 3, px + 3, py + 3,
                           fill=tr.color, outline=CARD_BG)
            parts.append("%s=%s%s" % (
                tr.name, _fmt_tick(v, _nice_step(yhi - ylo, 1000)), tr.unit))
        self.status.set("   ".join(parts))

    def _value_at(self, trace, t):
        times = trace.times
        values = trace.values
        if not times or t < times[0] or t > times[-1]:
            return None
        lo, hi = 0, len(times) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if times[mid] < t:
                lo = mid + 1
            else:
                hi = mid
        idx = lo
        if idx > 0 and abs(times[idx - 1] - t) < abs(times[idx] - t):
            idx -= 1
        return values[idx]

    # -- 交互 ----------------------------------------------------------------
    def _on_move(self, event):
        rx0, _, rx1, _ = self._plot_rect()
        self._hover = self._time_of(event.x) if rx0 <= event.x <= rx1 else None
        self.redraw()

    def _clear_cross(self):
        self._hover = None
        self.status.set("")
        self.redraw()

    def _on_wheel(self, event):
        factor = 1.2 if event.delta > 0 else 1 / 1.2
        t = self._hover if self._hover is not None else (self.x0 + self.x1) / 2.0
        self.x0 = t - (t - self.x0) * factor
        self.x1 = t + (self.x1 - t) * factor
        self.redraw()

    def _on_press(self, event):
        self._drag_x = event.x

    def _on_drag(self, event):
        if self._drag_x is None:
            return
        rx0, _, rx1, _ = self._plot_rect()
        dt = (event.x - self._drag_x) / float(max(1, rx1 - rx0)) * (self.x1 - self.x0)
        self._drag_x = event.x
        self.x0 -= dt
        self.x1 -= dt
        self.redraw()


# --------------------------------------------------------------------------- 主窗口
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("%s %s" % (APP_NAME, APP_VERSION))
        scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self._scale = scale
        win_w = min(int(980 * scale), self.winfo_screenwidth() - 24)
        self.geometry("%dx%d" % (win_w, min(int(1000 * scale),
                                            self.winfo_screenheight() - 56)))
        self.minsize(int(900 * scale), int(560 * scale))
        self.configure(bg=PAGE_BG)
        self._set_icon()

        self.ftp = None
        self.ftp_lock = threading.Lock()
        self.ftp_path = ""            # 相对 FTP 根目录的当前路径
        self.dir_index_names = []     # 当前目录 index.txt 里的记录名（每条一行）
        self.save_dir = DOWNLOAD_DIR
        self.events = queue.Queue()
        self.busy = False
        self._connecting = False      # 正在建立连接（可取消）
        self._conn_cancel = False     # 取消当前连接尝试
        self._conn_gen = 0            # 连接代号：旧连接任务过期作废
        self._aborting = False        # 用户主动断开，忽略后续网络报错

        self._lang_refs = []          # 语言切换时需要刷新的静态控件回调

        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        self.path_var = tk.StringVar(value=tr("path_off"))
        self.status_var = tk.StringVar(value=tr("status_off"))
        self.conn_var = tk.StringVar(value=tr("conn_off"))

        os.makedirs(self.save_dir, exist_ok=True)
        self._build()
        self._refresh_local()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._tick)

    # -- 图标 ----------------------------------------------------------------
    def _set_icon(self):
        ico = os.path.join(resource_dir(), "logo.ico")
        if os.path.exists(ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

    # -- 布局 ----------------------------------------------------------------
    def _build(self):
        side = 18

        head = tk.Frame(self, bg=PAGE_BG)
        head.pack(fill="x", padx=side, pady=(10, 6))
        png = os.path.join(resource_dir(), "logo_64.png")
        self._logo = None
        if os.path.exists(png):
            try:
                self._logo = tk.PhotoImage(file=png).subsample(2, 2)
                tk.Label(head, image=self._logo, bg=PAGE_BG).pack(
                    side="left", padx=(0, 14))
            except Exception:
                self._logo = None
        box = tk.Frame(head, bg=PAGE_BG)
        box.pack(side="left")
        tk.Label(box, text=APP_NAME, font=FONT_TITLE, bg=PAGE_BG,
                 fg=TEXT_MAIN).pack(anchor="w")
        self.subtitle_lbl = tk.Label(
            box, text=tr("subtitle"),
            font=FONT_SMALL, bg=PAGE_BG, fg=TEXT_MUTED)
        self.subtitle_lbl.pack(anchor="w", pady=(3, 0))
        self.lang_btn = RoundedButton(head, tr("lang_btn"), self._toggle_lang,
                                      height=26)
        self.lang_btn.pack(side="right")
        tk.Label(head, textvariable=self.conn_var, font=FONT_UI, bg=PAGE_BG,
                 fg=TEXT_MUTED).pack(side="right", padx=(0, 12))

        # 卡片一：仪器连接 -----------------------------------------------------
        card1 = Card(self, padding=14)
        card1.pack(fill="x", padx=side)
        b1 = card1.inner
        self.card1_lbl = tk.Label(b1, text=tr("conn_card"), font=FONT_SMALL,
                                  bg=CARD_BG, fg=TEXT_MUTED)
        self.card1_lbl.pack(anchor="w")
        row1 = tk.Frame(b1, bg=CARD_BG)
        row1.pack(fill="x", pady=(7, 0))
        self.addr_lbl = tk.Label(row1, text=tr("addr"), font=FONT_UI,
                                 bg=CARD_BG, fg=TEXT_MAIN)
        self.addr_lbl.pack(side="left")
        self.host_entry = RoundedEntry(row1, self.host_var, FONT_MONO, width=150)
        self.host_entry.pack(side="left", padx=(8, 0))
        self.port_lbl = tk.Label(row1, text=tr("port"), font=FONT_UI,
                                 bg=CARD_BG, fg=TEXT_MAIN)
        self.port_lbl.pack(side="left", padx=(14, 0))
        self.port_entry = RoundedEntry(row1, self.port_var, FONT_MONO, width=62)
        self.port_entry.pack(side="left", padx=(8, 0))
        self.connect_btn = RoundedButton(row1, tr("connect"),
                                         self._toggle_connect)
        self.connect_btn.pack(side="left", padx=(14, 0))
        self.wifi_hint_lbl = tk.Label(row1, text=tr("wifi_hint"),
                                      font=FONT_SMALL, bg=CARD_BG,
                                      fg=TEXT_MUTED)
        self.wifi_hint_lbl.pack(side="left", padx=(14, 0))

        # 卡片二：示波器文件（存储区 / 曲线条目，不按文件表展示） -------------
        card2 = Card(self, padding=12)
        card2.pack(fill="x", padx=side, pady=(8, 0))
        b2 = card2.inner
        row2 = tk.Frame(b2, bg=CARD_BG)
        row2.pack(fill="x")
        self.card2_lbl = tk.Label(row2, text=tr("remote_card"), font=FONT_SMALL,
                                  bg=CARD_BG, fg=TEXT_MUTED)
        self.card2_lbl.pack(side="left")
        self.refresh_btn = RoundedButton(row2, tr("refresh"), self._ftp_refresh,
                                         height=26)
        self.refresh_btn.pack(side="right")

        row2b = tk.Frame(b2, bg=CARD_BG)
        row2b.pack(fill="x", pady=(8, 0))
        self.up_btn = RoundedButton(row2b, tr("up"), self._ftp_up, height=26)
        self.up_btn.pack(side="left")
        tk.Label(row2b, textvariable=self.path_var, font=FONT_SMALL,
                 bg=CARD_BG, fg=TEXT_MUTED).pack(side="left", padx=(10, 0))

        self.remote_area = ScrollArea(b2, height=132)
        self.remote_area.pack(fill="x", pady=(6, 0))
        self._remote_items = []

        row3 = tk.Frame(b2, bg=CARD_BG)
        row3.pack(fill="x", pady=(8, 0))
        self.dbl_hint_lbl = tk.Label(row3, text=tr("dbl_hint"),
                                     font=FONT_SMALL, bg=CARD_BG,
                                     fg=TEXT_MUTED)
        self.dbl_hint_lbl.pack(side="left")

        # 卡片三：本地分析 + 曲线预览 -------------------------------------------
        card3 = Card(self, padding=12)
        card3.pack(fill="x", padx=side, pady=(8, 0))
        b3 = card3.inner
        row4 = tk.Frame(b3, bg=CARD_BG)
        row4.pack(fill="x")
        self.card3_lbl = tk.Label(row4, text=tr("local_card"), font=FONT_SMALL,
                                  bg=CARD_BG, fg=TEXT_MUTED)
        self.card3_lbl.pack(side="left")
        self.local_hint_lbl = tk.Label(row4, text=tr("local_hint"),
                                       font=FONT_SMALL, bg=CARD_BG,
                                       fg=TEXT_MUTED)
        self.local_hint_lbl.pack(side="right")

        self._tree_style()
        self.local_tree = ttk.Treeview(
            b3, columns=("type", "size", "mtime"), show="tree headings",
            selectmode="extended", height=1)
        self.local_tree.heading("#0", text=tr("col_name"), anchor="w")
        self.local_tree.heading("type", text=tr("col_type"), anchor="w")
        self.local_tree.heading("size", text=tr("col_size"), anchor="e")
        self.local_tree.heading("mtime", text=tr("col_mtime"), anchor="w")
        self.local_tree.column("#0", width=380, stretch=True)
        self.local_tree.column("type", width=110, anchor="w", stretch=False)
        self.local_tree.column("size", width=90, anchor="e", stretch=False)
        self.local_tree.column("mtime", width=140, anchor="w", stretch=False)
        self.local_tree.pack(fill="x", pady=(8, 0))
        self.local_tree.bind("<ButtonRelease-1>", self._local_click)

        # 内嵌曲线预览
        self.preview = PlotPanel(b3)
        self.preview.pack(fill="x", pady=(8, 0))

        row5 = tk.Frame(b3, bg=CARD_BG)
        row5.pack(fill="x", pady=(10, 0))
        self.export_btn = RoundedButton(row5, tr("export_csv"),
                                        self._export_selected)
        self.export_btn.pack(side="left")
        self.open_dir_btn = RoundedButton(row5, tr("open_dir"), self._open_dir)
        self.open_dir_btn.pack(side="left", padx=(10, 0))

        # 状态栏 ---------------------------------------------------------------
        bar = tk.Frame(self, bg=PAGE_BG)
        bar.pack(fill="x", padx=side + 4, pady=(4, 6))
        tk.Label(bar, textvariable=self.status_var, font=FONT_SMALL, bg=PAGE_BG,
                 fg=TEXT_MUTED).pack(side="left")
        tk.Label(bar, text="%s %s  ·  %s  %s" % (
            APP_NAME, APP_VERSION, APP_AUTHOR, APP_EMAIL), font=FONT_SMALL,
            bg=PAGE_BG, fg=TEXT_DISABLED).pack(side="right")

        # 语言切换时刷新静态文案（lang_btn / connect_btn 单独处理）
        self._lang_refs.extend([
            lambda: self.subtitle_lbl.config(text=tr("subtitle")),
            lambda: self.card1_lbl.config(text=tr("conn_card")),
            lambda: self.addr_lbl.config(text=tr("addr")),
            lambda: self.port_lbl.config(text=tr("port")),
            lambda: self.wifi_hint_lbl.config(text=tr("wifi_hint")),
            lambda: self.card2_lbl.config(text=tr("remote_card")),
            lambda: self.dbl_hint_lbl.config(text=tr("dbl_hint")),
            lambda: self.card3_lbl.config(text=tr("local_card")),
            lambda: self.local_hint_lbl.config(text=tr("local_hint")),
            lambda: self.refresh_btn.set_text(tr("refresh")),
            lambda: self.up_btn.set_text(tr("up")),
            lambda: self.export_btn.set_text(tr("export_csv")),
            lambda: self.open_dir_btn.set_text(tr("open_dir")),
            self.preview.redraw,       # 预览面板的空态提示 / 坐标轴文案
        ])
        self._lang_refs.append(self._refresh_local)   # 本地列表的类型列文案
        self._lang_refs.append(self._render_remote)   # 仪器条目文案
        self._lang_refs.append(lambda: (
            self.local_tree.heading("#0", text=tr("col_name")),
            self.local_tree.heading("type", text=tr("col_type")),
            self.local_tree.heading("size", text=tr("col_size")),
            self.local_tree.heading("mtime", text=tr("col_mtime"))))
        self._lang_refs.append(self._update_preview_title)

        self.bind("<F5>", self._refresh_local)
        self._set_busy(False)
        self._render_remote()

        # 窗口高度按内容自适应：保证曲线预览和两个按钮完整可见。
        # 屏幕不够高时依次压缩预览区、仪器条目区，按钮行绝不裁掉
        self.update_idletasks()
        limit = self.winfo_screenheight() - 56

        def _need():
            self.update_idletasks()
            return self.winfo_reqheight() + 24

        for widget, base, floor in ((self.preview.canvas, 216, 156),
                                    (self.remote_area.canvas, 132, 112)):
            need = _need()
            if need <= limit:
                break
            widget.configure(height=max(floor, base - (need - limit)))
        win_w = min(int(980 * self._scale), self.winfo_screenwidth() - 24)
        self.geometry("%dx%d" % (win_w, min(_need(), limit)))

    def _tree_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Treeview", background=CARD_BG, fieldbackground=CARD_BG,
            foreground=TEXT_MAIN, rowheight=28, font=FONT_UI, borderwidth=0)
        style.configure("Treeview.Heading", background=CARD_BG,
                        foreground=TEXT_MUTED, font=FONT_SMALL,
                        borderwidth=0, relief="flat")
        style.map("Treeview.Heading", background=[("active", CARD_BG)])
        style.map("Treeview",
                  background=[("selected", SELECT_BG)],
                  foreground=[("selected", TEXT_MAIN)])
        style.configure("Treeview", bordercolor=CARD_BG, lightcolor=CARD_BG,
                        darkcolor=CARD_BG)

    # -- 多语言 ------------------------------------------------------------------
    def _toggle_lang(self):
        global _LANG
        _LANG = "en" if _LANG == "zh" else "zh"
        _save_lang()
        self._apply_language()

    def _apply_language(self):
        self.lang_btn.set_text(tr("lang_btn"))
        for fn in self._lang_refs:
            fn()
        if self.ftp is None:      # 未连接：状态栏 / 路径 / 按钮直接换新语言
            self.path_var.set(tr("path_off"))
            self.status_var.set(tr("status_off"))
            self.conn_var.set(tr("conn_off"))
            self.connect_btn.set_text(tr("connect"))
        else:                     # 已连接：连接状态与按钮同样要刷新
            self.conn_var.set(tr("conn_on") % self.host_var.get())
            self.connect_btn.set_text(tr("disconnect"))
            self.status_var.set(tr("connected_log")
                                % (self.host_var.get(), self.port_var.get()))
        # 已列出的仪器条目，其显示名同样换到新语言
        self._render_remote()

    # -- 事件调度 --------------------------------------------------------------
    def _tick(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                handler = getattr(self, "_ev_" + kind, None)
                if handler:
                    handler(payload)
        except queue.Empty:
            pass
        except Exception as exc:
            self.status_var.set(tr("tick_error") % exc)
        self.after(200, self._tick)

    def _emit(self, kind, payload):
        self.events.put((kind, payload))

    def _ev_log(self, text):
        self.status_var.set(str(text))

    def _ev_status(self, text):
        self.status_var.set(str(text))

    def _ev_error(self, text):
        # 任何后台任务失败都必须解除 busy，否则后续点击全部被忽略
        self._set_busy(False)
        self.status_var.set(str(text))
        messagebox.showerror(APP_NAME, str(text))

    def _ev_connected(self, _):
        self._connecting = False      # 连接完成，解除「连接中」状态
        self._conn_cancel = False
        self.conn_var.set(tr("conn_on") % self.host_var.get())
        self.connect_btn.set_text(tr("disconnect"))
        self._set_busy(False)
        self._ftp_refresh_async()

    def _ev_disconnected(self, _):
        self._connecting = False
        self.conn_var.set(tr("conn_off"))
        self.connect_btn.set_text(tr("connect"))
        self.ftp_path = ""
        self._clear_remote()
        self.path_var.set(tr("path_off"))
        self._set_busy(False)
        self._render_remote()

    # -- 通用状态 --------------------------------------------------------------
    def _set_busy(self, busy):
        self.busy = busy
        # 注意：connect_btn 不参与禁用 —— 它是「断开/取消」的逃生通道，
        # 任何卡住的网络操作都可以随时点它打断
        for btn in (self.refresh_btn, self.export_btn,
                    self.open_dir_btn, self.up_btn):
            btn.set_enabled(not busy)
        connected = self.ftp is not None
        self.host_entry.set_enabled(not busy and not connected)
        self.port_entry.set_enabled(not busy and not connected)

    def _run_bg(self, fn, *args):
        self._aborting = False

        def worker():
            try:
                fn(*args)
            except Exception as exc:
                if self._aborting:
                    # 用户已主动断开，静默收尾，不再弹错误框
                    self._emit("log", tr("aborted_log"))
                    return
                self._emit("error", tr("err_prefix") % exc)
                if self.ftp is not None and isinstance(
                        exc, (EOFError, OSError, socket.error)):
                    self._drop_ftp()
                    self._emit("disconnected", None)
        threading.Thread(target=worker, daemon=True).start()

    def _drop_ftp(self):
        ftp, self.ftp = self.ftp, None
        if ftp is not None:
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass

    # -- 连接 -------------------------------------------------------------------
    def _toggle_connect(self):
        if self._connecting:
            # 正在连接中再点一次 = 取消连接
            self._conn_cancel = True
            self._emit("disconnected", None)
            self._emit("log", tr("aborted_log"))
            return
        if self.ftp is not None:
            # 已连接时再点 = 断开；若有卡住的操作，一并打断（连接按钮始终可点）
            if self.busy:
                self._aborting = True
                self._emit("status", tr("aborted_log"))
            self._drop_ftp()
            self._emit("disconnected", None)
            self._emit("log", tr("disconnected_log"))
            return
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            messagebox.showwarning(APP_NAME, tr("port_numeric"))
            return
        if not host:
            messagebox.showwarning(APP_NAME, tr("need_host"))
            return
        self._conn_gen += 1
        self._conn_cancel = False
        self._connecting = True
        self._set_busy(True)
        self._emit("status", tr("connecting") % host)
        self._run_bg(self._connect_job, host, port, self._conn_gen)

    def _connect_job(self, host, port, gen):
        try:
            ftp = ftp_connect(host, port)
        except Exception as exc:
            if gen == self._conn_gen and not self._conn_cancel:
                self._emit("error", tr("conn_failed") % (exc, DEFAULT_HOST))
            if gen == self._conn_gen:
                self._emit("disconnected", None)
            return
        if gen != self._conn_gen or self._conn_cancel:
            try:
                ftp.close()
            except Exception:
                pass
            if gen == self._conn_gen:
                self._emit("disconnected", None)
                self._emit("log", tr("aborted_log"))
            return
        self.ftp = ftp
        self._emit("log", tr("connected_log") % (host, port))
        self._emit("connected", None)

    def _clear_remote(self):
        self._remote_items = []
        self.dir_index_names = []
        if hasattr(self, "remote_area"):
            self.remote_area.clear()

    # -- 仪器文件 ---------------------------------------------------------------
    def _ftp_refresh_async(self, *args):
        if self.ftp is None or self.busy:
            if self.ftp is None:
                self._emit("status", tr("connect_first"))
            return
        self._set_busy(True)
        self._emit("status", tr("reading_dir"))
        self._run_bg(self._list_job)

    def _ftp_refresh(self):
        self._ftp_refresh_async()

    def _list_job(self):
        with self.ftp_lock:
            items = ftp_list(self.ftp, self.ftp_path)
            index = read_dir_index(self.ftp, self.ftp_path, items)
        self._emit("remote_list", (items, index))

    def _ev_remote_list(self, payload):
        items, index_names = payload
        self._remote_items = items
        self.dir_index_names = index_names
        self._render_remote()
        self._set_busy(False)
        self._emit("status", tr("dir_done") % len(items) if items
                   else tr("empty_dir"))

    def _crumb_text(self):
        if not self.ftp_path:
            return tr("root_label")
        parts = [tr("root_label")]
        segs = self.ftp_path.split("/")
        for i, name in enumerate(segs):
            if i == 0:
                parts.append(remote_display_name("", name, True))
            elif i == 1:
                parts.append(remote_display_name(segs[0], name, True,
                                                 self.dir_index_names))
            else:
                parts.append(name)
        return " / ".join(parts)

    def _render_remote(self):
        """按当前层级把仪器内容渲染成「条目」，而不是文件表。"""
        area = self.remote_area
        area.clear()
        self.path_var.set(self._crumb_text() if self.ftp is not None
                          else tr("path_off"))
        items = self._remote_items

        if self.ftp is None:
            self._add_row(tr("not_connected_row"), "", None, "", muted=True)
            return
        if not items:
            self._add_row(tr("empty_dir"), "", None, "", muted=True)
            return

        parent = self.ftp_path
        root = not parent
        storage = parent.lower() in ("internal", "external")
        dirs = [it for it in items if it[2]]
        files = [it for it in items if not it[2]]
        if storage:
            # 存储区只展示曲线槽位：actual 是仪器内部的当前采集缓存，
            # index.txt 是槽位名索引（软件已用来命名，不必展示）
            dirs = [it for it in dirs if it[0].lower() != "actual"]
            files = [it for it in files if it[0].lower() != "index.txt"]
        dirs.sort(key=lambda it: _nat_key(it[0]))

        for name, _size, is_dir, _mt in dirs:
            label = remote_display_name(parent, name, is_dir,
                                        self.dir_index_names)
            if root:
                sub = tr("sub_storage")
            elif name.isdigit():
                sub = tr("sub_record")
            else:
                sub = tr("sub_enter")
            self._add_row(label, sub,
                          lambda n=name: self._remote_activate(n, True), "›",
                          key=name)
        for name, size, _is_dir, _mt in files:
            kind = remote_kind_key(name, False)
            sub = tr("sub_file") % (tr(kind) if kind else name,
                                    human_size(size) if size is not None else "—")
            self._add_row(name, sub,
                          lambda n=name: self._remote_activate(n, False), "↓",
                          key=name)

    def _add_row(self, title, subtitle, command, chevron="›", muted=False,
                 key=None):
        row = EntryRow(self.remote_area.inner, title, subtitle,
                       command or (lambda: None), chevron)
        row.key = key
        if muted:
            row.set_muted()
        row.pack(fill="x")
        sep = tk.Frame(self.remote_area.inner, bg=GRID_LINE, height=1)
        sep.pack(fill="x")
        self.remote_area.bind_wheel(row)
        self.remote_area.bind_wheel(sep)

    def _remote_activate(self, name, is_dir):
        if self.ftp is None:
            self._emit("status", tr("connect_first"))
            return
        if self.busy or self._connecting:
            self._emit("status", tr("busy_now"))
            return
        if is_dir:
            self._folder_flow(name)      # 先列目录：容器则进入，记录则整包下载
        else:
            self._set_busy(True)
            self._run_bg(self._download_job, (name,))

    def _folder_flow(self, name):
        label = remote_display_name(self.ftp_path, name, True,
                                    self.dir_index_names)
        self._set_busy(True)
        self._emit("status", tr("reading_into") % label)
        self._run_bg(self._folder_job, name)

    def _folder_job(self, name):
        # 一次下载文件夹里的全部文件：曲线文件只有采样点，
        # 时间轴信息在 chA-srInfo / chA-mrInfo 等同目录文件里，缺一不可
        parent = self.ftp_path
        remote_dir = name if not parent else parent + "/" + name
        with self.ftp_lock:
            items = ftp_list(self.ftp, remote_dir)
            index = read_dir_index(self.ftp, remote_dir, items)
        files = [n for n, _sz, is_dir, _mt in items if not is_dir]
        if not any(_is_scope_record(n) or _is_meter_record(n) for n in files):
            label = remote_display_name(parent, name, True, index)
            if parent.lower() in ("internal", "external") and name.isdigit():
                # 空的曲线槽位：直接提示，不进入空文件夹
                self._emit("notice", (name, tr("no_curve_data") % label))
                return
            # 容器目录（内部存储 / 外部存储）：进入浏览，不下载
            self.ftp_path = remote_dir
            self._emit("remote_list", (items, index))
            return
        label = remote_display_name(parent, name, True, index)
        local_dir = os.path.join(self.save_dir, record_dir_name(remote_dir))
        if os.path.isdir(local_dir):
            # 同名目录里若是另一条记录（换了仪器 / 重新录制），另存一份，
            # 既不覆盖旧数据，也不把两台仪器的文件混在同一个目录里
            try:
                existing = set(os.listdir(local_dir))
            except OSError:
                existing = set()
            if existing != set(files):
                local_dir = unique_path(local_dir)
        os.makedirs(local_dir, exist_ok=True)
        for idx, fname in enumerate(files, 1):
            self._emit("status", tr("downloading") % (idx, len(files), fname))
            with self.ftp_lock:
                ftp_download(self.ftp, remote_dir + "/" + fname,
                             os.path.join(local_dir, fname))
            self._emit("log", tr("downloaded_log") % fname)
        self._emit("folder_done", (local_dir, label, len(files)))

    def _ftp_up(self):
        if self.ftp is None or self.busy or not self.ftp_path:
            return
        target = self.ftp_path.rsplit("/", 1)[0] if "/" in self.ftp_path else ""
        self._ftp_enter(target, absolute=True)

    def _ftp_enter(self, name, absolute=False):
        new_path = name if absolute else (
            self.ftp_path + "/" + name if self.ftp_path else name)
        self._set_busy(True)
        self._run_bg(self._enter_job, new_path)

    def _enter_job(self, new_path):
        with self.ftp_lock:
            items = ftp_list(self.ftp, new_path)
            index = read_dir_index(self.ftp, new_path, items)
        self.ftp_path = new_path
        self._emit("remote_list", (items, index))

    def _download_job(self, names):
        # 记录文件的时间轴元数据在 chA-srInfo / chA-mrInfo 里，一并下载，
        # 否则导出/绘图只能退回默认采样间隔
        names = list(names)
        extras = []
        for name in list(names):
            extra = (SR_INFO_FILE if _is_scope_record(name)
                     else "chA-mrInfo" if _is_meter_record(name) else None)
            if extra and extra not in names:
                names.append(extra)
                extras.append(extra)
        total = len(names)
        last = [0]

        def progress(done):
            if done - last[0] >= 512 * 1024:
                last[0] = done
                self._emit("status", tr("receiving") % human_size(done))

        done_files = []
        for idx, name in enumerate(names, 1):
            self._emit("status", tr("downloading") % (idx, total, name))
            remote = name if not self.ftp_path else self.ftp_path + "/" + name
            local = unique_path(os.path.join(self.save_dir, name))
            try:
                with self.ftp_lock:
                    ftp_download(self.ftp, remote, local, progress)
            except Exception:
                if name in extras:
                    continue          # 附属元数据不存在时忽略，不影响主文件
                raise
            done_files.append(os.path.basename(local))
            self._emit("log", tr("downloaded_log") % os.path.basename(local))
        self._emit("status", tr("download_done") % total)
        # 直接衔接本地分析：刷新列表、选中刚下载的文件并弹窗确认
        self._emit("download_done", (tuple(done_files), total))

    def _ev_refresh_local(self, _):
        self._refresh_local()

    def _ev_busy_off(self, _):
        self._set_busy(False)

    def _ev_notice(self, payload):
        # 空曲线槽位等提示：解除占用，并在对应条目的副标题上标出来
        name, text = payload
        self._set_busy(False)
        self.status_var.set(text)
        for row in self.remote_area.inner.winfo_children():
            if isinstance(row, EntryRow) and getattr(row, "key", None) == name:
                row.set_note(text)

    def _ev_download_done(self, payload):
        files, total = payload
        self._refresh_local()
        self._set_busy(False)
        items = [i for i in self.local_tree.get_children() if i in files]
        if items:
            self.local_tree.selection_set(items)
            self.local_tree.see(items[0])
        messagebox.showinfo(APP_NAME,
                            tr("download_done_msg") % (total, self.save_dir))

    def _ev_folder_done(self, payload):
        local_dir, name, total = payload
        self._refresh_local()
        self._set_busy(False)
        key = os.path.basename(local_dir)
        for iid in self.local_tree.get_children():
            if iid == key:
                self.local_tree.selection_set(iid)
                self.local_tree.see(iid)
                break
        self._preview_path(local_dir)     # 下载完成直接出曲线，无需再操作
        self._emit("status", tr("folder_done_msg") % (
            name, total, os.path.basename(local_dir)))

    # -- 本地文件 ---------------------------------------------------------------
    def _refresh_local(self, *args):
        if not hasattr(self, "local_tree"):
            return
        self.local_tree_delete_all()
        try:
            names = sorted(os.listdir(self.save_dir), key=_nat_key)
        except OSError as exc:
            self._emit("log", tr("read_dir_failed") % exc)
            return
        for name in names:
            path = os.path.join(self.save_dir, name)
            try:
                st = os.stat(path)
                mtime = time_str(st.st_mtime)
                size = human_size(st.st_size)
            except OSError:
                mtime, size = "—", "—"
            if os.path.isdir(path):
                # 仪器记录文件夹：整包数据（曲线 + 时间轴信息文件）在一起
                self.local_tree.insert("", "end", iid=name,
                                       text=local_display_name(name),
                                       values=(tr("type_folder"), "—", mtime))
                continue
            if not _previewable(name):
                continue  # 只显示可预览的文件（曲线/仪表记录、CSV）
            kind = remote_kind_key(name, False)
            self.local_tree.insert(
                "", "end", iid=name, text=name,
                values=(tr(kind) if kind else "—", size, mtime))

    def local_tree_delete_all(self):
        for item in self.local_tree.get_children():
            self.local_tree.delete(item)

    def _sel_paths(self):
        return [os.path.join(self.save_dir, i)
                for i in self.local_tree.selection()]

    def _local_click(self, event):
        # 单击即预览：文件夹 → 取其中的记录曲线；文件 → 直接预览
        row = self.local_tree.identify_row(event.y)
        if not row:
            return
        path = os.path.join(self.save_dir, row)
        if os.path.isdir(path) or _previewable(row):
            self._preview_path(path)

    def _open_dir(self):
        target = self.save_dir
        for p in self._sel_paths():
            if os.path.isdir(p):
                target = p       # 选中的是文件夹时直接打开它
        try:
            os.startfile(target)  # noqa: S606
        except OSError as exc:
            messagebox.showerror(APP_NAME, tr("open_dir_failed") % exc)

    # -- 预览 / 导出 ------------------------------------------------------------
    def _traces_for(self, path):
        """从文件夹或文件生成曲线，返回 (traces, 标题)。"""
        title = os.path.basename(path)
        if os.path.isdir(path):
            title = local_display_name(title)
            # 文件夹级流程：曲线文件只有采样点，时间轴在同目录的
            # chA-srInfo / chA-mrInfo 里，因此以文件夹为单位取数
            rec = None
            for name in sorted(os.listdir(path), key=_nat_key):
                p = os.path.join(path, name)
                if os.path.isfile(p) and (_is_scope_record(name)
                                          or _is_meter_record(name)):
                    rec = p
                    if _is_scope_record(name):
                        break        # 曲线记录优先
            if rec is None:
                for name in sorted(os.listdir(path), key=_nat_key):
                    if name.lower().endswith(".csv"):
                        rec = os.path.join(path, name)
                        break
            if rec is None:
                raise ValueError(tr("no_wave_folder"))
            path = rec        # 标题保留文件夹别名（示波器内部存储 · 曲线 1）
        traces = self._file_traces(path)
        if not traces:
            raise ValueError(tr("no_traces"))
        return traces, title

    def _file_traces(self, path):
        ext = os.path.splitext(path)[1].lower()
        if _is_meter_record(path):
            stats = parse_meter_record(path)
            traces = []
            for i, key in enumerate(("max", "avg", "min")):
                pts = stats[key]
                traces.append(Trace(
                    key, "V", [t for t, _ in pts],
                    [v for _, v in pts],
                    TRACE_COLORS[i % len(TRACE_COLORS)]))
            return traces
        if _is_scope_record(path):
            chans = parse_scope_record(path)
            n = max(len(v) for _, v in chans)
            period = scope_sample_period(path, n)
            traces = []
            for i, (name, vals) in enumerate(chans):
                times = [k * period for k in range(len(vals))]
                traces.append(Trace(name, "V", times, vals,
                                    TRACE_COLORS[i % len(TRACE_COLORS)]))
            return traces
        if ext == ".csv":
            return load_traces_from_csv(path)
        if ext == ".fvr":
            blocks, period = parse_fvr(path, DEFAULT_PERIOD)
            letters = "abcdefgh"
            traces = []
            for i, block in enumerate(blocks):
                name = "ch_%s" % (letters[i] if i < len(letters) else str(i))
                times = [k * period for k in range(len(block))]
                traces.append(Trace(name, "V", times, block,
                                    TRACE_COLORS[i % len(TRACE_COLORS)]))
            return traces
        raise ValueError(tr("unsupported"))

    def _preview_path(self, path):
        try:
            traces, title = self._traces_for(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("read_wave_failed") % (
                os.path.basename(path), exc))
            return
        self._preview_src = path
        self.preview.set_traces(traces, title)

    def _update_preview_title(self):
        """切换语言时，预览标题里的「示波器内部存储 · 曲线 N」也要跟着变。"""
        src = getattr(self, "_preview_src", None)
        if not src or not self.preview.traces:
            return
        title = (local_display_name(os.path.basename(src))
                 if os.path.isdir(src) else os.path.basename(src))
        self.preview.title_lbl.config(text=title)

    def _export_selected(self):
        jobs = []      # (记录文件路径, 输出目录)
        for p in self._sel_paths():
            if os.path.isdir(p):
                for name in sorted(os.listdir(p), key=_nat_key):
                    fp = os.path.join(p, name)
                    if os.path.isfile(fp) and (_is_scope_record(name)
                                               or _is_meter_record(name)):
                        jobs.append((fp, p))    # CSV 就近放在记录所在文件夹
            elif _previewable(os.path.basename(p)) \
                    and not p.lower().endswith(".csv"):
                jobs.append((p, os.path.dirname(p) or self.save_dir))
        if not jobs:
            messagebox.showinfo(APP_NAME, tr("pick_export"))
            return
        self._set_busy(True)
        self._run_bg(self._export_job, tuple(jobs))

    def _export_job(self, jobs):
        for path, out_dir in jobs:
            self._emit("status", tr("parsing") % os.path.basename(path))
            if _is_meter_record(path):
                outs = meter_record_to_csv(path, out_dir)
            elif _is_scope_record(path):
                outs = scope_record_to_csv(path, out_dir)
            else:
                outs = fvr_to_csv(path, out_dir, DEFAULT_PERIOD)
            for out in outs:
                self._emit("log", tr("exported_log") % os.path.basename(out))
        self._emit("status", tr("export_done"))
        self._emit("refresh_local", None)
        self._emit("busy_off", None)

    # -- 退出 -------------------------------------------------------------------
    def _on_close(self):
        self._drop_ftp()
        self.destroy()


def main():
    enable_dpi_awareness()
    App().mainloop()


if __name__ == "__main__":
    main()
