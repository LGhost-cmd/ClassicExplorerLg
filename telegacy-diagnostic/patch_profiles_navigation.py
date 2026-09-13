#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_profiles_navigation.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
p = root / "src" / "procs.cpp"
m = root / "src" / "message.cpp"
r = root / "src" / "response.cpp"
helpers = root / "src" / "helpers.cpp"

for path in (h, p, m, r, helpers):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, text):
    path.write_text(text, encoding="latin-1", newline="\r\n")


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
    in_line_comment = False
    in_block_comment = False
    escaped = False
    i = brace

    while i < len(source):
        c = source[i]
        n = source[i + 1] if i + 1 < len(source) else ""

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if c == "*" and n == "/":
                in_block_comment = False
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
            in_line_comment = True
            i += 2
            continue
        if c == "/" and n == "*":
            in_block_comment = True
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


def replace_function(source, signature, replacement):
    start, end = function_range(source, signature)
    return source[:start] + replacement + source[end:]


# Idempotence.
if "profile_navigation_latvianghost_v1" in read(p):
    print("Profile navigation patch already applied.")
    raise SystemExit(0)

# =============================================================================
# telegacy.h — cross-file declarations
# =============================================================================
s = read(h)
anchor = "void get_pfp(DCInfo* dcInfo, Peer* peer);"
if anchor not in s:
    raise SystemExit("Could not locate get_pfp declaration in telegacy.h.")

s = s.replace(
    anchor,
    anchor
    + "\n\n// profile_navigation_latvianghost_v1"
    + "\nvoid profile_nav_register_message_sender(int message_id, const BYTE* peer_id, char peer_type);"
    + "\nvoid profile_nav_clear_message_senders();"
    + "\nvoid profile_gallery_begin(Peer* peer, HWND picture, HWND previous, HWND next, HWND counter);"
    + "\nvoid profile_gallery_step(int delta);"
    + "\nvoid profile_gallery_clear();"
    + "\nbool profile_gallery_handle_photos_response(const BYTE* request_id, BYTE* response, int length);"
    + "\nbool profile_gallery_handle_upload(const BYTE* request_id, BYTE* response, int length);"
    + "\nbool profile_gallery_retry_download(const BYTE* request_id, DCInfo* dcInfo);"
    + "\nbool profile_gallery_showing_current();",
    1,
)
write(h, s)

# =============================================================================
# helpers.cpp — user avatar history via photos.getUserPhotos + upload.getFile
# =============================================================================
s = read(helpers)
insert_pos = s.find("void get_pfp(DCInfo* dcInfo, Peer* peer) {")
if insert_pos < 0:
    raise SystemExit("Could not locate get_pfp definition in helpers.cpp.")

