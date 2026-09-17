#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_scope_sync_v74_runner.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
base = Path(__file__).resolve().with_name("patch_chat_scope_sync_v74.py")
if not base.exists():
    raise SystemExit(f"Missing base v7.4 patch: {base}")

source = base.read_text(encoding="utf-8")

# Earlier UI/search patches can alter whitespace and neighbouring WM_COMMAND
# cases around the custom chat-search handler. Rewrite only the v7.4 Python
# source section that depended on that surrounding text; the generated C++
# target itself is the unique rebuild_chat_combo_by_name(query) call.
start_marker = '# Search edit: local filtering in My chats, contacts.search in All chats.\n'
end_marker = '# Selecting a server result clones it into a stable read-only Peer.'
start = source.find(start_marker)
end = source.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("Could not locate v7.4 search-routing source section.")

replacement = r"""# Search edit: local filtering in My chats, contacts.search in All chats.
route_call = "\t\t\trebuild_chat_combo_by_name(query);"
route_new = r'''\t\t\tif (global_chat_search_mode)
\t\t\t\tglobal_chat_search_begin(query);
\t\t\telse
\t\t\t\trebuild_chat_combo_by_name(query);'''.replace('\\t', '\t')
if s.count(route_call) != 1:
    raise SystemExit(
        f"Could not route chat search by scope: expected one local-search call, found {s.count(route_call)}."
    )
s = s.replace(route_call, route_new, 1)

"""
source = source[:start] + replacement + source[end:]

# Media/player patches add their own WM_TIMER branches before v7.4 runs, so the
# old v7.4 source could no longer match "case WM_TIMER + if (wParam == 0)" as one
# exact block. Keep the status-bar timer creation, then inject our timer branch
# immediately after the switch label without making assumptions about existing
# timer order.
start_marker = '# Periodic missed-update reconciliation. The existing client already knows how\n'
end_marker = '# Replace the top-control resize block installed by patch_telegacy.py.'
start = source.find(start_marker)
end = source.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("Could not locate v7.4 periodic-sync source section.")

replacement = r"""# Periodic missed-update reconciliation. The existing client already knows how
# to parse updates.getDifference; it simply only did this at startup. Reuse that
# proven path every 45 seconds and when Telegram says updatesTooLong.
status_anchor = "\t\thStatus = CreateWindow(STATUSCLASSNAME, NULL, WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS, 0, 0, 0, 0, hWnd, NULL, NULL, NULL);"
if status_anchor not in s:
    raise SystemExit("Could not locate status-bar creation for sync timer.")
s = s.replace(
    status_anchor,
    status_anchor + "\n\t\tSetTimer(hWnd, 3013, 45000, NULL); // chat_scope_sync_v74",
    1,
)

timer_anchor = "\tcase WM_TIMER:"
timer_new = r'''\tcase WM_TIMER:
\t\tif (wParam == 3013) {
\t\t\ttelegacy_request_difference_sync();
\t\t\tbreak;
\t\t}'''.replace('\\t', '\t')
if s.count(timer_anchor) != 1:
    raise SystemExit(
        f"Could not locate unique main WM_TIMER switch label; found {s.count(timer_anchor)}."
    )
s = s.replace(timer_anchor, timer_new, 1)

"""
source = source[:start] + replacement + source[end:]

# Telegacy's source tree is intentionally round-tripped as latin-1. Emit the
# Russian labels as C++ universal-character names so the generated source stays
# byte-safe while the compiled wide strings remain proper Unicode.
write_anchor = "write(t, s)\n\n# ---------------------------------------------------------------------------\n# response.cpp: contacts.Found + missed-update recovery/completion."
write_replacement = r'''s = s.replace(
    "Мои чаты",
    r"\u041c\u043e\u0438 \u0447\u0430\u0442\u044b"
)
s = s.replace(
    "Все чаты",
    r"\u0412\u0441\u0435 \u0447\u0430\u0442\u044b"
)
s = s.replace(
    "Поиск публичных каналов...",
    r"\u041f\u043e\u0438\u0441\u043a \u043f\u0443\u0431\u043b\u0438\u0447\u043d\u044b\u0445 \u043a\u0430\u043d\u0430\u043b\u043e\u0432..."
)
s = s.replace(
    "Поиск моих чатов...",
    r"\u041f\u043e\u0438\u0441\u043a \u043c\u043e\u0438\u0445 \u0447\u0430\u0442\u043e\u0432..."
)
write(t, s)

# ---------------------------------------------------------------------------
# response.cpp: contacts.Found + missed-update recovery/completion.'''
if write_anchor not in source:
    raise SystemExit("Could not locate v7.4 telegacy.cpp write boundary.")
source = source.replace(write_anchor, write_replacement, 1)

# Adjust only the verification tokens to look for the literal universal names
# now present in the generated ANSI-compatible source.
source = source.replace(
    '        "Мои чаты",\n        "Все чаты",',
    '        r"\\u041c\\u043e\\u0438 \\u0447\\u0430\\u0442\\u044b",\n'
    '        r"\\u0412\\u0441\\u0435 \\u0447\\u0430\\u0442\\u044b",',
    1,
)

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
