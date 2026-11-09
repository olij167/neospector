"""Safe, pure theme interchange for OmN-e Retrospector.

External theme formats are adapters into the existing semantic ``chrome``
model.  This module intentionally has no Tk, network or subprocess imports.
"""
from __future__ import annotations

import colorsys
import json
import os
import plistlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from builtin_themes import BUILTIN_THEMES, DEFAULT_THEME_NAME
from theme_color_math import best_text_color, contrast_ratio, normalize_hex, relative_luminance

MAX_THEME_BYTES = 1024 * 1024
MAX_STRING = 4096
MAX_ENTRIES = 4096
MAX_PALETTE = 512
NATIVE_FORMAT = "omne.footage-lab.theme"
NATIVE_VERSION = 1
DEFAULT_CHROME = BUILTIN_THEMES[DEFAULT_THEME_NAME]


class ThemeImportError(ValueError):
    pass


@dataclass(frozen=True)
class ThemeDiagnostic:
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportedTheme:
    name: str
    appearance: Literal["dark", "light"]
    chrome: dict[str, object]
    source_format: str
    source_metadata: dict[str, str]
    diagnostics: tuple[ThemeDiagnostic, ...]
    extensions: dict[str, object]
    contrast: dict[str, float]


def _bounded_text(value: object, field: str, maximum: int = MAX_STRING) -> str:
    if not isinstance(value, str):
        raise ThemeImportError(f"{field} must be text")
    if len(value) > maximum:
        raise ThemeImportError(f"{field} is too long")
    return value


def _colour(value: object, fallback: str | None = None) -> str:
    if value in (None, "") and fallback is not None:
        return normalize_hex(fallback)
    try:
        return normalize_hex(str(value))
    except ValueError as exc:
        if fallback is not None:
            return normalize_hex(fallback)
        raise ThemeImportError(str(exc)) from exc


def _validate_chrome(chrome: dict[str, object]) -> dict[str, object]:
    if not isinstance(chrome, dict) or len(chrome) > 256:
        raise ThemeImportError("chrome must be a bounded object")
    resolved = dict(DEFAULT_CHROME)
    resolved.update(chrome)
    for key, default in DEFAULT_CHROME.items():
        value = resolved.get(key)
        if isinstance(default, int):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ThemeImportError(f"chrome.{key} must be an integer")
            low, high = (50, 5000) if key == "tooltip_delay_ms" else (1, 4096)
            if not low <= value <= high:
                raise ThemeImportError(f"chrome.{key} must be from {low} to {high}")
        elif not isinstance(value, str) or len(value) > 200:
            raise ThemeImportError(f"chrome.{key} must be bounded text")
        elif isinstance(default, str) and default.startswith("#"):
            resolved[key] = _colour(value)
    return resolved


def _contrast_summary(chrome: dict[str, object]) -> dict[str, float]:
    pairs = {
        "main": ("foreground", "background"),
        "panel": ("foreground", "panel_bg"),
        "field": ("field_fg", "field_bg"),
        "button": ("button_fg", "button_bg"),
        "active": ("active_fg", "active_bg"),
        "selection": ("selection_fg", "selection_bg"),
        "selected_tab": ("selection_fg", "tab_selected_bg"),
        "preview": ("preview_fg", "preview_bg"),
        "tooltip": ("tooltip_fg", "tooltip_bg"),
    }
    return {name: contrast_ratio(str(chrome[fg]), str(chrome[bg])) for name, (fg, bg) in pairs.items()}


def _appearance(background: str) -> Literal["dark", "light"]:
    return "light" if relative_luminance(background) >= 0.45 else "dark"


def _diagnose_contrast(chrome: dict[str, object]) -> tuple[ThemeDiagnostic, ...]:
    rows = _contrast_summary(chrome)
    bad = tuple(name for name, ratio in rows.items() if ratio < 4.5)
    if not bad:
        return ()
    return (ThemeDiagnostic(
        "contrast-warning",
        "warning",
        "Some mapped text/background pairs are below the 4.5:1 release target: " + ", ".join(bad),
        bad,
    ),)