helpers_code = r'''
// profile_navigation_latvianghost_v1
struct TelegacyProfileGalleryPhoto {
    BYTE id[8];
    BYTE access_hash[8];
    BYTE* file_reference;
    int dc;
    char thumb_type;
};

static std::vector<TelegacyProfileGalleryPhoto> profile_gallery_photos;
static Peer* profile_gallery_peer = NULL;
static HWND profile_gallery_picture = NULL;
static HWND profile_gallery_previous = NULL;
static HWND profile_gallery_next = NULL;
static HWND profile_gallery_counter = NULL;
static int profile_gallery_index = 0;
static bool profile_gallery_active = false;
static bool profile_gallery_loading = false;
static BYTE profile_gallery_list_msgid[8] = {0};
static BYTE profile_gallery_file_msgid[8] = {0};

static void profile_gallery_free_entries() {
    for (int i = 0; i < (int)profile_gallery_photos.size(); i++) {
        free(profile_gallery_photos[i].file_reference);
        profile_gallery_photos[i].file_reference = NULL;
    }
    profile_gallery_photos.clear();
}

static void profile_gallery_update_controls() {
    int count = (int)profile_gallery_photos.size();
    bool multiple = profile_gallery_active && count > 1;

    if (profile_gallery_previous) {
        ShowWindow(profile_gallery_previous, multiple ? SW_SHOW : SW_HIDE);
        EnableWindow(
            profile_gallery_previous,
            multiple && !profile_gallery_loading && profile_gallery_index > 0
        );
    }

    if (profile_gallery_next) {
        ShowWindow(profile_gallery_next, multiple ? SW_SHOW : SW_HIDE);
        EnableWindow(
            profile_gallery_next,
            multiple && !profile_gallery_loading && profile_gallery_index + 1 < count
        );
    }

    if (profile_gallery_counter) {
        if (multiple) {
            wchar_t text[40] = {0};
            swprintf(text, L"%d / %d", profile_gallery_index + 1, count);
            SetWindowTextW(profile_gallery_counter, text);
            ShowWindow(profile_gallery_counter, SW_SHOW);
        } else {
            ShowWindow(profile_gallery_counter, SW_HIDE);
        }
    }
}

void profile_gallery_clear() {
    profile_gallery_free_entries();
    profile_gallery_peer = NULL;
    profile_gallery_picture = NULL;
    profile_gallery_previous = NULL;
    profile_gallery_next = NULL;
    profile_gallery_counter = NULL;
    profile_gallery_index = 0;
    profile_gallery_active = false;
    profile_gallery_loading = false;
    memset(profile_gallery_list_msgid, 0, sizeof(profile_gallery_list_msgid));
    memset(profile_gallery_file_msgid, 0, sizeof(profile_gallery_file_msgid));
}

static void profile_gallery_request_list(Peer* peer) {
    if (!peer || peer->type != 0)
        return;

    BYTE unenc_query[112] = {0};
    BYTE enc_query[136] = {0};

    internal_header(unenc_query, true);
    memcpy(profile_gallery_list_msgid, unenc_query + 16, 8);

    write_le(unenc_query + 32, 0x91cd32a8, 4); // photos.getUserPhotos
    int offset = 36;
    offset += place_peer(unenc_query + offset, peer, false); // InputUser
    write_le(unenc_query + offset, 0, 4); // offset
    offset += 4;
    memset(unenc_query + offset, 0, 8); // max_id:long
    offset += 8;
    write_le(unenc_query + offset, 50, 4); // enough for a useful gallery
    offset += 4;

    write_le(unenc_query + 28, offset - 32, 4);
    int padding = get_padding(offset);
    fortuna_read(unenc_query + offset, padding, &prng);
    offset += padding;

    convert_message(unenc_query, enc_query, offset, 0);
    send_query(enc_query, offset + 24);
}

void profile_gallery_begin(
    Peer* peer,
    HWND picture,
    HWND previous,
    HWND next,
    HWND counter
) {
    profile_gallery_clear();

    if (!peer || peer->type != 0)
        return;

    profile_gallery_peer = peer;
    profile_gallery_picture = picture;
    profile_gallery_previous = previous;
    profile_gallery_next = next;
    profile_gallery_counter = counter;
    profile_gallery_active = true;
    profile_gallery_index = 0;

    profile_gallery_update_controls();
    profile_gallery_request_list(peer);
}

static bool profile_gallery_parse_photo(
    BYTE* photo,
    TelegacyProfileGalleryPhoto* out
) {
    if (!photo || !out)
        return false;

    unsigned int constructor = (unsigned int)read_le(photo, 4);
    if (constructor == 0x2331b22d) // photoEmpty
        return false;

    int total = photo_offset(photo);
    if (total < 36)
        return false;

    memset(out, 0, sizeof(*out));
    memcpy(out->id, photo + 8, 8);
    memcpy(out->access_hash, photo + 16, 8);

    int file_ref_len = tlstr_len(photo + 24, true);
    if (file_ref_len <= 0 || file_ref_len > total - 24)
        return false;

    out->file_reference = (BYTE*)malloc(file_ref_len);
    if (!out->file_reference)
        return false;

    memcpy(out->file_reference, photo + 24, file_ref_len);
    out->dc = (int)read_le(photo + total - 4, 4);
    out->thumb_type = 0;

    int offset = 24 + file_ref_len;
    if (offset + 12 <= total) {
        offset += 4; // date

        if ((unsigned int)read_le(photo + offset, 4) == 0x1cb5c415) {
            int count = (int)read_le(photo + offset + 4, 4);
            offset += 8;

            int best_area = -1;
            char best_type = 0;
            bool found_medium = false;

            for (int i = 0; i < count && offset + 8 < total; i++) {
                BYTE* size = photo + offset;
                unsigned int size_constructor = (unsigned int)read_le(size, 4);
                int size_len = photo_video_size_offset(size, true, false, false);
                if (size_len <= 0 || offset + size_len > total)
                    break;

                char type = 0;
                BYTE* type_string = size + 4;
                if (type_string[0] == 1)
                    type = (char)type_string[1];

                int width = 0;
                int height = 0;
                int q = 4 + tlstr_len(type_string, true);

                if (
                    size_constructor == 0x75c78e60 || // photoSize
                    size_constructor == 0x21e1ad6 ||  // photoCachedSize
                    size_constructor == 0xfa3efb95    // photoSizeProgressive
                ) {
                    width = (int)read_le(size + q, 4);
                    height = (int)read_le(size + q + 4, 4);
                }

                if (type == 'm') {
                    best_type = type;
                    found_medium = true;
                } else if (!found_medium && type) {
                    int area = width > 0 && height > 0 ? width * height : 0;
                    if (area >= best_area) {
                        best_area = area;
                        best_type = type;
                    }
                }

                offset += size_len;
            }

            out->thumb_type = best_type ? best_type : 'm';
        }
    }

    if (!out->thumb_type)
        out->thumb_type = 'm';

    return true;
}

static bool profile_gallery_request_selected(DCInfo* dcInfo) {
    if (
        !profile_gallery_active ||
        !dcInfo ||
        profile_gallery_index < 0 ||
        profile_gallery_index >= (int)profile_gallery_photos.size()
    ) {
        return false;
    }

    TelegacyProfileGalleryPhoto* photo =
        &profile_gallery_photos[profile_gallery_index];

    BYTE unenc_query[160] = {0};
    BYTE enc_query[184] = {0};
    internal_header(dcInfo, unenc_query, true);
    memcpy(profile_gallery_file_msgid, unenc_query + 16, 8);

    write_le(unenc_query + 32, 0xbe5335be, 4); // upload.getFile
    write_le(unenc_query + 36, 0, 4);          // flags
    write_le(unenc_query + 40, 0x40181ffe, 4); // inputPhotoFileLocation
    memcpy(unenc_query + 44, photo->id, 8);
    memcpy(unenc_query + 52, photo->access_hash, 8);

    int ref_len = tlstr_len(photo->file_reference, true);
    memcpy(unenc_query + 60, photo->file_reference, ref_len);
    int offset = 60 + ref_len;

    memset(unenc_query + offset, 0, 4);
    unenc_query[offset] = 1;
    unenc_query[offset + 1] = photo->thumb_type;
    offset += 4;

    memset(unenc_query + offset, 0, 8); // offset:long
    offset += 8;
    write_le(unenc_query + offset, 1048576, 4);
    offset += 4;

    write_le(unenc_query + 28, offset - 32, 4);
    int padding = get_padding(offset);
    fortuna_read(unenc_query + offset, padding, &prng);
    offset += padding;

    convert_message(dcInfo, unenc_query, enc_query, offset, 0);
    profile_gallery_loading = true;
    profile_gallery_update_controls();
    send_query(dcInfo, enc_query, offset + 24);
    return true;
}

void profile_gallery_step(int delta) {
    if (
        !profile_gallery_active ||
        profile_gallery_loading ||
        profile_gallery_photos.size() < 2
    ) {
        return;
    }

    int next = profile_gallery_index + delta;
    if (next < 0 || next >= (int)profile_gallery_photos.size()) {
        MessageBeep(MB_ICONASTERISK);
        return;
    }

    profile_gallery_index = next;
    profile_gallery_update_controls();

    if (!profile_gallery_request_selected(&dcInfoMain)) {
        profile_gallery_loading = false;
        profile_gallery_update_controls();
    }
}

bool profile_gallery_handle_photos_response(
    const BYTE* request_id,
    BYTE* response,
    int length
) {
    if (!request_id || memcmp(request_id, profile_gallery_list_msgid, 8) != 0)
        return false;

    memset(profile_gallery_list_msgid, 0, sizeof(profile_gallery_list_msgid));

    if (!profile_gallery_active || !response || length < 12)
        return true;

    profile_gallery_free_entries();
    profile_gallery_index = 0;

    unsigned int constructor = (unsigned int)read_le(response, 4);
    int offset = 4;

    if (constructor == 0x15051f54) // photos.photosSlice
        offset += 4; // total count
    else if (constructor != 0x8dca6aa5) // photos.photos
        return true;

    if (
        offset + 8 > length ||
        (unsigned int)read_le(response + offset, 4) != 0x1cb5c415
    ) {
        profile_gallery_update_controls();
        return true;
    }

    int count = (int)read_le(response + offset + 4, 4);
    offset += 8;

    for (int i = 0; i < count && offset + 4 < length; i++) {
        int photo_len = photo_offset(response + offset);
        if (photo_len <= 0 || offset + photo_len > length)
            break;

        TelegacyProfileGalleryPhoto entry;
        if (profile_gallery_parse_photo(response + offset, &entry))
            profile_gallery_photos.push_back(entry);

        offset += photo_len;
    }

    profile_gallery_loading = false;
    profile_gallery_update_controls();

    // If this user currently has no avatar but has older photos, show the
    // first available gallery entry instead of the empty placeholder.
    if (
        profile_gallery_peer &&
        !read_le(profile_gallery_peer->photo, 8) &&
        !profile_gallery_photos.empty()
    ) {
        profile_gallery_request_selected(&dcInfoMain);
    }

    diag_log(
        "profile gallery loaded count=%d",
        (int)profile_gallery_photos.size()
    );

    return true;
}

bool profile_gallery_handle_upload(
    const BYTE* request_id,
    BYTE* response,
    int length
) {
    if (!request_id || memcmp(request_id, profile_gallery_file_msgid, 8) != 0)
        return false;

    memset(profile_gallery_file_msgid, 0, sizeof(profile_gallery_file_msgid));
    profile_gallery_loading = false;

    if (
        !profile_gallery_active ||
        !profile_gallery_picture ||
        !IsWindow(profile_gallery_picture) ||
        !response ||
        length < 16
    ) {
        profile_gallery_update_controls();
        return true;
    }

    int bytes_len = tlstr_len(response + 12, false);
    int header = bytes_len >= 254 ? 4 : 1;
    if (bytes_len <= 0 || 12 + header + bytes_len > length) {
        profile_gallery_update_controls();
        return true;
    }

    HBITMAP bitmap = jpg_to_bmp(response + 12 + header, bytes_len);
    if (bitmap) {
        HBITMAP old = (HBITMAP)SendMessageW(
            profile_gallery_picture,
            STM_SETIMAGE,
            IMAGE_BITMAP,
            (LPARAM)bitmap
        );

        if (old && old != bitmap)
            DeleteObject(old);
    }

    profile_gallery_update_controls();
    return true;
}

bool profile_gallery_retry_download(
    const BYTE* request_id,
    DCInfo* dcInfo
) {
    if (
        !request_id ||
        !dcInfo ||
        memcmp(request_id, profile_gallery_file_msgid, 8) != 0
    ) {
        return false;
    }

    return profile_gallery_request_selected(dcInfo);
}

bool profile_gallery_showing_current() {
    return !profile_gallery_active || profile_gallery_index == 0;
}

'''
s = s[:insert_pos] + helpers_code + s[insert_pos:]
write(helpers, s)

