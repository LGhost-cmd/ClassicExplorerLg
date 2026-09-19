#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_global_peer_photo_hit_v79.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"
p = root / "src" / "procs.cpp"
r = root / "src" / "response.cpp"

for path in (t, p, r):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


def function_range(source, signature):
    start = source.find(signature)
    if start < 0:
        raise SystemExit(f"Could not locate C++ function: {signature}")

    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not locate opening brace: {signature}")

    depth = 0
    in_string = False
    in_char = False
    in_line = False
    in_block = False
    escaped = False
    i = brace

    while i < len(source):
        c = source[i]
        n = source[i + 1] if i + 1 < len(source) else ""

        if in_line:
            if c == "\n":
                in_line = False
            i += 1
            continue

        if in_block:
            if c == "*" and n == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            i += 1
            continue

        if in_char:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == "'":
                in_char = False
            i += 1
            continue

        if c == "/" and n == "/":
            in_line = True
            i += 2
            continue
        if c == "/" and n == "*":
            in_block = True
            i += 2
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "'":
            in_char = True
            i += 1
            continue

        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1

        i += 1

    raise SystemExit(f"Could not locate closing brace: {signature}")


if "chat_global_peer_photo_hit_v79" in read(t):
    print("Chat global peer/photo hit v7.9 already applied.")
    raise SystemExit(0)

for token, path in (
    ("chat_photo_click_download_v78", t),
    ("chat_channel_media_layout_v77", t),
    ("chat_scope_sync_v74", t),
    ("chat_photo_click_download_proc_v78", p),
    ("media_chat_full_photo_retry_migrated", r),
):
    if token not in read(path):
        raise SystemExit(f"Required predecessor marker missing in {path.name}: {token}")

# =============================================================================
# 1) contacts.search: do not use legacy set_peer_info()'s returned byte count.
#
# Layer 196 channel#e00998b7 contains flags2 and optional tail objects including
# default_banned_rights#9f120418. Telegacy's set_peer_info() is useful for its
# own persisted peer database, but its return offset intentionally stops before
# several modern tail fields. v7.4 incorrectly used that return value to walk
# Vector<Chat>, so 0x9f120418 could be mistaken for the next Chat constructor.
#
# Instead, collect the exact peerChannel IDs from contacts.Found's two Peer
# vectors, scan for matching channel objects, and read only the stable leading
# fields required for InputPeerChannel: id, access_hash, title and username.
# =============================================================================
s = read(t)

old_start, old_end = function_range(
    s,
    "bool global_chat_search_handle_found("
)

