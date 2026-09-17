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

# The exact whitespace around case 3000 is changed by several earlier UI/search
# patches. Keep the v7.4 implementation itself intact, but make this one source
# transformation target the unique call rather than the surrounding case block.
start_marker = '# Search edit: local filtering in My chats, contacts.search in All chats.\n'
end_marker = '# Selecting a server result clones it into a stable read-only Peer.'
start = source.find(start_marker)
end = source.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("Could not locate v7.4 search-routing source section.")

replacement = r'''# Search edit: local filtering in My chats, contacts.search in All chats.
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

'''

source = source[:start] + replacement + source[end:]

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