# =============================================================================
# message.cpp — remember the sender behind each visible message header
# =============================================================================
s = read(m)

sender_anchor = '''\tbool chat_member_found = true;\n\twchar_t* sender = current_peer->name;'''
if sender_anchor not in s:
    raise SystemExit("Could not locate sender-resolution block in message.cpp.")

sender_new = '''\tBYTE profile_sender_id[8] = {0};\n\tchar profile_sender_type = -1;\n\tbool profile_sender_valid = false;\n\n\tif (message.outgoing) {\n\t\tmemcpy(profile_sender_id, myself.id, 8);\n\t\tprofile_sender_type = 0;\n\t\tprofile_sender_valid = true;\n\t} else if (current_peer && current_peer->type == 0) {\n\t\tmemcpy(profile_sender_id, current_peer->id, 8);\n\t\tprofile_sender_type = 0;\n\t\tprofile_sender_valid = true;\n\t} else if (chat_member_id) {\n\t\tmemcpy(profile_sender_id, chat_member_id, 8);\n\t\tunsigned int from_constructor = (unsigned int)read_le(chat_member_id - 4, 4);\n\t\tif (from_constructor == 0x59511722) profile_sender_type = 0;\n\t\telse if (from_constructor == 0x36c6019a) profile_sender_type = 1;\n\t\telse if (from_constructor == 0xa2a5371e) profile_sender_type = 2;\n\t\telse if (current_peer->type == 1) profile_sender_type = 0;\n\t\tprofile_sender_valid = profile_sender_type >= 0;\n\t}\n\n\tbool chat_member_found = true;\n\twchar_t* sender = current_peer->name;'''
s = s.replace(sender_anchor, sender_new, 1)