new_handler = r'''bool global_chat_search_handle_found(
    BYTE* response,
    int length
) {
    if (
        !response ||
        length < 4 ||
        read_le(response, 4) != 0xb3134d9d
    ) {
        return false;
    }

    if (
        !global_chat_search_pending ||
        memcmp(
            last_rpcresult_msgid,
            global_chat_search_rpc_id,
            8
        ) != 0
    ) {
        diag_log(
            "chat v79 ignored stale contacts.found"
        );
        return true;
    }

    global_chat_search_pending = false;

    for (
        int i = 0;
        i < (int)global_chat_search_results.size();
        i++
    ) {
        global_chat_search_free_result(
            &global_chat_search_results[i]
        );
    }

    global_chat_search_results.clear();

    std::vector<__int64> wanted_channels;

    int offset = 4;

    for (int vector_index = 0; vector_index < 2; vector_index++) {
        if (
            offset < 0 ||
            offset + 8 > length ||
            read_le(response + offset, 4) != 0x1cb5c415
        ) {
            diag_log(
                "chat v79 contacts.found peer vector invalid index=%d offset=%d",
                vector_index,
                offset
            );
            global_chat_search_rebuild_combo();
            return true;
        }

        int count =
            read_le(response + offset + 4, 4);

        if (
            count < 0 ||
            count > 10000 ||
            (__int64)offset + 8 + (__int64)count * 12 > length
        ) {
            diag_log(
                "chat v79 contacts.found peer count invalid index=%d count=%d",
                vector_index,
                count
            );
            global_chat_search_rebuild_combo();
            return true;
        }

        int item = offset + 8;

        for (int i = 0; i < count; i++, item += 12) {
            unsigned int peer_ctor =
                read_le(response + item, 4);

            // peerChannel#a2a5371e channel_id:long
            if (peer_ctor != 0xa2a5371e)
                continue;

            __int64 channel_id =
                (__int64)read_le(
                    response + item + 4,
                    8
                );

            bool duplicate = false;

            for (
                int j = 0;
                j < (int)wanted_channels.size();
                j++
            ) {
                if (wanted_channels[j] == channel_id) {
                    duplicate = true;
                    break;
                }
            }

            if (!duplicate)
                wanted_channels.push_back(channel_id);
        }

        offset += 8 + count * 12;
    }

    if (
        offset + 8 > length ||
        read_le(response + offset, 4) != 0x1cb5c415
    ) {
        diag_log(
            "chat v79 contacts.found chats vector missing offset=%d",
            offset
        );
        global_chat_search_rebuild_combo();
        return true;
    }

    int chat_count =
        read_le(response + offset + 4, 4);

    int scan_start = offset + 8;

    if (chat_count < 0 || chat_count > 1000) {
        diag_log(
            "chat v79 contacts.found chat count invalid=%d",
            chat_count
        );
        global_chat_search_rebuild_combo();
        return true;
    }

    int matched = 0;
    int skipped_no_hash = 0;

    for (
        int wanted_index = 0;
        wanted_index < (int)wanted_channels.size();
        wanted_index++
    ) {
        __int64 wanted_id =
            wanted_channels[wanted_index];

        int channel_offset = -1;

        // TL objects are 4-byte aligned. Searching for the exact layer-196
        // constructor plus the requested 64-bit ID is safer than trusting the
        // legacy set_peer_info() tail offset.
        for (
            int probe = scan_start;
            probe + 28 <= length;
            probe += 4
        ) {
            if (
                read_le(response + probe, 4) == 0xe00998b7 &&
                (__int64)read_le(
                    response + probe + 12,
                    8
                ) == wanted_id
            ) {
                channel_offset = probe;
                break;
            }
        }

        if (channel_offset < 0)
            continue;

        int flags =
            read_le(response + channel_offset + 4, 4);

        int cursor =
            channel_offset + 20; // ctor + flags + flags2 + id

        BYTE access_hash[8] = {0};

        if (flags & (1 << 13)) {
            if (cursor + 8 > length)
                continue;

            // Unlike legacy set_peer_info(), this must be copied even for a
            // min channel because a temporary search result has no old hash to
            // preserve.
            memcpy(
                access_hash,
                response + cursor,
                8
            );

            cursor += 8;
        }

        if (cursor >= length)
            continue;

        int title_tl =
            tlstr_len(
                response + cursor,
                true
            );

        if (
            title_tl <= 0 ||
            cursor + title_tl > length
        ) {
            continue;
        }

        wchar_t* title =
            read_string(
                response + cursor,
                NULL
            );

        cursor += title_tl;

        wchar_t* username = NULL;

        if (flags & (1 << 6)) {
            if (cursor >= length) {
                free(title);
                continue;
            }

            int username_tl =
                tlstr_len(
                    response + cursor,
                    true
                );

            if (
                username_tl <= 0 ||
                cursor + username_tl > length
            ) {
                free(title);
                continue;
            }

            username =
                read_string(
                    response + cursor,
                    NULL
                );
        }

        // If Telegram sent a min constructor without a hash, reuse the
        // canonical hash only when this channel is already in the local peer DB.
        if (!read_le(access_hash, 8)) {
            for (int j = 0; j < peers_count; j++) {
                if (
                    peers[j].type == 2 &&
                    (__int64)read_le(
                        peers[j].id,
                        8
                    ) == wanted_id &&
                    read_le(
                        peers[j].access_hash,
                        8
                    )
                ) {
                    memcpy(
                        access_hash,
                        peers[j].access_hash,
                        8
                    );
                    break;
                }
            }
        }

        if (!read_le(access_hash, 8)) {
            skipped_no_hash++;

            diag_log(
                "chat v79 skipped global channel without access_hash id=%I64d min=%d",
                wanted_id,
                (flags & (1 << 12)) ? 1 : 0
            );

            free(title);
            free(username);
            continue;
        }

        Peer peer = {0};
        peer.type = 2;
        peer.full = true;
        peer.name = title;
        peer.handle = username;
        memcpy(peer.id, &wanted_id, 8);
        memcpy(peer.access_hash, access_hash, 8);
        peer.reaction_list = NULL;
        peer.chat_users = NULL;

        peer.perm.cansendmsg = false;
        peer.perm.cansendmed = false;
        peer.perm.cansendvoice = false;
        peer.perm.cansendphoto = false;
        peer.perm.cansendvideo = false;
        peer.perm.cansendaudio = false;
        peer.perm.cansenddocs = false;
        peer.perm.canchangedesc = false;

        if (peer.name && peer.name[0]) {
            global_chat_search_results.push_back(peer);
            matched++;
        } else {
            global_chat_search_free_result(&peer);
        }
    }

    diag_log(
        "chat v79 global search peer_channels=%d chat_objects=%d matched=%d skipped_no_hash=%d",
        (int)wanted_channels.size(),
        chat_count,
        matched,
        skipped_no_hash
    );

    global_chat_search_rebuild_combo();
    return true;
}'''

