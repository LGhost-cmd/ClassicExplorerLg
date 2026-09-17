#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_scope_sync_v74.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"

for p in (h, t, r):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy file: {p}")


def read(p):
    return p.read_text(encoding="latin-1")


def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")


if "chat_scope_sync_v74" in read(t):
    print("Chat scope/sync v7.4 already applied.")
    raise SystemExit(0)

if "dialog_rows_v72" not in read(t):
    raise SystemExit("Dialog rows v7.2 must be applied before v7.4.")
if "media_inplace_upgrade_v73" not in read(t):
    raise SystemExit("Media in-place upgrade v7.3 must be applied before v7.4.")

# ---------------------------------------------------------------------------
# Header: response.cpp needs the global-search result parser and sync hooks.
# ---------------------------------------------------------------------------
s = read(h)
anchor = "void telegacy_hide_phantom_chat_rows(); // dialog_rows_v72"
if anchor not in s:
    raise SystemExit("Could not locate v7.2 header declaration.")
extra = r'''
bool global_chat_search_handle_found(BYTE* response, int length); // chat_scope_sync_v74
bool global_chat_search_is_result_peer(Peer* peer); // chat_scope_sync_v74
void telegacy_request_difference_sync(); // chat_scope_sync_v74
void telegacy_sync_note_response(const BYTE* rpc_id); // chat_scope_sync_v74'''
s = s.replace(anchor, anchor + extra, 1)
write(h, s)

# ---------------------------------------------------------------------------
# telegacy.cpp: extend the existing local chat-search subsystem.
# ---------------------------------------------------------------------------
s = read(t)
base = "HWND hChatSearch = NULL;\nbool chat_search_updating = false;"
if base not in s:
    raise SystemExit("Could not locate custom chat-search globals.")