position_anchor = '''\tmessage.start_char = cr_startmsg.cpMin;\n\tmessage.end_header = message.start_char + header_len;\n\tmessage.end_char = message.start_char + written - written_info;'''
if position_anchor not in s:
    raise SystemExit("Could not locate final Message positions in message.cpp.")

position_new = '''\tmessage.start_char = cr_startmsg.cpMin;\n\tmessage.end_header = message.start_char + header_len;\n\tmessage.end_char = message.start_char + written - written_info;\n\tif (!service && header && profile_sender_valid && message.id) {\n\t\tprofile_nav_register_message_sender(\n\t\t\tmessage.id,\n\t\t\tprofile_sender_id,\n\t\t\tprofile_sender_type\n\t\t);\n\t}'''
s = s.replace(position_anchor, position_new, 1)
write(m, s)

# =============================================================================
# procs.cpp — nickname clicks, participant list, profile photo arrows
# =============================================================================
s = read(p)

global_anchor = "HWND color_edits[4] = {0};"
if global_anchor not in s:
    raise SystemExit("Could not locate procs.cpp globals.")

procs_globals = r'''

// profile_navigation_latvianghost_v1
#define PROFILE_PREV_BUTTON 9101
#define PROFILE_NEXT_BUTTON 9102
#define PROFILE_MEMBERS_LIST 9103
#define PROFILE_MEMBERS_TIMER 9104

struct TelegacyMessageSenderRef {
    int message_id;
    BYTE peer_id[8];
    char peer_type;
};

static std::vector<TelegacyMessageSenderRef> profile_message_senders;
static Peer* profile_dialog_peer = NULL;
static HWND profile_members_list = NULL;
static HWND profile_photo_previous = NULL;
static HWND profile_photo_next = NULL;
static HWND profile_photo_counter = NULL;

static void telegacy_open_peer_profile(Peer* peer);

void profile_nav_clear_message_senders() {
    profile_message_senders.clear();
}

void profile_nav_register_message_sender(
    int message_id,
    const BYTE* peer_id,
    char peer_type
) {
    if (!message_id || !peer_id || peer_type < 0)
        return;

    for (int i = 0; i < (int)profile_message_senders.size(); i++) {
        if (profile_message_senders[i].message_id == message_id) {
            memcpy(profile_message_senders[i].peer_id, peer_id, 8);
            profile_message_senders[i].peer_type = peer_type;
            return;
        }
    }

    TelegacyMessageSenderRef item;
    item.message_id = message_id;
    memcpy(item.peer_id, peer_id, 8);
    item.peer_type = peer_type;
    profile_message_senders.push_back(item);

    if (profile_message_senders.size() > 12000)
        profile_message_senders.erase(profile_message_senders.begin());
}

static Peer* profile_nav_find_peer(
    const BYTE* peer_id,
    char peer_type
) {
    if (!peer_id)
        return NULL;

    if (peer_type == 0 && memcmp(myself.id, peer_id, 8) == 0)
        return &myself;

    if (
        current_peer &&
        current_peer->type == 1 &&
        current_peer->chat_users
    ) {
        for (int i = 0; i < (int)current_peer->chat_users->size(); i++) {
            Peer* candidate = &current_peer->chat_users->at(i);
            if (
                candidate->type == peer_type &&
                memcmp(candidate->id, peer_id, 8) == 0
            ) {
                return candidate;
            }
        }
    }

    for (int i = 0; i < peers_count; i++) {
        if (
            peers[i].type == peer_type &&
            memcmp(peers[i].id, peer_id, 8) == 0
        ) {
            return &peers[i];
        }
    }

    if (
        current_peer &&
        current_peer->type == peer_type &&
        memcmp(current_peer->id, peer_id, 8) == 0
    ) {
        return current_peer;
    }

    return NULL;
}

static Peer* profile_nav_sender_for_message(int message_id) {
    for (int i = (int)profile_message_senders.size() - 1; i >= 0; i--) {
        if (profile_message_senders[i].message_id == message_id) {
            return profile_nav_find_peer(
                profile_message_senders[i].peer_id,
                profile_message_senders[i].peer_type
            );
        }
    }
    return NULL;
}

static void profile_dialog_fill_members() {
    if (!profile_members_list || !profile_dialog_peer || profile_dialog_peer->type != 1)
        return;

    SendMessageW(profile_members_list, LB_RESETCONTENT, 0, 0);

    if (!profile_dialog_peer->chat_users) {
        int row = (int)SendMessageW(
            profile_members_list,
            LB_ADDSTRING,
            0,
            (LPARAM)L"\u0417\u0430\u0433\u0440\u0443\u0437\u043A\u0430 \u0443\u0447\u0430\u0441\u0442\u043D\u0438\u043A\u043E\u0432..."
        );
        if (row >= 0)
            SendMessageW(profile_members_list, LB_SETITEMDATA, row, (LPARAM)-1);
        return;
    }

    if (profile_dialog_peer->chat_users->empty()) {
        int row = (int)SendMessageW(
            profile_members_list,
            LB_ADDSTRING,
            0,
            (LPARAM)L"\u041D\u0435\u0442 \u0443\u0447\u0430\u0441\u0442\u043D\u0438\u043A\u043E\u0432"
        );
        if (row >= 0)
            SendMessageW(profile_members_list, LB_SETITEMDATA, row, (LPARAM)-1);
        return;
    }

    for (int i = 0; i < (int)profile_dialog_peer->chat_users->size(); i++) {
        Peer* member = &profile_dialog_peer->chat_users->at(i);
        const wchar_t* label = member->name && member->name[0]
            ? member->name
            : L"Unknown";
        int row = (int)SendMessageW(
            profile_members_list,
            LB_ADDSTRING,
            0,
            (LPARAM)label
        );
        if (row >= 0)
            SendMessageW(profile_members_list, LB_SETITEMDATA, row, i);
    }
}
'''
s = s.replace(global_anchor, global_anchor + procs_globals, 1)

