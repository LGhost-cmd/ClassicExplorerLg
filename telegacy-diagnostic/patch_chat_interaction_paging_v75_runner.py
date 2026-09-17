#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_interaction_paging_v75_runner.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
base = Path(__file__).resolve().with_name("patch_chat_interaction_paging_v75.py")
if not base.exists():
    raise SystemExit(f"Missing base v7.5 patch: {base}")

source = base.read_text(encoding="utf-8")

# Search-context v2 rebalances the in-chat search row before v7.5 runs, so the
# base v7.5 geometry targets from the original search/media patch are no longer
# present. Replace only the Python source section responsible for second-row
# geometry; all other v7.5 behavior remains unchanged.
start_marker = "# Second row: 12-13px gaps between search, arrows and Media. Media ends 10px\n"
end_marker = "write(t, s)\n\n# ---------------------------------------------------------------------------\n# RichEdit direct mouse retry and scroll-top pagination trigger."
start = source.find(start_marker)
end = source.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("Could not locate v7.5 second-row layout source section.")

replacement = r'''# Second row: preserve the result-count label introduced by search-context v2,
# but give every control a real 15-pixel visual gap and keep Media 10px from the
# right edge. At the minimum 500px window width the message search still keeps
# 180px of usable width.
second_row_rules = [
    (r"width\s*-\s*260", "width - 320", 2, "message search width"),
    (r"width\s*-\s*245", "width - 295", 2, "search result status x"),
    (r"width\s*-\s*175", "width - 225", 2, "previous button x"),
    (r"width\s*-\s*135", "width - 175", 2, "next button x"),
    (r"width\s*-\s*95", "width - 125", 2, "Media button x"),
]
for pattern, replacement_text, expected, label in second_row_rules:
    s, count = re.subn(pattern, replacement_text, s)
    if count != expected:
        raise SystemExit(
            f"Could not relax second-row spacing for {label}: expected {expected}, found {count}."
        )

status_width_pattern = re.compile(
    r"(width\s*-\s*295,\s*40,\s*)65(,\s*22)",
    re.MULTILINE,
)
s, status_width_count = status_width_pattern.subn(r"\g<1>55\2", s)
if status_width_count != 2:
    raise SystemExit(
        f"Could not resize search-result status: expected 2, found {status_width_count}."
    )

media_width_pattern = re.compile(
    r"(width\s*-\s*125,\s*40,\s*)85(,\s*22)",
    re.MULTILINE,
)
s, media_width_count = media_width_pattern.subn(r"\g<1>115\2", s)
if media_width_count != 2:
    raise SystemExit(
        f"Could not widen Media button after repositioning: expected 2, found {media_width_count}."
    )

'''
source = source[:start] + replacement + source[end:]

old_checks = '''        "width - 280",\n        "width - 258",\n        "width - 200",\n        "width - 142",'''
new_checks = '''        "width - 320",\n        "width - 295",\n        "width - 225",\n        "width - 175",\n        "width - 125",'''
if old_checks not in source:
    raise SystemExit("Could not locate v7.5 second-row verification tokens.")
source = source.replace(old_checks, new_checks, 1)

old_argv = sys.argv[:]
namespace = {
    "__name__": "__main__",
    "__file__": str(base),
}
try:
    sys.argv = [str(base), str(root)]
    exec(compile(source, str(base), "exec"), namespace, namespace)
finally:
    sys.argv = old_argv