runtime = r'''HWND hChatSearch = NULL;
bool chat_search_updating = false;

// chat_scope_sync_v74
HWND hChatScopeTabs = NULL;
static bool global_chat_search_mode = false;
static bool global_chat_search_pending = false;
static BYTE global_chat_search_rpc_id[8] = {0};
static std::vector<Peer> global_chat_search_results;
static std::vector<Peer*> global_chat_search_opened;

static bool telegacy_sync_pending = false;
static BYTE telegacy_sync_rpc_id[8] = {0};

bool global_chat_search_is_result_peer(Peer* peer) {
    if (!peer)
        return false;

    for (int i = 0; i < (int)global_chat_search_results.size(); i++) {
        if (peer == &global_chat_search_results[i])
            return true;
    }

    for (int i = 0; i < (int)global_chat_search_opened.size(); i++) {
        if (peer == global_chat_search_opened[i])
            return true;
    }

    return false;
}

static void global_chat_search_free_result(Peer* peer) {
    if (!peer)
        return;

    free(peer->name);
    peer->name = NULL;
    free(peer->handle);
    peer->handle = NULL;
}

static void global_chat_search_clear_results() {
    for (int i = 0; i < (int)global_chat_search_results.size(); i++)
        global_chat_search_free_result(&global_chat_search_results[i]);

    global_chat_search_results.clear();
    global_chat_search_pending = false;
    memset(global_chat_search_rpc_id, 0, sizeof(global_chat_search_rpc_id));

    if (global_chat_search_mode && hComboBoxChats)
        SendMessage(hComboBoxChats, CB_RESETCONTENT, 0, 0);
}

static void global_chat_search_rebuild_combo() {
    if (!global_chat_search_mode || !hComboBoxChats)
        return;

    SendMessage(hComboBoxChats, CB_RESETCONTENT, 0, 0);

    for (int i = 0; i < (int)global_chat_search_results.size(); i++) {
        Peer* peer = &global_chat_search_results[i];
        if (!peer->name || !peer->name[0])
            continue;

        LRESULT item = SendMessage(
            hComboBoxChats,
            CB_ADDSTRING,
            0,
            (LPARAM)peer->name
        );

        if (item != CB_ERR && item != CB_ERRSPACE) {
            SendMessage(
                hComboBoxChats,
                CB_SETITEMDATA,
                item,
                (LPARAM)peer
            );
        }
    }

    telegacy_hide_phantom_chat_rows();
}

static void global_chat_search_begin(const wchar_t* query) {
    global_chat_search_clear_results();

    if (!query || lstrlenW(query) < 2)
        return;

    wchar_t q[256] = {0};
    lstrcpynW(q, query, ARRAYSIZE(q));

    BYTE unenc_query[2048] = {0};
    BYTE enc_query[2072] = {0};

    internal_header(unenc_query, true);
    write_le(unenc_query + 32, 0x11f812d8, 4); // contacts.search
    write_string(unenc_query + 36, q);

    int offset = 36 + tlstr_len(unenc_query + 36, true);
    if (offset + 4 >= (int)sizeof(unenc_query))
        return;

    write_le(unenc_query + offset, 50, 4);
    offset += 4;
    write_le(unenc_query + 28, offset - 32, 4);

    int padding = get_padding(offset);
    if (
        padding < 0 ||
        offset + padding > (int)sizeof(unenc_query) ||
        offset + padding + 24 > (int)sizeof(enc_query)
    ) {
        return;
    }

    fortuna_read(unenc_query + offset, padding, &prng);
    offset += padding;

    if (!convert_message(unenc_query, enc_query, offset, 0))
        return;

    memcpy(global_chat_search_rpc_id, unenc_query + 16, 8);
    global_chat_search_pending = send_query(enc_query, offset + 24) > 0;

    diag_log(
        "chat v74 global search sent chars=%d pending=%d",
        lstrlenW(q),
        global_chat_search_pending ? 1 : 0
    );
}

static int global_chat_search_skip_peer_vector(
    BYTE* response,
    int length,
    int offset
) {
    if (
        !response ||
        offset < 0 ||
        offset + 8 > length ||
        read_le(response + offset, 4) != 0x1cb5c415
    ) {
        return -1;
    }

    int count = read_le(response + offset + 4, 4);
    if (count < 0 || count > 10000)
        return -1;

    __int64 end = (__int64)offset + 8 + (__int64)count * 12;
    if (end > length)
        return -1;

    return (int)end;
}

static int global_chat_search_nonfull_chat_size(
    BYTE* object,
    int available
) {
    if (!object || available < 12)
        return -1;

    unsigned int ctor = read_le(object, 4);

    if (ctor == 0x29562865) // chatEmpty
        return 12;

    if (ctor == 0x6592a1a7) { // chatForbidden
        if (available < 13)
            return -1;
        int title = tlstr_len(object + 12, true);
        return title > 0 && 12 + title <= available ? 12 + title : -1;
    }

    if (ctor == 0x17d493d5) { // channelForbidden
        if (available < 25)
            return -1;
        int flags = read_le(object + 4, 4);
        int title = tlstr_len(object + 24, true);
        int total = 24 + title + ((flags & (1 << 16)) ? 4 : 0);
        return title > 0 && total <= available ? total : -1;
    }

    return -1;
}

bool global_chat_search_handle_found(BYTE* response, int length) {
    if (!response || length < 4 || read_le(response, 4) != 0xb3134d9d)
        return false;

    // Old, out-of-order search responses are intentionally swallowed. They must
    // never replace the results for the most recently typed query.
    if (
        !global_chat_search_pending ||
        memcmp(last_rpcresult_msgid, global_chat_search_rpc_id, 8) != 0
    ) {
        diag_log("chat v74 ignored stale contacts.found");
        return true;
    }

    global_chat_search_pending = false;

    for (int i = 0; i < (int)global_chat_search_results.size(); i++)
        global_chat_search_free_result(&global_chat_search_results[i]);
    global_chat_search_results.clear();

    int offset = 4;
    offset = global_chat_search_skip_peer_vector(response, length, offset);
    if (offset < 0)
        return true;
    offset = global_chat_search_skip_peer_vector(response, length, offset);
    if (offset < 0)
        return true;

    if (
        offset + 8 > length ||
        read_le(response + offset, 4) != 0x1cb5c415
    ) {
        return true;
    }

    int chat_count = read_le(response + offset + 4, 4);
    offset += 8;

    if (chat_count < 0 || chat_count > 1000)
        return true;

    for (int i = 0; i < chat_count && offset + 4 <= length; i++) {
        unsigned int ctor = read_le(response + offset, 4);
        int consumed = 0;

        if (ctor == 0xe00998b7) { // channel (Telegacy layer 196)
            Peer peer = {0};
            peer.type = 2;
            consumed = set_peer_info(response + offset, &peer, false);

            if (consumed <= 0 || consumed > length - offset) {
                global_chat_search_free_result(&peer);
                break;
            }

            // Global public results are opened as read-only peers. This avoids
            // adding a channel the user merely searched for to the persisted
            // dialog database while still allowing messages.getHistory.
            peer.full = true;
            peer.perm.cansendmsg = false;
            peer.perm.cansendmed = false;
            peer.perm.cansendvoice = false;
            peer.perm.cansendphoto = false;
            peer.perm.cansendvideo = false;
            peer.perm.cansendaudio = false;
            peer.perm.cansenddocs = false;
            peer.reaction_list = NULL;
            peer.chat_users = NULL;

            if (peer.name && peer.name[0])
                global_chat_search_results.push_back(peer);
            else
                global_chat_search_free_result(&peer);
        } else if (ctor == 0x41cbf256) { // basic chat; parse only to advance
            Peer peer = {0};
            peer.type = 1;
            consumed = set_peer_info(response + offset, &peer, false);
            global_chat_search_free_result(&peer);
            if (consumed <= 0 || consumed > length - offset)
                break;
        } else {
            consumed = global_chat_search_nonfull_chat_size(
                response + offset,
                length - offset
            );
            if (consumed <= 0) {
                diag_log(
                    "chat v74 stopped on unsupported Chat ctor=0x%08X index=%d",
                    ctor,
                    i
                );
                break;
            }
        }

        offset += consumed;
    }

    diag_log(
        "chat v74 global search parsed channels=%d",
        (int)global_chat_search_results.size()
    );

    global_chat_search_rebuild_combo();
    return true;
}

static Peer* global_chat_search_open_peer(Peer* source) {
    if (!source)
        return NULL;

    // A result may already be one of the user's ordinary dialogs. Reuse the
    // canonical Peer in that case so unread state, permissions and metadata are
    // retained.
    for (int i = 0; i < peers_count; i++) {
        if (
            peers[i].type == source->type &&
            memcmp(peers[i].id, source->id, 8) == 0
        ) {
            return &peers[i];
        }
    }

    Peer* clone = (Peer*)calloc(1, sizeof(Peer));
    if (!clone)
        return NULL;

    *clone = *source;
    clone->name = source->name ? _wcsdup(source->name) : NULL;
    clone->handle = source->handle ? _wcsdup(source->handle) : NULL;
    clone->about = NULL;
    clone->chat_users = NULL;
    clone->reaction_list = NULL;
    clone->full = true;
    clone->perm.cansendmsg = false;
    clone->perm.cansendmed = false;
    clone->perm.cansendvoice = false;
    clone->perm.cansendphoto = false;
    clone->perm.cansendvideo = false;
    clone->perm.cansendaudio = false;
    clone->perm.cansenddocs = false;

    if (!clone->name) {
        free(clone->handle);
        free(clone);
        return NULL;
    }

    global_chat_search_opened.push_back(clone);
    return clone;
}

void telegacy_request_difference_sync() {
    if (
        telegacy_sync_pending ||
        !dcInfoMain.authorized ||
        !read_le(dcInfoMain.future_salt, 8) ||
        pts <= 0
    ) {
        return;
    }

    BYTE unenc_query[64] = {0};
    BYTE enc_query[88] = {0};

    internal_header(unenc_query, true);
    memcpy(telegacy_sync_rpc_id, unenc_query + 16, 8);
    write_le(unenc_query + 28, 20, 4);
    write_le(unenc_query + 32, 0x19c2f763, 4); // updates.getDifference
    memset(unenc_query + 36, 0, 4);
    write_le(unenc_query + 40, pts, 4);
    write_le(unenc_query + 44, date, 4);
    write_le(unenc_query + 48, qts, 4);
    fortuna_read(unenc_query + 52, 12, &prng);

    if (!convert_message(unenc_query, enc_query, 64, 0))
        return;

    telegacy_sync_pending = send_query(enc_query, 88) > 0;

    if (telegacy_sync_pending)
        diag_log("chat v74 periodic getDifference pts=%d date=%d qts=%d", pts, date, qts);
}

void telegacy_sync_note_response(const BYTE* rpc_id) {
    if (
        telegacy_sync_pending &&
        rpc_id &&
        memcmp(rpc_id, telegacy_sync_rpc_id, 8) == 0
    ) {
        telegacy_sync_pending = false;
        memset(telegacy_sync_rpc_id, 0, sizeof(telegacy_sync_rpc_id));
        diag_log("chat v74 periodic sync completed");
    }
}
'''