# Track the actual Peer rather than just dlg_peer's shallow copy.
init_anchor = '''\t\tPeer* peer = (Peer*)lParam;\n\t\tdlg_peer = *peer;'''
if init_anchor not in s:
    raise SystemExit("Could not locate DlgProc WM_INITDIALOG peer setup.")
s = s.replace(
    init_anchor,
    init_anchor + '''\n\t\tprofile_dialog_peer = peer;\n\t\tprofile_members_list = NULL;\n\t\tprofile_photo_previous = NULL;\n\t\tprofile_photo_next = NULL;\n\t\tprofile_photo_counter = NULL;''',
    1,
)

# Add the participant panel / avatar navigation controls right after dlgPic.
picture_anchor = '''\t\tdlgPic = CreateWindowEx(WS_EX_CLIENTEDGE, L"STATIC", NULL, WS_CHILD | WS_VISIBLE | SS_BITMAP | SS_NOTIFY, 10, 10, 160, 160, hDlg, NULL, NULL, NULL);'''
if picture_anchor not in s:
    raise SystemExit("Could not locate dlgPic creation in DlgProc.")

picture_extra = r'''

        if (peer->type == 0) {
            profile_photo_previous = CreateWindowW(
                L"BUTTON", L"<-",
                WS_CHILD | WS_TABSTOP,
                10, 174, 42, 23,
                hDlg, (HMENU)PROFILE_PREV_BUTTON, NULL, NULL
            );
            profile_photo_counter = CreateWindowW(
                L"STATIC", L"",
                WS_CHILD | SS_CENTER | SS_CENTERIMAGE,
                56, 174, 68, 23,
                hDlg, NULL, NULL, NULL
            );
            profile_photo_next = CreateWindowW(
                L"BUTTON", L"->",
                WS_CHILD | WS_TABSTOP,
                128, 174, 42, 23,
                hDlg, (HMENU)PROFILE_NEXT_BUTTON, NULL, NULL
            );

            RECT wr;
            GetWindowRect(hDlg, &wr);
            SetWindowPos(
                hDlg, NULL,
                0, 0,
                wr.right - wr.left,
                wr.bottom - wr.top + 30,
                SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE
            );
        } else if (peer->type == 1) {
            CreateWindowW(
                L"STATIC", L"\u0423\u0447\u0430\u0441\u0442\u043D\u0438\u043A\u0438 (\u0434\u0432\u043E\u0439\u043D\u043E\u0439 \u0449\u0435\u043B\u0447\u043E\u043A \u2014 \u043F\u0440\u043E\u0444\u0438\u043B\u044C):",
                WS_CHILD | WS_VISIBLE,
                10, 184, 460, 18,
                hDlg, NULL, NULL, NULL
            );

            profile_members_list = CreateWindowExW(
                WS_EX_CLIENTEDGE,
                L"LISTBOX",
                L"",
                WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL |
                    LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
                10, 202, 460, 112,
                hDlg,
                (HMENU)PROFILE_MEMBERS_LIST,
                NULL,
                NULL
            );

            RECT wr;
            GetWindowRect(hDlg, &wr);
            SetWindowPos(
                hDlg, NULL,
                0, 0,
                wr.right - wr.left,
                wr.bottom - wr.top + 145,
                SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE
            );

            profile_dialog_fill_members();

            if (!peer->chat_users) {
                get_full_peer(peer);
                SetTimer(hDlg, PROFILE_MEMBERS_TIMER, 300, NULL);
            }
        }
'''
s = s.replace(picture_anchor, picture_anchor + picture_extra, 1)

