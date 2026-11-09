from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk

from builtin_themes import BUILTIN_THEMES, DEFAULT_THEME_NAME, PUBLISHED_THEME_ORDER, THEME_ALIASES
from theme_color_math import relative_luminance
from theme_interchange import ThemeImportError, export_native_theme, import_theme_file


DEFAULT_CHROME = copy.deepcopy(BUILTIN_THEMES[DEFAULT_THEME_NAME])

THEME_LABELS = {
    "background":"Window","panel_bg":"Panels","panel_edge":"Panel edge","field_bg":"Fields","field_fg":"Field text",
    "foreground":"Text","muted_fg":"Muted text","button_bg":"Buttons","button_fg":"Button text","active_bg":"Hover / active",
    "active_fg":"Active text","accent":"Primary accent","secondary_accent":"Secondary accent","selection_bg":"Selection","selection_fg":"Selection text",
    "tab_bg":"Tabs","tab_selected_bg":"Selected tab","preview_bg":"Preview background","preview_fg":"Preview text","success_fg":"Success",
    "warning_fg":"Warning","failure_fg":"Error","running_fg":"Running","sash_color":"Resize edge","scrollbar_bg":"Scrollbar","scrollbar_trough":"Scrollbar trough",
    "scale_bg":"Slider background","scale_trough":"Slider trough","tooltip_bg":"Tooltip background","tooltip_fg":"Tooltip text",
}
THEME_COLOUR_KEYS = [k for k,v in DEFAULT_CHROME.items() if isinstance(v,str) and re.fullmatch(r"#[0-9a-fA-F]{6}",v)]
THEME_COLOUR_ORDER = [
    "background","panel_bg","field_bg","foreground","muted_fg","button_bg","button_fg","active_bg",
    "selection_bg","accent","secondary_accent","tab_bg","tab_selected_bg","panel_edge","sash_color","preview_bg",
    "success_fg","warning_fg","failure_fg","running_fg","tooltip_bg","tooltip_fg","field_fg","active_fg","selection_fg",
    "disabled_fg","scrollbar_bg","scrollbar_trough","scale_bg","scale_trough","preview_fg",
]
THEME_COLOUR_ORDER = [k for k in THEME_COLOUR_ORDER if k in THEME_COLOUR_KEYS]
THEME_NUMBER_KEYS = [k for k,v in DEFAULT_CHROME.items() if isinstance(v,int) and k != "tooltip_delay_ms"]


def resolve_theme_preference(name: str | None, user_themes: dict, published_themes: list[str]) -> str:
    candidate = str(name or "")
    if candidate in user_themes:
        return candidate
    if candidate in published_themes:
        return candidate
    migrated = THEME_ALIASES.get(candidate)
    if migrated in published_themes:
        return migrated
    return DEFAULT_THEME_NAME if DEFAULT_THEME_NAME in published_themes else published_themes[0]


def tk_scale_theme_options(chrome: dict) -> dict:
    """Semantic colour options shared by native Tk Scale widgets.

    ttk does not own tk.Scale rendering, so these need explicit refreshes when
    the live Retrospector-style theme changes.
    """
    return {
        "background": chrome["scale_bg"],
        "foreground": chrome["foreground"],
        "troughcolor": chrome["scale_trough"],
        "activebackground": chrome["active_bg"],
        "highlightthickness": 0,
    }


def retheme_native_tk_scales(root, chrome: dict) -> None:
    """Refresh every tk.Scale below *root*, including open theme windows."""
    try:
        children = root.winfo_children()
    except Exception:
        return
    for child in children:
        if isinstance(child, tk.Scale):
            try:
                child.configure(**tk_scale_theme_options(chrome))
            except Exception:
                pass
        retheme_native_tk_scales(child, chrome)