s = s.replace(base, runtime, 1)

# Local search in "My chats" searches the complete account dialog list rather
# than only the currently selected Telegram folder. With an empty query the
# selected folder is still shown normally.
old = r'''    if (!current_folder)
        return;

    for (int i = 0; i < current_folder->count; i++) {
        Peer* peer =
            &peers[current_folder->peers[i]];'''
new = r'''    ChatsFolder* source_folder = current_folder;

    if (
        query && query[0] &&
        folders && folders_count > 0
    ) {
        source_folder = &folders[0];
    }

    if (!source_folder)
        return;

    for (int i = 0; i < source_folder->count; i++) {
        Peer* peer =
            &peers[source_folder->peers[i]];'''
if old not in s:
    raise SystemExit("Could not widen local chat search to all loaded dialogs.")
s = s.replace(old, new, 1)

# v7.2's phantom-row predicate originally accepted only pointers inside the
# persisted peers array. Global server results deliberately live outside that
# array, so mark those pointers as legitimate combo rows as well.
old = r'''    bool known = false;

    for (int i = 0; i < peers_count; i++) {'''
new = r'''    bool known = global_chat_search_is_result_peer(peer);

    for (int i = 0; i < peers_count && !known; i++) {'''
if old not in s:
    raise SystemExit("Could not extend v7.2 peer validity predicate.")