# Start the avatar list only after the initial/current avatar request has been queued.
focus_anchor = '''\t\tSetFocus(birthday);\n\t\tSetFocus(dlgPic);'''
if focus_anchor not in s:
    raise SystemExit("Could not locate profile focus anchor.")
s = s.replace(
    focus_anchor,
    '''\t\tif (peer->type == 0) {\n\t\t\tprofile_gallery_begin(\n\t\t\t\tpeer,\n\t\t\t\tdlgPic,\n\t\t\t\tprofile_photo_previous,\n\t\t\t\tprofile_photo_next,\n\t\t\t\tprofile_photo_counter\n\t\t\t);\n\t\t}\n\n''' + focus_anchor,
    1,
)

# Handle arrows and participant activation before legacy IDOK/STN_CLICKED logic.
command_anchor = '''\tcase WM_COMMAND: {\n\t\tif (LOWORD(wParam) == IDOK) {'''
if command_anchor not in s:
    raise SystemExit("Could not locate DlgProc WM_COMMAND prologue.")
command_new = r'''	case WM_COMMAND: {
        if (LOWORD(wParam) == PROFILE_PREV_BUTTON) {
            profile_gallery_step(-1);
            return TRUE;
        }
        if (LOWORD(wParam) == PROFILE_NEXT_BUTTON) {
            profile_gallery_step(1);
            return TRUE;
        }
        if (
            LOWORD(wParam) == PROFILE_MEMBERS_LIST &&
            HIWORD(wParam) == LBN_DBLCLK &&
            profile_dialog_peer &&
            profile_dialog_peer->type == 1 &&
            profile_dialog_peer->chat_users
        ) {
            int selected = (int)SendMessageW(
                profile_members_list,
                LB_GETCURSEL,
                0,
                0
            );

            if (
                selected != LB_ERR &&
                selected >= 0 &&
                selected < (int)profile_dialog_peer->chat_users->size()
            ) {
                Peer* member = &profile_dialog_peer->chat_users->at(selected);
                telegacy_open_peer_profile(member);
                return TRUE;
            }
        }

		if (LOWORD(wParam) == IDOK) {'''
s = s.replace(command_anchor, command_new, 1)

# Poll once while get_full_peer() fills a basic group's real vector.
color_anchor = '''\tcase WM_CTLCOLORDLG:\n\tcase WM_CTLCOLORSTATIC:'''
if color_anchor not in s:
    raise SystemExit("Could not locate DlgProc color cases.")
