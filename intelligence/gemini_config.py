"""Shared Gemini model and private local credential lookup."""
import os

DEFAULT_MODEL = "gemini-3.5-flash-lite"


def api_key():
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if key or os.name != "nt":
        return key

    # The process may predate a change to Windows user environment variables.
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env:
            return winreg.QueryValueEx(env, "GOOGLE_API_KEY")[0]
    except OSError:
        return None
