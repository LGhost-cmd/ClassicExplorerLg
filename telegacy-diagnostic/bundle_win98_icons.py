#!/usr/bin/env python3
"""Bundle actual classic Windows icon PNGs from the archived Win98 icon collection.

Source: https://github.com/alexh/vintage-icons/tree/main/static/icons
This is third-party visual content, not original Telegacy artwork.
"""
from pathlib import Path
import io, sys, urllib.request
from PIL import Image

root = Path(sys.argv[1]) if len(sys.argv)>1 else Path("artifact/icons98")
root.mkdir(parents=True, exist_ok=True)
selected = {
    "search":"magnifying_glass_0.png",
    "profile":"address_book_card.png",
    "options":"directory_control_panel_0.png",
    "media":"camera_0.png",
    "chats":"message_envelope_open_0.png",
    "notifications":"msg_information_0.png",
}
base = "https://raw.githubusercontent.com/alexh/vintage-icons/main/static/icons/"
for action, name in selected.items():
    with urllib.request.urlopen(base+name,timeout=30) as resp:
        data = resp.read()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("Not a PNG: " + name)
    src = Image.open(io.BytesIO(data)).convert("RGBA")
    # Preserve hard-edged native 1990s shapes. Each source is already pixel art.
    icon = src.resize((32,32),Image.Resampling.NEAREST)
    icon.save(root / f"{action}.ico", format="ICO", sizes=[(16,16),(32,32)])
    (root / f"{action}.png").write_bytes(data)
(root/"SOURCES.txt").write_text(
    "Classic Windows icon assets for Telegacy Concept98.\n"
    "Source: https://github.com/alexh/vintage-icons/tree/main/static/icons\n"
    "Windows 98 icons by their original rights holders. Used for the\n"
    "user-requested personal retro UI. Redistribution rights are not\n"
    "granted by this asset manifest.\n"
    "Telegacy action names map to upstream files:\n"+
    "".join(f"{k}: {v}\n" for k,v in selected.items()),
    encoding="utf-8",
)
print("Bundled",len(selected),"classic Win98 icon pairs",root)