timer_case = r'''	case WM_TIMER:
        if (wParam == PROFILE_MEMBERS_TIMER) {
            if (
                profile_dialog_peer &&
                profile_dialog_peer->type == 1 &&
                profile_dialog_peer->chat_users
            ) {
                KillTimer(hDlg, PROFILE_MEMBERS_TIMER);
                profile_dialog_fill_members();
            }
            return TRUE;
        }
        break;
'''
s = s.replace(color_anchor, timer_case + color_anchor, 1)

# Clean gallery state and list pointers before the HWNDs disappear.
destroy_anchor = '''\tcase WM_DESTROY:\n\t\tif (dlgPic) {'''
if destroy_anchor not in s:
    raise SystemExit("Could not locate DlgProc WM_DESTROY.")
s = s.replace(
    destroy_anchor,
    '''\tcase WM_DESTROY:\n\t\tKillTimer(hDlg, PROFILE_MEMBERS_TIMER);\n\t\tprofile_gallery_clear();\n\t\tprofile_dialog_peer = NULL;\n\t\tprofile_members_list = NULL;\n\t\tprofile_photo_previous = NULL;\n\t\tprofile_photo_next = NULL;\n\t\tprofile_photo_counter = NULL;\n\t\tif (dlgPic) {''',
    1,
)

# Add one canonical helper for opening any resolved Peer in the existing DlgProc.
dlg_start, dlg_end = function_range(s, "INT_PTR CALLBACK DlgProc(")
open_helper = r'''

static void telegacy_open_peer_profile(Peer* peer) {
    if (!peer)
        return;

    BYTE buffer[24] = {0};
    LONG dlgUnits = GetDialogBaseUnits();
    DLGTEMPLATE* dlg = (DLGTEMPLATE*)buffer;
    dlg->style = WS_POPUP | WS_CAPTION | WS_SYSMENU | DS_MODALFRAME;
    dlg->cx = MulDiv(490, 4, LOWORD(dlgUnits));
    dlg->cy = MulDiv(180, 8, HIWORD(dlgUnits));

    if (current_dialog && IsWindow(current_dialog))
        DestroyWindow(current_dialog);

    current_dialog = CreateDialogIndirectParamW(
        GetModuleHandleW(NULL),
        dlg,
        hMain,
        DlgProc,
        (LPARAM)peer
    );
}
'''
s = s[:dlg_end] + open_helper + s[dlg_end:]

# Clear sender references whenever chat contents are replaced.
settext_anchor = '''\tcase WM_SETTEXT: {\n\t\tmessages.clear();'''
if settext_anchor not in s:
    raise SystemExit("Could not locate WndProcChat WM_SETTEXT.")
s = s.replace(
    settext_anchor,
    '''\tcase WM_SETTEXT: {\n\t\tprofile_nav_clear_message_senders();\n\t\tmessages.clear();''',
    1,
)

# Clickable sender headers. Keep media player's pre-switch mouse hook intact.
click_anchor = '''\tcase WM_PAINT:\n\tcase WM_LBUTTONUP:\n\t\tHideCaret(hWnd);\n\t\tbreak;'''
if click_anchor not in s:
    raise SystemExit("Could not locate WndProcChat paint/click block.")
click_new = r'''	case WM_PAINT:
        HideCaret(hWnd);
        break;
    case WM_LBUTTONUP: {
        HideCaret(hWnd);

        CHARRANGE selection = {0};
        SendMessageW(hWnd, EM_EXGETSEL, 0, (LPARAM)&selection);
        if (selection.cpMin != selection.cpMax)
            break;

        POINT point = {
            GET_X_LPARAM(lParam),
            GET_Y_LPARAM(lParam)
        };
        int character = (int)SendMessageW(
            hWnd,
            EM_CHARFROMPOS,
            0,
            (LPARAM)&point
        );

        for (int i = (int)messages.size() - 1; i >= 0; i--) {
            if (
                character >= messages[i].start_char &&
                character < messages[i].end_header
            ) {
                Peer* sender = profile_nav_sender_for_message(messages[i].id);
                if (sender) {
                    telegacy_open_peer_profile(sender);
                    return 0;
                }
                break;
            }
        }
        break;
    }'''
s = s.replace(click_anchor, click_new, 1)
write(p, s)

# =============================================================================
# response.cpp — route photos.Photos and selected upload.file chunks
# =============================================================================
s = read(r)

# DC migration retry: gallery first, then legacy current-avatar request.
retry_anchor = '''\t\t\t\t\t\tif (memcmp(pfp_msgid, last_rpcresult_msgid, 8) == 0) {\n\t\t\t\t\t\t\tget_pfp(active_dc, current_peer);\n\t\t\t\t\t\t\tbreak;\n\t\t\t\t\t\t}'''
if retry_anchor not in s:
    raise SystemExit("Could not locate legacy pfp DC-migrate retry block.")