s = s[:old_start] + new_handler + s[old_end:]

# Runtime marker used by CI and logs.
marker_anchor = "// chat_scope_sync_v74"
if marker_anchor not in s:
    raise SystemExit("Could not locate global-search marker.")
s = s.replace(
    marker_anchor,
    marker_anchor + "\n// chat_global_peer_photo_hit_v79",
    1,
)

# =============================================================================
# 2) Photo hit testing: bind clicks to the actual RichEdit OLE object.
#
# v7.8 still relied primarily on Document::min/max. Those coordinates can drift
# after prepends/replacements; the log then contains no v7.8 click entry even
# though the visible low-res OLE was clicked. Locate the clicked OLE card first
# and map its real cp to the nearest Document. This also refuses video Documents
# so the proven video handler keeps ownership of video cards.
# =============================================================================
handler_start, handler_end = function_range(
    s,
    "bool media_chat_photo_handle_chat_mouse("
)

new_photo_handler = r'''static int media_chat_v79_clicked_photo_document(
    POINT point
) {
    if (!chat)
        return -1;

    int clicked_cp = -1;

    IRichEditOle* ole = NULL;

    SendMessageW(
        chat,
        EM_GETOLEINTERFACE,
        0,
        (LPARAM)&ole
    );

    if (ole) {
        LONG object_count =
            ole->GetObjectCount();

        int effective_dpi =
            dpi > 0
                ? dpi
                : 96;

        int card_width =
            MulDiv(
                288,
                effective_dpi,
                96
            );

        int card_height =
            MulDiv(
                216,
                effective_dpi,
                96
            );

        for (
            LONG i = 0;
            i < object_count;
            i++
        ) {
            REOBJECT reo = {0};
            reo.cbStruct = sizeof(reo);

            if (
                FAILED(
                    ole->GetObject(
                        i,
                        &reo,
                        REO_GETOBJ_NO_INTERFACES
                    )
                )
            ) {
                continue;
            }

            POINTL origin = {0, 0};

            if (
                SendMessageW(
                    chat,
                    EM_POSFROMCHAR,
                    (WPARAM)&origin,
                    (LPARAM)reo.cp
                ) == -1
            ) {
                continue;
            }

            RECT card = {
                (LONG)origin.x,
                (LONG)origin.y,
                (LONG)origin.x + card_width,
                (LONG)origin.y + card_height
            };

            if (
                PtInRect(
                    &card,
                    point
                )
            ) {
                clicked_cp =
                    (int)reo.cp;
                break;
            }
        }

        ole->Release();
    }

    if (clicked_cp < 0) {
        LRESULT raw_hit =
            SendMessageW(
                chat,
                EM_CHARFROMPOS,
                0,
                (LPARAM)&point
            );

        if (raw_hit >= 0)
            clicked_cp = (int)raw_hit;
    }

    if (clicked_cp < 0)
        return -1;

    int best = -1;
    int best_distance = INT_MAX;

    for (
        int i = 0;
        i < (int)documents.size();
        i++
    ) {
        Document* document =
            &documents[i];

        if (
            !document->visible ||
            !document->file_reference ||
            document->photo_size == 0 ||
            document->photo_size == 1
        ) {
            continue;
        }

        int distance = 0;

        if (
            clicked_cp < document->min
        ) {
            distance =
                document->min - clicked_cp;
        } else if (
            clicked_cp > document->max
        ) {
            distance =
                clicked_cp - document->max;
        }

        if (distance < best_distance) {
            best_distance = distance;
            best = i;
        }
    }

    if (
        best < 0 ||
        best_distance > 192
    ) {
        diag_log(
            "chat v79 OLE click unmapped cp=%d distance=%d",
            clicked_cp,
            best_distance
        );
        return -1;
    }

    // Do not steal video cards from media_chat_video_handle_chat_mouse().
    if (documents[best].photo_size == 3)
        return -1;

    diag_log(
        "chat v79 OLE click mapped cp=%d document=%d range=%d..%d distance=%d",
        clicked_cp,
        best,
        documents[best].min,
        documents[best].max,
        best_distance
    );

    return best;
}

static bool media_chat_full_photo_user_action(
    Document* document,
    bool save_and_open
);

bool media_chat_photo_handle_chat_mouse(
    HWND hWnd,
    UINT msg,
    WPARAM,
    LPARAM lParam
) {
    if (
        !chat ||
        hWnd != chat ||
        (
            msg != WM_LBUTTONDOWN &&
            msg != WM_LBUTTONDBLCLK
        )
    ) {
        return false;
    }

    POINT point = {
        GET_X_LPARAM(lParam),
        GET_Y_LPARAM(lParam)
    };

    int document_index =
        media_chat_v79_clicked_photo_document(
            point
        );

    if (
        document_index < 0 ||
        document_index >= (int)documents.size()
    ) {
        return false;
    }

    Document* document =
        &documents[document_index];

    bool save_and_open =
        msg == WM_LBUTTONDBLCLK;

    bool started =
        media_chat_full_photo_user_action(
            document,
            save_and_open
        );

    diag_log(
        "chat v79 photo click index=%d range=%d..%d double=%d started=%d",
        document_index,
        document->min,
        document->max,
        save_and_open ? 1 : 0,
        started ? 1 : 0
    );

    if (!started)
        MessageBeep(MB_ICONASTERISK);

    return true;
}'''

