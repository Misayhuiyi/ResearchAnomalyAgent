"""Windows extended paths for local files; never use this for URL validation."""
import os
from pathlib import Path


def filesystem_path(value):
    path=Path(value).resolve()
    text=str(path)
    if os.name!='nt' or text.startswith('\\\\?\\'): return path
    return Path('\\\\?\\UNC\\'+text[2:] if text.startswith('\\\\') else '\\\\?\\'+text)


def display_path(value):
    text=str(value)
    if text.startswith('\\\\?\\UNC\\'): return '\\\\'+text[8:]
    return text[4:] if text.startswith('\\\\?\\') else text