retry_new = '''\t\t\t\t\t\tif (profile_gallery_retry_download(last_rpcresult_msgid, active_dc)) {\n\t\t\t\t\t\t\tbreak;\n\t\t\t\t\t\t}\n\t\t\t\t\t\tif (memcmp(pfp_msgid, last_rpcresult_msgid, 8) == 0) {\n\t\t\t\t\t\t\tif (profile_gallery_showing_current() && current_dialog && IsWindow(current_dialog)) get_pfp(active_dc, &dlg_peer);\n\t\t\t\t\t\t\tbreak;\n\t\t\t\t\t\t}'''
s = s.replace(retry_anchor, retry_new, 1)

# upload.file: selected historical avatar is independent of Media/document queues.
# Insert after Telegacy's migrated-DC idle timer so gallery downloads do not
# keep an auxiliary DC connection alive forever.
upload_anchor = '''\tcase 0x96a18d5: { // upload.file'''
up = s.find(upload_anchor)
if up < 0:
    raise SystemExit("Could not locate upload.file response route.")

timer_anchor = '''\t\tif (dcInfo != &dcInfoMain) SetTimer(hMain, 20 + dcInfo->dc, 60000, NULL);'''
timer_pos = s.find(timer_anchor, up)
if timer_pos < 0:
    raise SystemExit("Could not locate upload.file migrated-DC timer.")
insert_after_timer = timer_pos + len(timer_anchor)
upload_hook = '''\n\t\tif (profile_gallery_handle_upload(last_rpcresult_msgid, unenc_response, length)) {\n\t\t\tbreak;\n\t\t}'''
s = s[:insert_after_timer] + upload_hook + s[insert_after_timer:]

# Legacy current-avatar response should not overwrite an older selected photo.
pfp_anchor = '''\t\tif (memcmp(pfp_msgid, last_rpcresult_msgid, 8) == 0) {\n\t\t\tHBITMAP hBmp = jpg_to_bmp(unenc_response + 16, tlstr_len(unenc_response + 12, false));\n\t\t\tSendMessage(dlgPic, STM_SETIMAGE, IMAGE_BITMAP, (LPARAM)hBmp);\n\t\t\tbreak;\n\t\t}'''
if pfp_anchor not in s:
    raise SystemExit("Could not locate legacy pfp upload.file block.")
pfp_new = '''\t\tif (memcmp(pfp_msgid, last_rpcresult_msgid, 8) == 0) {\n\t\t\tif (profile_gallery_showing_current() && dlgPic && IsWindow(dlgPic)) {\n\t\t\t\tint bytes_len = tlstr_len(unenc_response + 12, false);\n\t\t\t\tint bytes_header = bytes_len >= 254 ? 4 : 1;\n\t\t\t\tHBITMAP hBmp = jpg_to_bmp(unenc_response + 12 + bytes_header, bytes_len);\n\t\t\t\tif (hBmp) {\n\t\t\t\t\tHBITMAP oldBmp = (HBITMAP)SendMessage(dlgPic, STM_SETIMAGE, IMAGE_BITMAP, (LPARAM)hBmp);\n\t\t\t\t\tif (oldBmp && oldBmp != hBmp) DeleteObject(oldBmp);\n\t\t\t\t}\n\t\t\t}\n\t\t\tbreak;\n\t\t}'''
s = s.replace(pfp_anchor, pfp_new, 1)

# photos.getUserPhotos result. Insert before the existing photos.photo no-op.
photos_anchor = '''\tcase 0x20212ca8: // photos.photo\n\t\tbreak;'''
if photos_anchor not in s:
    raise SystemExit("Could not locate photos.photo response route.")
photos_new = '''\tcase 0x8dca6aa5: // photos.photos\n\tcase 0x15051f54: // photos.photosSlice\n\t\tprofile_gallery_handle_photos_response(last_rpcresult_msgid, unenc_response, length);\n\t\tbreak;\n\tcase 0x20212ca8: // photos.photo\n\t\tbreak;'''
s = s.replace(photos_anchor, photos_new, 1)
write(r, s)

# =============================================================================
# Verification
# =============================================================================
checks = {
    h: [
        "profile_navigation_latvianghost_v1",
        "profile_gallery_handle_photos_response",
        "profile_nav_register_message_sender",
    ],
    helpers: [
        "photos.getUserPhotos",
        "profile_gallery_request_selected",
        "profile_gallery_handle_upload",
        "profile_gallery_step",
    ],
    m: [
        "profile_sender_id",
        "profile_nav_register_message_sender",
    ],
    p: [
        "PROFILE_MEMBERS_LIST",
        "profile_dialog_fill_members",
        "telegacy_open_peer_profile",
        "profile_nav_sender_for_message",
        "profile_gallery_begin",
    ],
    r: [
        "case 0x8dca6aa5",
        "case 0x15051f54",
        "profile_gallery_retry_download",
        "profile_gallery_handle_upload",
    ],
}

for path, tokens in checks.items():
    text = read(path)
    for token in tokens:
        if token not in text:
            raise SystemExit(f"Profile navigation verification failed in {path.name}: {token}")

print(
    "Applied LatvianGhost profile navigation: clickable message senders, "
    "basic-group participant list, member profiles, and user avatar gallery."
)