s = s.replace(old, new, 1)

# Actual two-scope tab control in the main top bar.
create_anchor = "\t\thComboBoxFolders = CreateWindow("
if create_anchor not in s:
    raise SystemExit("Could not locate top-bar folder combo creation.")
create_tabs = r'''		hChatScopeTabs = CreateWindowW(
			WC_TABCONTROLW,
			L"",
			WS_CHILD | WS_VISIBLE | TCS_FIXEDWIDTH | TCS_FOCUSNEVER,
			10, 7, 180, 29,
			hWnd,
			(HMENU)3010,
			NULL,
			NULL
		);

		if (hChatScopeTabs) {
			TCITEMW scope_item = {0};
			scope_item.mask = TCIF_TEXT;
			scope_item.pszText =
				(LANG[0] == 'R' && LANG[1] == 'U')
					? (LPWSTR)L"Мои чаты"
					: (LPWSTR)L"My chats";
			TabCtrl_InsertItem(hChatScopeTabs, 0, &scope_item);
			scope_item.pszText =
				(LANG[0] == 'R' && LANG[1] == 'U')
					? (LPWSTR)L"Все чаты"
					: (LPWSTR)L"All chats";
			TabCtrl_InsertItem(hChatScopeTabs, 1, &scope_item);
			TabCtrl_SetCurSel(hChatScopeTabs, 0);
			SendMessage(hChatScopeTabs, TCM_SETITEMSIZE, 0, MAKELPARAM(84, 21));
		}

'''
s = s.replace(create_anchor, create_tabs + create_anchor, 1)

# Move the existing three controls to the right of the new scope tabs.
for old_coord, new_coord, label in (
    ("\t\t\t10, 10, 115, 300,", "\t\t\t195, 10, 115, 300,", "folder combo"),
    ("\t\t\t130, 10, 130, 22,", "\t\t\t315, 10, 150, 22,", "chat search"),
    ("\t\t\t265, 10, width - 275, 300,", "\t\t\t470, 10, width - 480, 300,", "chat combo"),
):
    if old_coord not in s:
        raise SystemExit(f"Could not relocate {label} for v7.4.")
    s = s.replace(old_coord, new_coord, 1)