def load_user_themes(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict):
            return {}
        result = {}
        for name, chrome in data.items():
            if isinstance(name, str) and name.strip() and isinstance(chrome, dict):
                result[name] = {**copy.deepcopy(DEFAULT_CHROME), **chrome}
        return result
    except Exception:
        return {}


def save_user_themes(path: Path, themes: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(themes, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class ToolTip:
    def __init__(self, widget, text: str, chrome: dict):
        self.widget = widget
        self.text = str(text or "")
        self.chrome = chrome
        self.after_id = None
        self.hide_id = None
        self.win = None
        self.enabled = True
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<FocusIn>", self._enter, add="+")
        widget.bind("<FocusOut>", self._schedule_hide, add="+")
        widget.bind("<Escape>", self._force_hide, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._force_hide, add="+")

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        if not self.enabled:
            self._cancel(); self._hide()

    def _enter(self, _event=None):
        if not self.enabled:
            return
        self._cancel()
        if not self.win:self.after_id = self.widget.after(max(50, int(self.chrome.get("tooltip_delay_ms", 360))), self._show)

    def _leave(self, _event=None):
        self._cancel(); self._schedule_hide()

    def _force_hide(self, _event=None):
        self._cancel();self._hide()

    def _schedule_hide(self, _event=None):
        if self.hide_id:return
        try:self.hide_id=self.widget.after(180,self._hide)
        except tk.TclError:self._hide()

    def _cancel(self,_event=None):
        if self.hide_id:
            try:self.widget.after_cancel(self.hide_id)
            except Exception:pass
            self.hide_id=None
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _show(self):
        if not self.enabled or not self.text or self.win:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            self.win = tk.Toplevel(self.widget)
            self.win.wm_overrideredirect(True)
            label = tk.Label(
                self.win, text=self.text, justify="left", wraplength=self.chrome.get("tooltip_wrap_px", 390),
                bg=self.chrome.get("tooltip_bg", "#301A36"), fg=self.chrome.get("tooltip_fg", "#FFF5FA"),
                relief="solid", bd=1, padx=8, pady=6,
                font=(self.chrome.get("font_family", "TkDefaultFont"), self.chrome.get("tooltip_font_size", 9)),
            )
            label.pack()
            self.win.bind("<Enter>", self._cancel)
            self.win.bind("<Leave>", self._schedule_hide)
            self.win.bind("<Escape>", self._force_hide)
            self.win.update_idletasks()
            x = max(0, min(x, self.widget.winfo_screenwidth() - self.win.winfo_reqwidth() - 8))
            y = max(0, min(y, self.widget.winfo_screenheight() - self.win.winfo_reqheight() - 8))
            self.win.wm_geometry(f"+{x}+{y}")
        except Exception:
            self.win = None

    def _hide(self):
        self.hide_id=None
        if self.win:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None


class ResizablePane(tk.PanedWindow):
    """Retrospector-style pane with hard drag limits and visible handles."""
    def __init__(self, master, orient, chrome, **kw):
        vertical = orient in (tk.VERTICAL, "vertical")
        super().__init__(
            master, orient=orient, opaqueresize=True, showhandle=True,
            handlesize=chrome.get("handle_size", 10), handlepad=chrome.get("handle_offset", 18),
            sashwidth=chrome.get("sash_width", 7), sashrelief=tk.RAISED, bd=0, relief=tk.FLAT,
            bg=chrome.get("sash_color", "#6A465E"),
            sashcursor="sb_v_double_arrow" if vertical else "sb_h_double_arrow", **kw,
        )
        self._bounds_provider = None
        self._drag_index = None
        self._drag_offset = 0
        self.bind("<ButtonPress-1>", self._begin, add="+")
        self.bind("<B1-Motion>", self._drag, add="+")
        self.bind("<ButtonRelease-1>", self._end, add="+")

    def add(self, child, **kw):
        kw.pop("weight", None)
        kw.setdefault("stretch", "always")
        return super().add(child, **kw)

    def set_bounds_provider(self, provider):
        self._bounds_provider = provider

    def sashpos(self, index, newpos=None):
        x, y = self.sash_coord(index)
        current = y if str(self.cget("orient")) == "vertical" else x
        if newpos is None:
            return current
        if self._bounds_provider:
            try:
                lo, hi = self._bounds_provider(index)
                newpos = max(int(lo), min(int(hi), int(newpos)))
            except Exception:
                pass
        if str(self.cget("orient")) == "vertical":
            self.sash_place(index, x, int(newpos))
        else:
            self.sash_place(index, int(newpos), y)
        return int(newpos)

    def _bounds(self, index):
        axis = self.winfo_height() if str(self.cget("orient")) == "vertical" else self.winfo_width()
        try:
            lo, hi = self._bounds_provider(index) if self._bounds_provider else (0, axis)
            lo, hi = int(lo), int(hi)
        except Exception:
            lo, hi = 0, axis
        return lo, max(lo, hi)

    def _begin(self, event):
        try:
            ident = self.identify(event.x, event.y)
        except tk.TclError:
            return
        if not ident:
            return
        try:
            index, kind = int(ident[0]), str(ident[1])
        except Exception:
            return
        if kind not in {"sash", "handle"}:
            return
        self._drag_index = index
        coord = event.y if str(self.cget("orient")) == "vertical" else event.x
        self._drag_offset = coord - self.sashpos(index)
        return "break"

    def _drag(self, event):
        if self._drag_index is None:
            return
        coord = event.y if str(self.cget("orient")) == "vertical" else event.x
        lo, hi = self._bounds(self._drag_index)
        self.sashpos(self._drag_index, max(lo, min(hi, int(coord - self._drag_offset))))
        return "break"

    def _end(self, _event):
        if self._drag_index is None:
            return
        index = self._drag_index
        self._drag_index = None
        lo, hi = self._bounds(index)
        self.sashpos(index, max(lo, min(hi, self.sashpos(index))))
        try:
            self.event_generate("<<OmneSashChanged>>", when="tail")
        except tk.TclError:
            pass
        return "break"


class CollapsibleSection(ttk.Frame):
    def __init__(self, parent, title: str, expanded: bool = True, on_toggle=None):
        super().__init__(parent)
        self.title = title
        self.expanded = bool(expanded)
        self.on_toggle = on_toggle
        self.header = ttk.Button(self, style="Collapse.TButton", command=self.toggle)
        self.header.pack(fill="x")
        self.body = ttk.Frame(self, padding=(5, 4, 5, 6))
        self._sync()

    def _sync(self):
        self.header.configure(text=("▾  " if self.expanded else "▸  ") + self.title)
        if self.expanded:
            self.body.pack(fill="both", expand=True)
        else:
            self.body.pack_forget()

    def set_expanded(self, value: bool, notify=False):
        self.expanded = bool(value); self._sync()
        if notify and self.on_toggle:
            self.on_toggle(self.expanded)

    def toggle(self):
        self.set_expanded(not self.expanded, notify=True)


class SearchableFontCombobox(ttk.Combobox):
    def __init__(self, parent, **kw):
        self._all_fonts = sorted(set(tkfont.families(parent)), key=str.casefold)
        kw.setdefault("values", self._all_fonts)
        super().__init__(parent, **kw)
        self.bind("<KeyRelease>", self._filter, add="+")

    def _filter(self, event):
        if event.keysym in {"Up", "Down", "Return", "Escape", "Tab"}:
            return
        needle = self.get().casefold().strip()
        self["values"] = self._all_fonts if not needle else [x for x in self._all_fonts if needle in x.casefold()]


def retheme_native_menus(root,chrome):
    """Update already created menu surfaces as well as future popup defaults."""
    def walk(parent):
        for child in parent.winfo_children():
            if isinstance(child,tk.Menu):
                try:child.configure(background=chrome['field_bg'],foreground=chrome['field_fg'],
                    activebackground=chrome['selection_bg'],activeforeground=chrome['selection_fg'])
                except tk.TclError:pass
            if isinstance(child,ttk.Combobox):
                # Tk keeps an already-created native dropdown Listbox after
                # its first opening. Option defaults alone do not repaint it.
                name=str(child)+'.popdown.f.l'
                try:
                    if int(root.tk.call('winfo','exists',name)):
                        root.tk.call(name,'configure',
                            '-background',chrome['field_bg'],'-foreground',chrome['field_fg'],
                            '-selectbackground',chrome['selection_bg'],
                            '-selectforeground',chrome['selection_fg'])
                except tk.TclError:pass
            walk(child)
    try:walk(root)
    except tk.TclError:pass


def configure_theme(root, chrome: dict):
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    font = (chrome["font_family"], chrome["font_size"])
    heading = (chrome["font_family"], chrome["heading_size"], "bold")
    root.option_add("*Font", font)
    style.configure(".", background=chrome["panel_bg"], foreground=chrome["foreground"], font=font,
                    borderwidth=chrome["border_width"], bordercolor=chrome["panel_edge"], lightcolor=chrome["panel_edge"],
                    darkcolor=chrome["panel_edge"], troughcolor=chrome["scrollbar_trough"], focuscolor=chrome["accent"])
    style.configure("TFrame", background=chrome["panel_bg"])
    style.configure("TLabel", background=chrome["panel_bg"], foreground=chrome["foreground"])
    style.configure("Muted.TLabel", background=chrome["panel_bg"], foreground=chrome["muted_fg"])
    style.configure("Title.TLabel", background=chrome["panel_bg"], foreground=chrome["foreground"], font=heading)
    style.configure("Welcome.TLabel", background=chrome["panel_bg"], foreground=chrome["foreground"], font=(chrome["font_family"], chrome["welcome_size"], "bold"))
    style.configure("TLabelframe", background=chrome["panel_bg"], bordercolor=chrome["panel_edge"], lightcolor=chrome["panel_edge"], darkcolor=chrome["panel_edge"])
    style.configure("TLabelframe.Label", background=chrome["panel_bg"], foreground=chrome["foreground"])
    style.configure("TButton", background=chrome["button_bg"], foreground=chrome["button_fg"], padding=(chrome["button_pad_x"], chrome["button_pad_y"]), bordercolor=chrome["panel_edge"])
    style.configure("Accent.TButton", background=chrome["accent"], foreground=chrome["background"], padding=(chrome["button_pad_x"] + 2, chrome["button_pad_y"] + 1), bordercolor=chrome["accent"])
    style.map("Accent.TButton", background=[("active", chrome["secondary_accent"]), ("pressed", chrome["selection_bg"])])
    style.configure("Collapse.TButton", background=chrome["panel_bg"], foreground=chrome["secondary_accent"], padding=(6,2), anchor="w", relief="flat", borderwidth=0)
    style.map("Collapse.TButton", background=[("active", chrome["active_bg"])], foreground=[("active", chrome["active_fg"])])
    style.map("TButton", background=[("pressed", chrome["selection_bg"]), ("active", chrome["active_bg"])], foreground=[("disabled", chrome["disabled_fg"]), ("active", chrome["active_fg"])])
    for st in ("TCheckbutton", "TRadiobutton"):
        style.configure(st, background=chrome["panel_bg"], foreground=chrome["foreground"])
        style.map(st, background=[("active", chrome["panel_bg"])], foreground=[("disabled", chrome["disabled_fg"]), ("active", chrome["active_fg"])])
    for st in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(st, fieldbackground=chrome["field_bg"], background=chrome["field_bg"], foreground=chrome["field_fg"], selectbackground=chrome["selection_bg"], selectforeground=chrome["selection_fg"], arrowcolor=chrome["secondary_accent"], bordercolor=chrome["panel_edge"])
    # Read-only Comboboxes are a separate ttk state. The non-editable field
    # and the native listbox popup must follow the live theme as well.
    style.map("TCombobox",fieldbackground=[("readonly",chrome["field_bg"])],
              foreground=[("readonly",chrome["field_fg"])],
              selectbackground=[("readonly",chrome["selection_bg"])],
              selectforeground=[("readonly",chrome["selection_fg"])],
              arrowcolor=[("readonly",chrome["secondary_accent"])])
    root.option_add('*Menu.background',chrome['field_bg'])
    root.option_add('*Menu.foreground',chrome['field_fg'])
    root.option_add('*Menu.activeBackground',chrome['selection_bg'])
    root.option_add('*Menu.activeForeground',chrome['selection_fg'])
    root.option_add('*TCombobox*Listbox.background',chrome['field_bg'])
    root.option_add('*TCombobox*Listbox.foreground',chrome['field_fg'])
    root.option_add('*TCombobox*Listbox.selectBackground',chrome['selection_bg'])
    root.option_add('*TCombobox*Listbox.selectForeground',chrome['selection_fg'])
    retheme_native_menus(root,chrome)
    style.configure("TNotebook", background=chrome["background"], bordercolor=chrome["panel_edge"], tabmargins=(2,2,2,0))
    style.configure("TNotebook.Tab", background=chrome["tab_bg"], foreground=chrome["foreground"], padding=(10,4), bordercolor=chrome["panel_edge"])
    style.map("TNotebook.Tab", background=[("selected", chrome["tab_selected_bg"]), ("active", chrome["active_bg"])], foreground=[("selected", chrome["selection_fg"]), ("active", chrome["active_fg"])])
    style.configure("Treeview", background=chrome["field_bg"], fieldbackground=chrome["field_bg"], foreground=chrome["field_fg"], rowheight=chrome["row_height"], bordercolor=chrome["panel_edge"])
    style.map("Treeview", background=[("selected", chrome["selection_bg"])], foreground=[("selected", chrome["selection_fg"])])
    style.configure("Treeview.Heading", background=chrome["button_bg"], foreground=chrome["button_fg"], bordercolor=chrome["panel_edge"])
    for st in ("Horizontal.TScrollbar", "Vertical.TScrollbar"):
        style.configure(st, background=chrome["scrollbar_bg"], troughcolor=chrome["scrollbar_trough"], arrowcolor=chrome["foreground"], arrowsize=chrome["scrollbar_width"])
    style.configure("Horizontal.TProgressbar", background=chrome["accent"], troughcolor=chrome["scrollbar_trough"])
    style.configure("TSeparator", background=chrome["panel_edge"])
    root.configure(background=chrome["background"])
    return style


class ThemeEditor(ttk.Frame):
    RANGES = {
        "font_size":(7,18,1),"heading_size":(8,26,1),"welcome_size":(10,34,1),"panel_padding":(2,24,1),
        "button_pad_x":(2,20,1),"button_pad_y":(1,14,1),"border_width":(1,5,1),"row_height":(18,40,1),
        "sash_width":(3,14,1),"handle_size":(5,18,1),"handle_offset":(4,50,1),"scrollbar_width":(8,22,1),
        "slider_length":(100,320,5),"tooltip_font_size":(8,16,1),"tooltip_wrap_px":(220,700,10),"mono_size":(8,16,1),
        "tooltip_delay_ms":(100,1500,1),
    }

    def __init__(self, master, app, *, embedded=True):
        super().__init__(master)
        self.app = app
        self.embedded = bool(embedded)
        self.session_original_name = app.theme_name.get()
        self.session_original_chrome = copy.deepcopy(app.ui_chrome)
        self.original_chrome = copy.deepcopy(app.ui_chrome)
        self._loading = False; self._saved = False; self.vars = {}

        outer = ttk.Frame(self, padding=10); outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer); top.pack(fill="x", pady=(0,7)); top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Theme").grid(row=0,column=0,sticky="w")
        self.base = tk.StringVar(value=self.session_original_name)
        self.combo = ttk.Combobox(top, textvariable=self.base, values=app.available_themes, state="readonly")
        self.combo.grid(row=0,column=1,sticky="ew",padx=6); self.combo.bind("<<ComboboxSelected>>", lambda _e:self.load_base())
        tools=ttk.Frame(outer);tools.pack(fill="x",pady=(0,5))
        ttk.Button(tools,text="Save as Theme…",command=self.save_as).pack(side="left",padx=(0,5))
        ttk.Button(tools,text="Import…",command=lambda:import_theme_dialog(app)).pack(side="left",padx=(0,5))
        ttk.Button(tools,text="Export…",command=self.export_current).pack(side="left",padx=(0,5))
        ttk.Button(tools,text="Revert",command=self.load_base).pack(side="left")

        holder=ttk.Frame(outer);holder.pack(fill="both",expand=True);holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(holder,highlightthickness=0,background=app.ui_chrome["background"]);self.canvas.grid(row=0,column=0,sticky="nsew")
        bar=ttk.Scrollbar(holder,orient="vertical",command=self.canvas.yview);bar.grid(row=0,column=1,sticky="ns");self.canvas.configure(yscrollcommand=bar.set)
        self.body=ttk.Frame(self.canvas,padding=(4,2,8,8));self.win=self.canvas.create_window(0,0,window=self.body,anchor="nw")
        self.body.bind("<Configure>",lambda _e:self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",lambda e:self.canvas.itemconfigure(self.win,width=e.width))

        ttk.Label(self.body,text="Palette",style="Title.TLabel").pack(anchor="w",pady=(0,5))
        palette=ttk.Frame(self.body);palette.pack(fill="x")
        for i,key in enumerate(THEME_COLOUR_ORDER):
            row=i//2;group=i%2;col=group*3
            ttk.Label(palette,text=THEME_LABELS.get(key,key.replace("_"," ").title())).grid(row=row,column=col,sticky="w",padx=(0,4),pady=3)
            var=tk.StringVar();self.vars[key]=var
            sw=tk.Button(palette,width=3,relief="solid",bd=1,command=lambda k=key:self.pick(k));sw.grid(row=row,column=col+1,padx=2);var._swatch=sw
            ttk.Entry(palette,textvariable=var,width=10).grid(row=row,column=col+2,sticky="ew",padx=(0,12));var.trace_add("write",lambda *_a,k=key:self.changed(k))
        palette.columnconfigure(2,weight=1);palette.columnconfigure(5,weight=1)

        ttk.Separator(self.body).pack(fill="x",pady=10)
        ttk.Label(self.body,text="Sizing & density",style="Title.TLabel").pack(anchor="w",pady=(0,5))
        for key in THEME_NUMBER_KEYS + ["tooltip_delay_ms"]:
            if key not in self.RANGES: continue
            lo,hi,step=self.RANGES[key];row=ttk.Frame(self.body);row.pack(fill="x",pady=2);row.columnconfigure(1,weight=1)
            ttk.Label(row,text=key.replace("_"," ").title(),width=22).grid(row=0,column=0,sticky="w")
            var=tk.IntVar();self.vars[key]=var
            tk.Scale(row,from_=lo,to=hi,resolution=step,orient="horizontal",showvalue=False,variable=var,command=lambda _v,k=key:self.changed(k),**tk_scale_theme_options(app.ui_chrome)).grid(row=0,column=1,sticky="ew",padx=(0,5))
            ttk.Spinbox(row,from_=lo,to=hi,increment=step,textvariable=var,width=7,command=lambda k=key:self.changed(k)).grid(row=0,column=2)
            var.trace_add("write",lambda *_a,k=key:self.changed(k))

        ttk.Separator(self.body).pack(fill="x",pady=10)
        for key,label in [("font_family","Font family"),("mono_font","Monospace font")]:
            row=ttk.Frame(self.body);row.pack(fill="x",pady=2);row.columnconfigure(1,weight=1)
            ttk.Label(row,text=label,width=22).grid(row=0,column=0,sticky="w")
            var=tk.StringVar();self.vars[key]=var
            combo=SearchableFontCombobox(row,textvariable=var);combo.grid(row=0,column=1,sticky="ew");combo.bind("<<ComboboxSelected>>",lambda _e,k=key:self.changed(k));var.trace_add("write",lambda *_a,k=key:self.changed(k))

        note=ttk.Label(self.body,text="Changes update the running interface immediately. Saved themes stay on this computer and do not change the approved Funk theme library.",style="Muted.TLabel",justify="left",wraplength=680)
        note.pack(fill="x",pady=(10,0))
        if not embedded:
            foot=ttk.Frame(outer);foot.pack(fill="x",pady=(8,0))
            ttk.Button(foot,text="Done",command=self.close).pack(side="right")
            ttk.Button(foot,text="Cancel changes",command=self.cancel).pack(side="left")
        self.load_base()

    def current(self):
        result = copy.deepcopy(self.original_chrome)
        for key,var in self.vars.items():
            try: result[key] = int(var.get()) if isinstance(var,tk.IntVar) else str(var.get())
            except Exception: pass
        return {**copy.deepcopy(DEFAULT_CHROME), **result}

    def load_base(self):
        name=self.base.get();chrome=self.app.theme_library.get(name,self.app.ui_chrome);self._loading=True;self.original_chrome=copy.deepcopy(chrome)
        for key,var in self.vars.items():
            try: var.set(chrome.get(key,DEFAULT_CHROME.get(key,"")))
            except Exception: pass
        self._loading=False;self._saved=False;self.repaint_swatches();self.app.theme_name.set(name);self.app.apply_theme(name,save=False,chrome_override=self.current())

    def repaint_swatches(self):
        for key in THEME_COLOUR_ORDER:
            var=self.vars.get(key)
            if var:
                try: var._swatch.configure(bg=var.get(),activebackground=var.get())
                except Exception: pass
        try: self.canvas.configure(background=self.current()["background"])
        except Exception: pass

    def changed(self,key):
        if self._loading: return
        if key in THEME_COLOUR_KEYS and not re.fullmatch(r"#[0-9a-fA-F]{6}",str(self.vars[key].get())): return
        self._saved=False;self.repaint_swatches();self.app.apply_theme(self.base.get(),save=False,chrome_override=self.current())

    def pick(self,key):
        from tkinter import colorchooser
        colour=colorchooser.askcolor(color=self.vars[key].get(),parent=self,title=f"Choose {THEME_LABELS.get(key,key)}")[1]
        if colour:self.vars[key].set(colour.upper())

    def save_as(self):
        name=simpledialog.askstring(self.app.app_name,"Theme name:",parent=self)
        if not name or not name.strip(): return
        name=name.strip()
        if name in self.app.user_themes and not messagebox.askyesno(self.app.app_name,f'Replace local theme "{name}"?',parent=self): return
        chrome=self.current();self.app.user_themes[name]=copy.deepcopy(chrome);save_user_themes(self.app.user_theme_path,self.app.user_themes)
        self.app.theme_library[name]=copy.deepcopy(chrome);self.app.refresh_theme_choices();self.app.theme_name.set(name);self.app.apply_theme(name,save=True);self.base.set(name);self._saved=True
        self.session_original_name=name;self.session_original_chrome=copy.deepcopy(chrome);messagebox.showinfo(self.app.app_name,f"Saved local theme: {name}",parent=self)

    def export_current(self):
        name=(self.base.get() or DEFAULT_THEME_NAME).strip();initial=re.sub(r"[^A-Za-z0-9._-]+","_",name).strip("_") or "OmN-e_Theme"
        path=filedialog.asksaveasfilename(parent=self,title="Export OmN-e Theme",defaultextension=".omne-theme.json",initialfile=initial+".omne-theme.json",filetypes=[("OmN-e Theme","*.omne-theme.json"),("JSON","*.json")])
        if not path:return
        chrome=self.current();appearance="light" if relative_luminance(str(chrome["background"]))>=0.45 else "dark"
        export_native_theme(path,name,appearance,chrome,overwrite=True)
        messagebox.showinfo(self.app.app_name,f"Exported theme to {path}",parent=self)

    def persist(self):
        """Commit an edited palette without changing published built-in definitions."""
        name=self.base.get();chrome=self.current()
        if chrome!=self.app.theme_library.get(name):
            name=name if name in self.app.user_themes else name+' (custom)'
            self.app.user_themes[name]=copy.deepcopy(chrome)
            save_user_themes(self.app.user_theme_path,self.app.user_themes)
            self.app.theme_library[name]=copy.deepcopy(chrome)
            self.app.refresh_theme_choices()
        self.app.apply_theme(name,save=True)
        self.base.set(name)
        self.session_original_name=name
        self.session_original_chrome=copy.deepcopy(chrome)
        self.original_chrome=copy.deepcopy(chrome)

    def discard_preview(self):
        """Return to the last applied theme when closing Preferences."""
        self.app.theme_name.set(self.session_original_name)
        self.app.apply_theme(self.session_original_name,save=False,
                             chrome_override=self.session_original_chrome)

    def close(self):
        self.persist()
        self._finish()

    def cancel(self):
        self.app.theme_name.set(self.session_original_name)
        self.app.apply_theme(self.session_original_name,save=False,chrome_override=self.session_original_chrome)
        self.app.save_preferences()
        self._finish()

    def _finish(self):
        window=self.winfo_toplevel()
        if window is not self.app and not self.embedded:
            try:window.grab_release()
            except tk.TclError:pass
            window.destroy()
        else:self.destroy()



class ThemeStudio(tk.Toplevel):
    """Legacy standalone host; Neospector routes all current editing to Preferences."""
    def __init__(self, app):
        super().__init__(app)
        self.title(app.t("customize_theme", "Customize Theme"))
        self.transient(app)
        self.geometry("780x690");self.minsize(680,580)
        self.editor=ThemeEditor(self,app,embedded=False)
        self.editor.pack(fill="both",expand=True)
        self.protocol("WM_DELETE_WINDOW",self.editor.close)
        self.bind("<Escape>",lambda _e:self.editor.cancel())
        self.grab_set()

def import_theme_dialog(app):
    path=filedialog.askopenfilename(parent=app,title="Import Theme",filetypes=[("Supported themes","*.omne-theme.json *.json *.jsonc *.yaml *.yml *.tmTheme *.gpl"),("All files","*")])
    if not path:return
    try: imported=import_theme_file(path)
    except (ThemeImportError,Exception) as exc:
        messagebox.showerror(app.app_name,f"Theme import failed: {exc}",parent=app);return
    previous_name=app.theme_name.get();previous_chrome=copy.deepcopy(app.ui_chrome)
    app.apply_theme(imported.name,save=False,chrome_override=imported.chrome)
    answer=messagebox.askyesnocancel(app.app_name,f"Previewing {imported.name}\n\nSave this mapped theme locally?\nChoose No to use it only for this session.",parent=app)
    if answer is None:
        app.theme_name.set(previous_name);app.apply_theme(previous_name,save=False,chrome_override=previous_chrome);return
    name=imported.name.strip() or Path(path).stem
    if answer:
        app.user_themes[name]=copy.deepcopy(imported.chrome);save_user_themes(app.user_theme_path,app.user_themes)
    app.theme_library[name]=copy.deepcopy(imported.chrome);app.refresh_theme_choices();app.theme_name.set(name);app.apply_theme(name,save=bool(answer))
