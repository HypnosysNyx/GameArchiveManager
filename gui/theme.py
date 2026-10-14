"""Colour choices for the graphical interface."""


def system_prefers_dark() -> bool:
    """Read Windows' AppsUseLightTheme preference, defaulting to light."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            apps_use_light_theme, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return not bool(apps_use_light_theme)
    except (ImportError, OSError):
        return False


def resolved_appearance(choice: str, prefers_dark: bool | None = None) -> str:
    """Resolve an explicit or system-following appearance choice."""
    if choice == "auto":
        return "dark" if (system_prefers_dark() if prefers_dark is None else prefers_dark) else "light"
    if choice in {"light", "dark"}:
        return choice
    raise ValueError("choice must be 'auto', 'light', or 'dark'")


def palette(appearance: str) -> dict[str, str]:
    """Return the colours used by a resolved light or dark appearance."""
    palettes = {
        "light": {
            "bg": "#f3f3f3",
            "fg": "#1a1a1a",
            "muted": "#5c5c5c",
            "border": "#e5e5e5",
            "accent": "#0067c0",
            "accent_fg": "#ffffff",
            "surface": "#ffffff",
            "entry_bg": "#ffffff",
            "corner_radius": 8,
            "danger": "#b42318",
            "ok": "#18794e",
        },
        "dark": {
            "bg": "#1e1e1e",
            "fg": "#f2f2f2",
            "muted": "#bdbdbd",
            "border": "#3a3a3a",
            "accent": "#4cc2ff",
            "accent_fg": "#06202b",
            "surface": "#2a2a2a",
            "entry_bg": "#141414",
            "corner_radius": 4,
            "danger": "#ff8a80",
            "ok": "#6ee7a0",
        },
    }
    try:
        return palettes[appearance].copy()
    except KeyError as error:
        raise ValueError("appearance must be 'light' or 'dark'") from error