def _imported(name: str, chrome: dict[str, object], source_format: str,
              source_metadata: dict[str, str] | None = None,
              diagnostics: tuple[ThemeDiagnostic, ...] = (),
              extensions: dict[str, object] | None = None,
              appearance: str | None = None) -> ImportedTheme:
    resolved = _validate_chrome(chrome)
    mode = appearance if appearance in {"dark", "light"} else _appearance(str(resolved["background"]))
    combined = tuple(diagnostics) + _diagnose_contrast(resolved)
    return ImportedTheme(
        name=(name.strip() or "Imported Theme")[:120],
        appearance=mode,  # type: ignore[arg-type]
        chrome=resolved,
        source_format=source_format,
        source_metadata=dict(source_metadata or {}),
        diagnostics=combined,
        extensions=dict(extensions or {}),
        contrast=_contrast_summary(resolved),
    )


def detect_theme_format(filename: str, raw: bytes) -> str:
    name = str(filename).lower()
    head = raw[:4096].lstrip()
    if name.endswith(".omne-theme.json"):
        return "native"
    if name.endswith(".tmtheme") or head.startswith(b"<?xml") or head.startswith(b"bplist"):
        return "textmate"
    if name.endswith(".gpl") or head.startswith(b"GIMP Palette"):
        return "gimp-gpl"
    if name.endswith((".yaml", ".yml")):
        return "base16"
    if name.endswith((".json", ".jsonc")) or head.startswith(b"{"):
        try:
            obj = json.loads(_strip_jsonc(raw.decode("utf-8")))
        except Exception:
            obj = None
        if isinstance(obj, dict) and obj.get("format") == NATIVE_FORMAT:
            return "native"
        return "vscode"
    raise ThemeImportError("Unsupported theme format")