# Search edit: local filtering in My chats, contacts.search in All chats.
old = "\t\t\trebuild_chat_combo_by_name(query);\n\n\t\t\tbreak;\n\t\t}\n\n\t\tcase 3: {"
new = r'''			if (global_chat_search_mode)
				global_chat_search_begin(query);
			else
				rebuild_chat_combo_by_name(query);

			break;
		}

		case 3: {'''
if old not in s:
    raise SystemExit("Could not route chat search by scope.")
s = s.replace(old, new, 1)

# Selecting a server result clones it into a stable read-only Peer. We do not
# add it to peers/folders, so searching a public channel does not pretend the
# user is subscribed to it or persist it into database.dat.
selection_anchor = r'''\t\t\tif (
\t\t\t\t!selected_peer ||
\t\t\t\tselected_peer == (Peer*)CB_ERR
\t\t\t) {
\t\t\t\tbreak;
\t\t\t}

\t\t\tif (
\t\t\t\tlParam &&'''.replace('\\t', '\t')
selection_new = r'''\t\t\tif (
\t\t\t\t!selected_peer ||
\t\t\t\tselected_peer == (Peer*)CB_ERR
\t\t\t) {
\t\t\t\tbreak;
\t\t\t}

\t\t\tif (global_chat_search_mode) {
\t\t\t\tselected_peer = global_chat_search_open_peer(selected_peer);
\t\t\t\tif (!selected_peer)
\t\t\t\t\tbreak;
\t\t\t}

\t\t\tif (
\t\t\t\tlParam &&'''.replace('\\t', '\t')
if selection_anchor not in s:
    raise SystemExit("Could not locate filtered chat selection validation.")
s = s.replace(selection_anchor, selection_new, 1)

# Handle scope tab changes ahead of the existing RichEdit notification chain.
notify_anchor = "\t\tif (pNMHDR->hwndFrom == chat && pNMHDR->code == EN_LINK"
notify_new = r'''		if (
			pNMHDR->hwndFrom == hChatScopeTabs &&
			pNMHDR->code == TCN_SELCHANGE
		) {
			global_chat_search_mode =
				TabCtrl_GetCurSel(hChatScopeTabs) == 1;

			EnableWindow(
				hComboBoxFolders,
				global_chat_search_mode ? FALSE : TRUE
			);

			chat_search_updating = true;
			SetWindowTextW(hChatSearch, L"");
			chat_search_updating = false;

			if (global_chat_search_mode) {
				global_chat_search_clear_results();
				SendMessageW(
					hChatSearch,
					EM_SETCUEBANNER,
					TRUE,
					(LPARAM)(
						(LANG[0] == 'R' && LANG[1] == 'U')
							? L"Поиск публичных каналов..."
							: L"Search public channels..."
					)
				);
				SetFocus(hChatSearch);
			} else {
				SendMessageW(
					hChatSearch,
					EM_SETCUEBANNER,
					TRUE,
					(LPARAM)(
						(LANG[0] == 'R' && LANG[1] == 'U')
							? L"Поиск моих чатов..."
							: L"Search my chats..."
					)
				);
				rebuild_chat_combo_by_name(L"");
			}

			break;
		} else if (pNMHDR->hwndFrom == chat && pNMHDR->code == EN_LINK'''
if notify_anchor not in s:
    raise SystemExit("Could not locate WM_NOTIFY chat EN_LINK branch.")
s = s.replace(notify_anchor, notify_new, 1)

# Periodic missed-update reconciliation. The existing client already knows how
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

timer_anchor = "\tcase WM_TIMER:\n\t\tif (wParam == 0) {"
timer_new = r'''	case WM_TIMER:
		if (wParam == 3013) {
			telegacy_request_difference_sync();
		} else if (wParam == 0) {'''
if timer_anchor not in s:
    raise SystemExit("Could not locate main WM_TIMER handler.")
s = s.replace(timer_anchor, timer_new, 1)

