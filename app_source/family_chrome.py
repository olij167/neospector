"""Neospector visual instrument welcome and theme hosting; the original Theme Studio is unchanged."""
import copy,webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from ui_chrome import ThemeStudio,import_theme_dialog
APP='Neospector'
from release_identity import VERSION
WEBSITE_URL='https://omne.space/'
SUPPORT_URL='https://omne.space/support'
class FamilyChromeMixin:
    def refresh_theme_choices(self):
        self.available_themes=list(dict.fromkeys(self.published_themes+list(self.user_themes)))
        if hasattr(self,'theme_preset_combo'):self.theme_preset_combo.configure(values=self.available_themes)
        if self.startup_window and self.startup_window.winfo_exists():
            try:self.startup_theme_combo.configure(values=self.available_themes)
            except Exception:pass

    def apply_welcome_theme(self,name):
        """One committed selection path for Welcome and the Appearance editor."""
        if name not in self.available_themes:return False
        prefs=getattr(self,'preferences_window',None)
        if prefs is not None and prefs.winfo_exists() and hasattr(prefs,'theme_editor'):
            editor=prefs.theme_editor
            editor.base.set(name)
            editor.load_base()  # matches the Appearance tab's live preview
            editor.persist()    # explicit Welcome selection commits immediately
        else:
            self.apply_theme(name,save=True)
        return True

    def open_theme_studio(self):
        # UX36: Theme Studio and Appearance are one editor and one window.
        return self.open_preferences('appearance')

    def open_theme_import(self):import_theme_dialog(self)

    def show_startup_window(self,force=False):
        from welcome_ui import show
        return show(self,force)

    def set_tooltips(self):
        enabled=bool(self.tooltips_enabled.get())
        for tip in self.tip_instances:tip.set_enabled(enabled)
        self.save_preferences()