def _strip_jsonc(text: str) -> str:
    """Remove JSONC comments/trailing commas without touching string content."""
    if len(text) > MAX_THEME_BYTES:
        raise ThemeImportError("Theme file is too large")
    out: list[str] = []
    i = 0
    in_string = False
    escape = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            if end < 0:
                raise ThemeImportError("Unterminated JSONC block comment")
            i = end + 2
            continue
        out.append(ch)
        i += 1
    if in_string:
        raise ThemeImportError("Unterminated JSON string")
    cleaned = "".join(out)
    # Remove commas immediately before ]/}, still respecting strings.
    out = []
    i = 0
    in_string = False
    escape = False
    while i < len(cleaned):
        ch = cleaned[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(cleaned) and cleaned[j].isspace():
                j += 1
            if j < len(cleaned) and cleaned[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _json_object(raw: bytes, jsonc: bool = False) -> dict[str, object]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ThemeImportError("Theme text must be UTF-8") from exc
    try:
        value = json.loads(_strip_jsonc(text) if jsonc else text)
    except (json.JSONDecodeError, ThemeImportError) as exc:
        raise ThemeImportError(f"Invalid JSON theme: {exc}") from exc
    if not isinstance(value, dict) or len(value) > MAX_ENTRIES:
        raise ThemeImportError("Theme JSON must be a bounded object")
    return value


def _parse_native(raw: bytes) -> ImportedTheme:
    data = _json_object(raw)
    if data.get("format") != NATIVE_FORMAT or data.get("version") != NATIVE_VERSION:
        raise ThemeImportError("Unsupported native theme format/version")
    if set(data) - {"format", "version", "name", "appearance", "source", "chrome", "extensions"}:
        raise ThemeImportError("Native theme contains unknown top-level fields")
    name = _bounded_text(data.get("name", ""), "name", 120)
    appearance = data.get("appearance")
    if appearance not in {"dark", "light"}:
        raise ThemeImportError("appearance must be dark or light")
    source = data.get("source") or {}
    if not isinstance(source, dict) or len(source) > 8:
        raise ThemeImportError("source must be a bounded object")
    metadata: dict[str, str] = {}
    for key, value in source.items():
        if key not in {"format", "name", "author", "uri"}:
            raise ThemeImportError(f"Unsupported source field: {key}")
        metadata[str(key)] = _bounded_text(value, f"source.{key}", 2048 if key == "uri" else 200)
    extensions = data.get("extensions") or {}
    if not isinstance(extensions, dict) or len(extensions) > 128:
        raise ThemeImportError("extensions must be a bounded object")
    try:
        encoded = json.dumps(extensions)
    except (TypeError, ValueError) as exc:
        raise ThemeImportError("extensions must be JSON-compatible") from exc
    if len(encoded) > 128 * 1024:
        raise ThemeImportError("extensions are too large")
    return _imported(name, data.get("chrome") or {}, "native", metadata,
                     extensions=extensions, appearance=str(appearance))


def _parse_flat_base16(raw: bytes) -> tuple[str, dict[str, str], dict[str, str]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ThemeImportError("Base16 YAML must be UTF-8") from exc
    if any(token in text for token in ("&", "*", "!", "<<:")):
        raise ThemeImportError("YAML anchors, aliases, tags and merges are not supported")
    data: dict[str, str] = {}
    for number, raw_line in enumerate(text.splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[:1].isspace():
            raise ThemeImportError(f"Nested YAML is not supported (line {number})")
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*:\s*(.*?)\s*", raw_line)
        if not match:
            raise ThemeImportError(f"Unsupported YAML syntax at line {number}")
        key, value = match.groups()
        if value.startswith(("[", "{", "|", ">")):
            raise ThemeImportError("Nested/compound YAML values are not supported")
        if len(data) >= 64:
            raise ThemeImportError("Base16 file has too many entries")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            # Strip an unquoted comment only when preceded by whitespace.
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        data[key] = value
    scheme = data.get("scheme") or "Imported Base16"
    metadata = {k: data[k] for k in ("scheme", "author") if k in data}
    colours: dict[str, str] = {}
    for i in range(24):
        key = f"base{i:02X}"
        if key in data:
            colours[key] = _colour(data[key])
    required = {f"base{i:02X}" for i in range(16)}
    missing = sorted(required - colours.keys())
    if missing:
        raise ThemeImportError("Base16 theme is missing: " + ", ".join(missing))
    return scheme, colours, metadata


def _base16_chrome(colours: dict[str, str]) -> dict[str, object]:
    b = colours
    selected_text = best_text_color(b["base02"], b["base05"], b["base06"], b["base07"], "#000000", "#FFFFFF")
    active_text = best_text_color(b["base02"], b["base05"], b["base06"], b["base07"], "#000000", "#FFFFFF")
    return {
        **DEFAULT_CHROME,
        "background": b["base00"], "panel_bg": b["base01"], "field_bg": b["base00"],
        "foreground": b["base05"], "muted_fg": b["base03"], "field_fg": b["base05"],
        "button_bg": b["base02"], "button_fg": best_text_color(b["base02"], b["base05"], b["base06"], b["base07"]),
        "active_bg": b["base02"], "active_fg": active_text,
        "selection_bg": b["base02"], "selection_fg": selected_text,
        "disabled_fg": b["base04"], "accent": b["base0D"], "secondary_accent": b["base0E"],
        "tab_bg": b["base01"], "tab_selected_bg": b["base02"],
        "scrollbar_bg": b["base03"], "scrollbar_trough": b["base01"],
        "scale_bg": b["base01"], "scale_trough": b["base02"],
        "preview_bg": b["base00"], "preview_fg": best_text_color(b["base00"], b["base05"], b["base06"], b["base07"]),
        "success_fg": b["base0B"], "warning_fg": b["base0A"], "failure_fg": b["base08"], "running_fg": b["base0C"],
        "sash_color": b["base03"], "panel_edge": b["base03"],
        "tooltip_bg": b["base02"], "tooltip_fg": best_text_color(b["base02"], b["base05"], b["base06"], b["base07"]),
    }


def _parse_base16(raw: bytes) -> ImportedTheme:
    name, colours, metadata = _parse_flat_base16(raw)
    extras = {key: value for key, value in colours.items() if int(key[4:], 16) >= 16}
    diagnostics = (ThemeDiagnostic("base24-extra", "info", f"Preserved {len(extras)} Base24 extension colours"),) if extras else ()
    return _imported(name, _base16_chrome(colours), "base16", metadata, diagnostics,
                     extensions={"base24": extras} if extras else {})


def _first_colour_from_tokens(data: object) -> str | None:
    if isinstance(data, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", data):
        return _colour(data)
    if isinstance(data, dict):
        for value in data.values():
            found = _first_colour_from_tokens(value)
            if found:
                return found
    if isinstance(data, list):
        for value in data:
            found = _first_colour_from_tokens(value)
            if found:
                return found
    return None


def _parse_vscode(raw: bytes) -> ImportedTheme:
    data = _json_object(raw, jsonc=True)
    name = str(data.get("name") or "Imported VS Code Theme")[:120]
    colors = data.get("colors") or {}
    if not isinstance(colors, dict) or len(colors) > MAX_ENTRIES:
        raise ThemeImportError("VS Code colors must be a bounded object")
    def get(*keys: str, fallback: str | None = None) -> str | None:
        for key in keys:
            value = colors.get(key)
            if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", value):
                return _colour(value[:7])
        return fallback
    bg = get("editor.background", "sideBar.background", "panel.background", fallback=str(DEFAULT_CHROME["background"]))
    fg = get("editor.foreground", "foreground", "sideBar.foreground", fallback=best_text_color(str(bg)))
    panel = get("sideBar.background", "panel.background", "editorGroupHeader.tabsBackground", fallback=str(bg))
    field = get("input.background", "dropdown.background", fallback=str(bg))
    button = get("button.background", fallback=get("list.hoverBackground", fallback=str(panel)))
    selection = get("list.activeSelectionBackground", "editor.selectionBackground", fallback=get("focusBorder", fallback=str(button)))
    accent = get("focusBorder", "button.background", "activityBarBadge.background") or _first_colour_from_tokens(data.get("tokenColors")) or str(DEFAULT_CHROME["accent"])
    secondary = _first_colour_from_tokens(data.get("semanticTokenColors")) or _first_colour_from_tokens(data.get("tokenColors")) or str(DEFAULT_CHROME["secondary_accent"])
    chrome = {
        **DEFAULT_CHROME,
        "background": bg, "panel_bg": panel, "field_bg": field, "foreground": fg, "muted_fg": get("descriptionForeground", fallback=str(DEFAULT_CHROME["muted_fg"])),
        "field_fg": get("input.foreground", fallback=fg), "button_bg": button, "button_fg": get("button.foreground", fallback=best_text_color(str(button))),
        "active_bg": get("list.hoverBackground", "list.focusBackground", fallback=str(button)),
        "active_fg": get("list.hoverForeground", fallback=fg),
        "selection_bg": selection, "selection_fg": get("list.activeSelectionForeground", fallback=best_text_color(str(selection))),
        "disabled_fg": get("disabledForeground", fallback=str(DEFAULT_CHROME["disabled_fg"])),
        "accent": accent, "secondary_accent": secondary,
        "tab_bg": get("tab.inactiveBackground", "editorGroupHeader.tabsBackground", fallback=str(panel)),
        "tab_selected_bg": get("tab.activeBackground", fallback=str(selection)),
        "scrollbar_bg": get("scrollbarSlider.background", fallback=str(DEFAULT_CHROME["scrollbar_bg"])),
        "scrollbar_trough": panel, "scale_bg": panel, "scale_trough": selection,
        "preview_bg": bg, "preview_fg": fg,
        "failure_fg": get("errorForeground", fallback=str(DEFAULT_CHROME["failure_fg"])),
        "warning_fg": get("editorWarning.foreground", fallback=str(DEFAULT_CHROME["warning_fg"])),
        "success_fg": get("gitDecoration.addedResourceForeground", fallback=str(DEFAULT_CHROME["success_fg"])),
        "running_fg": get("progressBar.background", fallback=str(accent)),
        "sash_color": get("sash.hoverBorder", fallback=str(accent)),
        "panel_edge": get("panel.border", "contrastBorder", fallback=str(DEFAULT_CHROME["panel_edge"])),
        "tooltip_bg": get("editorHoverWidget.background", fallback=str(panel)),
        "tooltip_fg": get("editorHoverWidget.foreground", fallback=fg),
    }
    return _imported(name, chrome, "vscode", {"name": name},
                     (ThemeDiagnostic("vscode-workbench", "info", "Mapped Workbench/UI colours before syntax token colours"),))


def _parse_textmate(raw: bytes) -> ImportedTheme:
    upper = raw.upper()
    if b"<!ENTITY" in upper:
        raise ThemeImportError("TextMate entity declarations are not supported")
    if b"<!DOCTYPE" in upper and b"APPLE//DTD PLIST 1.0//EN" not in upper:
        raise ThemeImportError("Custom TextMate document types are not supported")
    try:
        data = plistlib.loads(raw)
    except Exception as exc:
        raise ThemeImportError(f"Invalid TextMate plist: {exc}") from exc
    if not isinstance(data, dict):
        raise ThemeImportError("TextMate theme must be a plist dictionary")
    settings = data.get("settings") or []
    if not isinstance(settings, list) or len(settings) > 4096:
        raise ThemeImportError("TextMate settings must be a bounded array")
    globals_: dict[str, object] = {}
    scoped: list[str] = []
    for row in settings:
        if not isinstance(row, dict):
            continue
        opts = row.get("settings") or {}
        if not isinstance(opts, dict):
            continue
        if not row.get("scope"):
            globals_.update(opts)
        else:
            value = opts.get("foreground")
            if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                scoped.append(_colour(value))
    bg = _colour(globals_.get("background"), str(DEFAULT_CHROME["background"]))
    fg = _colour(globals_.get("foreground"), best_text_color(bg))
    selection = _colour(globals_.get("selection"), str(DEFAULT_CHROME["selection_bg"]))
    accent = scoped[0] if scoped else str(DEFAULT_CHROME["accent"])
    secondary = scoped[1] if len(scoped) > 1 else accent
    chrome = {
        **DEFAULT_CHROME,
        "background": bg, "panel_bg": bg, "field_bg": bg, "foreground": fg, "field_fg": fg,
        "selection_bg": selection, "selection_fg": best_text_color(selection, fg, "#000000", "#FFFFFF"),
        "accent": accent, "secondary_accent": secondary,
        "preview_bg": bg, "preview_fg": fg,
        "tooltip_bg": bg, "tooltip_fg": fg,
    }
    name = str(data.get("name") or "Imported TextMate Theme")[:120]
    return _imported(name, chrome, "textmate", {"name": name},
                     (ThemeDiagnostic("textmate-global-first", "info", "Mapped TextMate global settings before scoped syntax colours"),))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


def _parse_gpl(raw: bytes) -> ImportedTheme:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ThemeImportError("GIMP palette must be UTF-8") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "GIMP Palette":
        raise ThemeImportError("Not a GIMP GPL palette")
    name = "Imported GIMP Palette"
    colours: list[tuple[int, int, int]] = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.lower().startswith("columns:"):
            continue
        if stripped.lower().startswith("name:"):
            name = stripped.split(":", 1)[1].strip()[:120] or name
            continue
        match = re.match(r"^(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})(?:\s+.*)?$", stripped)
        if not match:
            raise ThemeImportError(f"Invalid GPL palette row: {stripped[:80]}")
        rgb = tuple(map(int, match.groups()))
        if any(v > 255 for v in rgb):
            raise ThemeImportError("GPL RGB components must be 0..255")
        colours.append(rgb)  # type: ignore[arg-type]
        if len(colours) > MAX_PALETTE:
            raise ThemeImportError("GPL palette has too many colours")
    if len(colours) < 2:
        raise ThemeImportError("GPL palette needs at least two colours")
    by_lum = sorted(colours, key=lambda c: relative_luminance(_rgb_to_hex(c)))
    median = by_lum[len(by_lum) // 2]
    dark_mode = relative_luminance(_rgb_to_hex(median)) < 0.45
    background = _rgb_to_hex(by_lum[0] if dark_mode else by_lum[-1])
    foreground = _rgb_to_hex(by_lum[-1] if dark_mode else by_lum[0])
    # Structural candidates are low saturation; accents are the most saturated.
    def sat(c: tuple[int, int, int]) -> float:
        return colorsys.rgb_to_hsv(*(v / 255 for v in c))[1]
    low = sorted(colours, key=lambda c: (sat(c), abs(relative_luminance(_rgb_to_hex(c)) - relative_luminance(background))))
    high = sorted(colours, key=lambda c: (sat(c), relative_luminance(_rgb_to_hex(c))), reverse=True)
    panel = _rgb_to_hex(low[min(1, len(low) - 1)])
    field = background
    button = _rgb_to_hex(low[min(2, len(low) - 1)])
    accent = _rgb_to_hex(high[0])
    secondary = _rgb_to_hex(high[1] if len(high) > 1 else high[0])
    selection = accent
    chrome = {
        **DEFAULT_CHROME,
        "background": background, "panel_bg": panel, "field_bg": field,
        "foreground": foreground, "field_fg": foreground,
        "muted_fg": best_text_color(panel, foreground, str(DEFAULT_CHROME["muted_fg"])),
        "button_bg": button, "button_fg": best_text_color(button, foreground, "#000000", "#FFFFFF"),
        "active_bg": button, "active_fg": best_text_color(button, foreground, "#000000", "#FFFFFF"),
        "selection_bg": selection, "selection_fg": best_text_color(selection, foreground, "#000000", "#FFFFFF"),
        "accent": accent, "secondary_accent": secondary,
        "tab_bg": panel, "tab_selected_bg": selection,
        "preview_bg": background, "preview_fg": foreground,
        "tooltip_bg": button, "tooltip_fg": best_text_color(button, foreground, "#000000", "#FFFFFF"),
    }
    return _imported(name, chrome, "gimp-gpl", {"name": name},
                     (ThemeDiagnostic("palette-derived", "info", "Semantic UI roles were derived from a colour-only GPL palette"),))


def import_theme_bytes(filename: str, raw: bytes) -> ImportedTheme:
    if not isinstance(raw, (bytes, bytearray)):
        raise ThemeImportError("Theme input must be bytes")
    if len(raw) > MAX_THEME_BYTES:
        raise ThemeImportError("Theme file exceeds the 1 MiB import limit")
    fmt = detect_theme_format(filename, bytes(raw))
    if fmt == "native":
        return _parse_native(bytes(raw))
    if fmt == "base16":
        return _parse_base16(bytes(raw))
    if fmt == "vscode":
        return _parse_vscode(bytes(raw))
    if fmt == "textmate":
        return _parse_textmate(bytes(raw))
    if fmt == "gimp-gpl":
        return _parse_gpl(bytes(raw))
    raise ThemeImportError("Unsupported theme format")


def import_theme_file(path: str | os.PathLike[str]) -> ImportedTheme:
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise ThemeImportError(str(exc)) from exc
    if size > MAX_THEME_BYTES:
        raise ThemeImportError("Theme file exceeds the 1 MiB import limit")
    return import_theme_bytes(p.name, p.read_bytes())


def export_native_theme(path: str | os.PathLike[str], name: str, appearance: str,
                        chrome: dict[str, object], *, source: dict[str, str] | None = None,
                        extensions: dict[str, object] | None = None, overwrite: bool = False) -> Path:
    p = Path(path)
    if p.exists() and not overwrite:
        raise FileExistsError(p)
    resolved = _validate_chrome(chrome)
    if appearance not in {"dark", "light"}:
        appearance = _appearance(str(resolved["background"]))
    payload = {
        "format": NATIVE_FORMAT,
        "version": NATIVE_VERSION,
        "name": str(name).strip()[:120] or "Exported Theme",
        "appearance": appearance,
        "source": dict(source or {"format": "omne-retrospector"}),
        "chrome": resolved,
        "extensions": dict(extensions or {}),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=p.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, p)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return p
