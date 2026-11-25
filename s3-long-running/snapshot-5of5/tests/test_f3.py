import os
import sqlite3
import tempfile
import unittest
from datetime import datetime

from chat_store import ChatStore, group_by_date  # noqa: F401

T0 = datetime(2026, 3, 1, 8, 0, 0)
T1 = datetime(2026, 3, 1, 9, 0, 0)
T2 = datetime(2026, 3, 1, 10, 0, 0)


class TestF3SoftDelete(unittest.TestCase):
    def setUp(self):
        self.store = ChatStore(':memory:')

    def tearDown(self):
        self.store.close()

    def test_delete_hides_from_list(self):
        a = self.store.create_conversation('A', now=T0)
        b = self.store.create_conversation('B', now=T1)
        self.assertIsNone(self.store.delete_conversation(a['id'], now=T2))
        ids = [x['id'] for x in self.store.list_conversations()]
        self.assertEqual(ids, [b['id']])

    def test_deleted_get_raises(self):
        a = self.store.create_conversation('A', now=T0)
        self.store.delete_conversation(a['id'], now=T1)
        with self.assertRaises(KeyError):
            self.store.get_conversation(a['id'])

    def test_deleted_rename_and_add_message_raise(self):
        a = self.store.create_conversation('A', now=T0)
        self.store.delete_conversation(a['id'], now=T1)
        with self.assertRaises(KeyError):
            self.store.rename_conversation(a['id'], 'X', now=T2)
        with self.assertRaises(KeyError):
            self.store.add_message(a['id'], 'user', 'hi', now=T2)

    def test_double_delete_raises(self):
        a = self.store.create_conversation('A', now=T0)
        self.store.delete_conversation(a['id'], now=T1)
        with self.assertRaises(KeyError):
            self.store.delete_conversation(a['id'], now=T2)

    def test_delete_unknown_raises(self):
        with self.assertRaises(KeyError):
            self.store.delete_conversation(9999, now=T0)

    def test_deleted_hidden_from_search(self):
        a = self.store.create_conversation('Secret plan', now=T0)
        self.store.add_message(a['id'], 'user', 'hidden words', now=T0)
        b = self.store.create_conversation('Secret two', now=T1)
        self.store.delete_conversation(a['id'], now=T2)
        self.assertEqual([x['id'] for x in self.store.search_conversations('Secret')], [b['id']])
        self.assertEqual(self.store.search_conversations('hidden'), [])


class TestF3RowStaysInDb(unittest.TestCase):
    def test_row_and_messages_remain(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'chat.db')
            s = ChatStore(p)
            c = s.create_conversation('Gone', now=T0)
            s.add_message(c['id'], 'user', 'm1', now=T0)
            s.add_message(c['id'], 'assistant', 'm2', now=T1)
            s.delete_conversation(c['id'], now=T2)
            s.close()
            conn = sqlite3.connect(p)
            try:
                row = conn.execute('SELECT is_deleted, title FROM conversations WHERE id = ?', (c['id'],)).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], 1)
                self.assertEqual(row[1], 'Gone')
                n = conn.execute('SELECT COUNT(*) FROM messages WHERE conversation_id = ?', (c['id'],)).fetchone()[0]
                self.assertEqual(n, 2)
            finally:
                conn.close()


if __name__ == '__main__':
    unittest.main()
