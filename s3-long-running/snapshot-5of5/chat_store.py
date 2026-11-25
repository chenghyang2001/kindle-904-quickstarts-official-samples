"""Conversation-management data layer for the claude.ai clone (stdlib sqlite3 only).

F1 implemented: ChatStore.__init__/close/create_conversation/add_message/
get_conversation/list_conversations.
F2 implemented: rename_conversation.
F3 implemented: delete_conversation (soft delete via is_deleted = 1).
F4 implemented: search_conversations (literal substring match on title or any
message content; %, _ and backslash are escaped and matched literally via
LIKE ... ESCAPE '\\'; ASCII case-insensitive; EXISTS keeps each conversation once;
same ordering as list_conversations; stripped empty query -> []).
F5 implemented: group_by_date (pure function; compares the DATE part of
updated_at with now.date(); fixed group order Today, Yesterday,
Previous 7 days, Older; empty groups omitted; input order kept).
"""

import sqlite3
from datetime import datetime

VALID_ROLES = ("user", "assistant", "system")

_CONV_COLUMNS = "id, title, created_at, updated_at, is_deleted"

GROUP_ORDER = ("Today", "Yesterday", "Previous 7 days", "Older")


def _ts(now):
    if now is None:
        now = datetime.now()
    return now.isoformat(timespec="seconds")


def _conv_row_to_dict(row):
    return {
        "id": int(row[0]),
        "title": row[1],
        "created_at": row[2],
        "updated_at": row[3],
        "is_deleted": bool(row[4]),
    }


def _clean_title(title):
    if not isinstance(title, str):
        raise ValueError("title must be a string")
    t = title.strip()
    if not t:
        raise ValueError("title must not be empty")
    return t


def _escape_like(text):
    # Backslash first, then the LIKE wildcards.
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ChatStore:
    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS conversations ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " title TEXT NOT NULL,"
            " created_at TEXT NOT NULL,"
            " updated_at TEXT NOT NULL,"
            " is_deleted INTEGER NOT NULL DEFAULT 0)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " conversation_id INTEGER NOT NULL,"
            " role TEXT NOT NULL,"
            " content TEXT NOT NULL,"
            " created_at TEXT NOT NULL)"
        )
        self._conn.commit()

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _fetch_active(self, conversation_id):
        row = self._conn.execute(
            "SELECT " + _CONV_COLUMNS + " FROM conversations WHERE id = ? AND is_deleted = 0",
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise KeyError(conversation_id)
        return _conv_row_to_dict(row)

    def create_conversation(self, title="New Conversation", *, now=None):
        t = _clean_title(title)
        ts = _ts(now)
        cur = self._conn.execute(
            "INSERT INTO conversations (title, created_at, updated_at, is_deleted) VALUES (?, ?, ?, 0)",
            (t, ts, ts),
        )
        self._conn.commit()
        return {
            "id": int(cur.lastrowid),
            "title": t,
            "created_at": ts,
            "updated_at": ts,
            "is_deleted": False,
        }

    def add_message(self, conversation_id, role, content, *, now=None):
        if role not in VALID_ROLES:
            raise ValueError("invalid role: %r" % (role,))
        self._fetch_active(conversation_id)
        ts = _ts(now)
        cur = self._conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, ts),
        )
        self._conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (ts, conversation_id),
        )
        self._conn.commit()
        return {
            "id": int(cur.lastrowid),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": ts,
        }

    def get_conversation(self, conversation_id):
        return self._fetch_active(conversation_id)

    def list_conversations(self):
        rows = self._conn.execute(
            "SELECT " + _CONV_COLUMNS + " FROM conversations WHERE is_deleted = 0"
            " ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        return [_conv_row_to_dict(r) for r in rows]

    def rename_conversation(self, conversation_id, title, *, now=None):
        t = _clean_title(title)
        self._fetch_active(conversation_id)
        ts = _ts(now)
        self._conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND is_deleted = 0",
            (t, ts, conversation_id),
        )
        self._conn.commit()
        return self._fetch_active(conversation_id)

    def delete_conversation(self, conversation_id, *, now=None):
        self._fetch_active(conversation_id)
        self._conn.execute(
            "UPDATE conversations SET is_deleted = 1 WHERE id = ? AND is_deleted = 0",
            (conversation_id,),
        )
        self._conn.commit()
        return None

    def search_conversations(self, query):
        if not isinstance(query, str):
            return []
        q = query.strip()
        if not q:
            return []
        pattern = "%" + _escape_like(q) + "%"
        rows = self._conn.execute(
            "SELECT c.id, c.title, c.created_at, c.updated_at, c.is_deleted"
            " FROM conversations c"
            " WHERE c.is_deleted = 0 AND ("
            "  c.title LIKE ? ESCAPE '\\'"
            "  OR EXISTS (SELECT 1 FROM messages m"
            "   WHERE m.conversation_id = c.id AND m.content LIKE ? ESCAPE '\\'))"
            " ORDER BY c.updated_at DESC, c.id DESC",
            (pattern, pattern),
        ).fetchall()
        return [_conv_row_to_dict(r) for r in rows]


def _group_name(days):
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days <= 7:
        return "Previous 7 days"
    return "Older"


def group_by_date(conversations, now):
    """Group conversations by the date part of updated_at relative to now.date().

    Returns [{"group": name, "conversations": [...]}, ...] in the fixed order
    Today, Yesterday, Previous 7 days, Older; empty groups are omitted and the
    input order is kept inside each group. Does not touch the database.
    """
    today = now.date()
    buckets = {name: [] for name in GROUP_ORDER}
    for conv in conversations:
        updated_date = datetime.fromisoformat(conv["updated_at"]).date()
        days = (today - updated_date).days
        buckets[_group_name(days)].append(conv)
    return [
        {"group": name, "conversations": buckets[name]}
        for name in GROUP_ORDER
        if buckets[name]
    ]
