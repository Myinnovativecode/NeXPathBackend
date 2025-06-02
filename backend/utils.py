# utils.py (create this file if you don’t have one yet)
import unicodedata

def remove_invalid_characters(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return ''.join(c for c in text if unicodedata.category(c)[0] != 'C')  # Remove control chars, unprintables