s = s[:handler_start] + new_photo_handler + s[handler_end:]

write(t, s)

# =============================================================================
# 3) Never leave getHistory permanently pending after a bad temporary peer.
# The v7.4 search clone is not part of peers[]. If Telegram rejects it with
# PEER_ID_INVALID/CHANNEL_INVALID, clear the latch immediately so switching
# chats and later history requests still work.
# =============================================================================
s = read(r)

rpc_case = s.find("case 0x2144ca19:")
if rpc_case < 0:
    raise SystemExit("Could not locate rpc_error case for v7.9.")

guard_anchor = s.find(
    "if (media_chat_full_photo_handle_rpc_error(",
    rpc_case
)
if guard_anchor < 0:
    raise SystemExit("Could not locate v7.6 rpc error guard.")

guard_end = s.find("\n\t\t}", guard_anchor)
if guard_end < 0:
    raise SystemExit("Could not isolate v7.6 rpc error guard.")
guard_end = s.find("\n", guard_end + 1)
if guard_end < 0:
    raise SystemExit("Could not locate line end after v7.6 rpc error guard.")
guard_end += 1

pending_guard = r'''
		if (
			error_code == 400 &&
			current_peer &&
			global_chat_search_is_result_peer(current_peer) &&
			(
				wcscmp(error_message, L"PEER_ID_INVALID") == 0 ||
				wcscmp(error_message, L"CHANNEL_INVALID") == 0
			)
		) {
			InterlockedExchange(&history_request_pending, 0);
			no_more_msgs = true;

			diag_log(
				"chat v79 invalid global peer released history pending error=%ls",
				error_message
			);
		}
'''.replace("\t", "	")

s = s[:guard_end] + pending_guard + s[guard_end:]

write(r, s)

# procs.cpp itself is unchanged, but keep the v7.8 direct interception as a
# required final invariant.
s = read(p)
if "chat_photo_click_download_proc_v78" not in s:
    raise SystemExit("v7.8 direct photo interception disappeared.")
write(p, s)

checks = {
    t: [
        "chat_global_peer_photo_hit_v79",
        "chat v79 global search peer_channels=",
        "0xa2a5371e",
        "0xe00998b7",
        "chat v79 OLE click mapped",
        "chat v79 photo click",
    ],
    r: [
        "chat v79 invalid global peer released history pending",
        "InterlockedExchange(&history_request_pending, 0)",
        'wcscmp(error_message, L"CHANNEL_INVALID")',
    ],
    p: [
        "chat_photo_click_download_proc_v78",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(
                f"v7.9 verification failed in {path.name}: {token}"
            )

print(
    "Applied chat global-peer/photo-hit v7.9: contacts.search channels are "
    "reconstructed from exact peerChannel IDs and stable layer-196 channel "
    "identity fields instead of a truncated legacy parser offset; min results "
    "retain access_hash; image clicks bind to the real RichEdit OLE card; and "
    "invalid temporary global peers cannot leave getHistory permanently pending."
)