# Replace the top-control resize block installed by patch_telegacy.py.
resize_old = r'''			hdwp = DeferWindowPos(
				hdwp,
				hComboBoxFolders,
				NULL,
				10,
				10,
				115,
				300,
				SWP_NOZORDER
			);

			hdwp = DeferWindowPos(
				hdwp,
				hChatSearch,
				NULL,
				130,
				10,
				130,
				22,
				SWP_NOZORDER
			);

			hdwp = DeferWindowPos(
				hdwp,
				hComboBoxChats,
				NULL,
				265,
				10,
				width - 275,
				300,
				SWP_NOZORDER
			);'''.replace('\\t', '\t')
resize_new = r'''			hdwp = DeferWindowPos(
				hdwp, hChatScopeTabs, NULL,
				10, 7, 180, 29, SWP_NOZORDER
			);
			hdwp = DeferWindowPos(
				hdwp, hComboBoxFolders, NULL,
				195, 10, 115, 300, SWP_NOZORDER
			);
			hdwp = DeferWindowPos(
				hdwp, hChatSearch, NULL,
				315, 10, 150, 22, SWP_NOZORDER
			);
			hdwp = DeferWindowPos(
				hdwp, hComboBoxChats, NULL,
				470, 10, width - 480, 300, SWP_NOZORDER
			);'''.replace('\\t', '\t')
if resize_old not in s:
    raise SystemExit("Could not locate patched top-control WM_SIZE block.")
s = s.replace(resize_old, resize_new, 1)

write(t, s)

# ---------------------------------------------------------------------------
# response.cpp: contacts.Found + missed-update recovery/completion.
# ---------------------------------------------------------------------------
s = read(r)

# Telegram global search result constructor.
case_anchor = "\tcase 0x99622c0c: { // peerNotifySettings"
case_insert = r'''	case 0xb3134d9d: { // contacts.found - chat_scope_sync_v74
		global_chat_search_handle_found(unenc_response, length);
		break;
	}
'''.replace('\\t', '\t')
if case_anchor not in s:
    raise SystemExit("Could not locate response case insertion point.")
s = s.replace(case_anchor, case_insert + case_anchor, 1)

# Telegacy 1.0.4 ignored updatesTooLong entirely, which can leave the visible
# state frozen until restart. Request getDifference immediately instead.
old = "\tcase 0xe317af7e: // updatesTooLong\n\t\tbreak;"
new = r'''	case 0xe317af7e: // updatesTooLong
		telegacy_request_difference_sync(); // chat_scope_sync_v74
		break;'''.replace('\\t', '\t')
if old not in s:
    raise SystemExit("Could not locate updatesTooLong handler.")
s = s.replace(old, new, 1)

# The v7.1 response boundary plus v7.2 row refresh is a stable place to release
# our periodic-sync pending flag after the matching rpc_result has completed.
anchor = "        telegacy_hide_phantom_chat_rows();"
if anchor not in s:
    raise SystemExit("Could not locate v7.2 response-boundary refresh.")
s = s.replace(
    anchor,
    anchor + "\n        telegacy_sync_note_response(last_rpcresult_msgid); // chat_scope_sync_v74",
    1,
)
write(r, s)

checks = {
    h: [
        "global_chat_search_handle_found",
        "telegacy_request_difference_sync",
    ],
    t: [
        "chat_scope_sync_v74",
        "contacts.search",
        "global_chat_search_mode",
        "WC_TABCONTROLW",
        "Мои чаты",
        "Все чаты",
        "telegacy_request_difference_sync()",
        "wParam == 3013",
        "source_folder = &folders[0]",
    ],
    r: [
        "contacts.found - chat_scope_sync_v74",
        "updatesTooLong",
        "telegacy_sync_note_response(last_rpcresult_msgid)",
    ],
}
for p, tokens in checks.items():
    data = read(p)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"v7.4 verification failed in {p.name}: {token}")

print(
    "Applied chat scope/sync v7.4: My chats searches every loaded account dialog, "
    "All chats uses Telegram contacts.search for public channels without persisting "
    "search-only peers, and a periodic/updateTooLong getDifference reconciliation "
    "keeps fresh server state flowing into the legacy client."
)
