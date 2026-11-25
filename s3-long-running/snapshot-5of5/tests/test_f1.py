import os
import tempfile
import unittest
from datetime import datetime

from chat_store import ChatStore, group_by_date  # noqa: F401

CONV_KEYS = {'id', 'title', 'created_at', 'updated_at', 'is_deleted'}
MSG_KEYS = {'id', 'conversation_id', 'role', 'content', 'created_at'}
T0 = datetime(2026, 1, 1, 10, 0, 0)


class TestF1CreateAndList(unittest.TestCase):
    def setUp(self):
        self.store = ChatStore(':memory:')

    def tearDown(self):
        self.store.close()

    def test_create_default_title(self):
        c = self.store.create_conversation(now=T0)
        self.assertEqual(set(c.keys()), CONV_KEYS)
        self.assertIsInstance(c['id'], int)
        self.assertEqual(c['title'], 'New Conversation')
        self.assertEqual(c['created_at'], '2026-01-01T10:00:00')
        self.assertEqual(c['updated_at'], '2026-01-01T10:00:00')
        self.assertIs(c['is_deleted'], False)

    def test_create_title_stripped(self):
        c = self.store.create_conversation('  Hello 世界  ', now=T0)
        self.assertEqual(c['title'], 'Hello 世界')

    def test_create_empty_title_raises(self):
        for t in ['', '   ', '\t\n']:
            with self.assertRaises(ValueError):
                self.store.create_conversation(t, now=T0)
        self.assertEqual(self.store.list_conversations(), [])

    def test_get_conversation(self):
        c = self.store.create_conversation('A', now=T0)
        g = self.store.get_conversation(c['id'])
        self.assertEqual(set(g.keys()), CONV_KEYS)
        self.assertEqual(g, c)

    def test_get_unknown_raises_keyerror(self):
        with self.assertRaises(KeyError):
            self.store.get_conversation(9999)

    def test_add_message(self):
        c = self.store.create_conversation('A', now=T0)
        t1 = datetime(2026, 1, 1, 11, 30, 0)
        m = self.store.add_message(c['id'], 'user', '你好', now=t1)
        self.assertEqual(set(m.keys()), MSG_KEYS)
        self.assertIsInstance(m['id'], int)
        self.assertEqual(m['conversation_id'], c['id'])
        self.assertEqual(m['role'], 'user')
        self.assertEqual(m['content'], '你好')
        self.assertEqual(m['created_at'], '2026-01-01T11:30:00')
        g = self.store.get_conversation(c['id'])
        self.assertEqual(g['updated_at'], '2026-01-01T11:30:00')
        self.assertEqual(g['created_at'], '2026-01-01T10:00:00')

    def test_add_message_roles(self):
        c = self.store.create_conversation('A', now=T0)
        for role in ['user', 'assistant', 'system']:
            m = self.store.add_message(c['id'], role, 'x', now=T0)
            self.assertEqual(m['role'], role)
        for role in ['bot', '', 'User']:
            with self.assertRaises(ValueError):
                self.store.add_message(c['id'], role, 'x', now=T0)

    def test_add_message_unknown_conversation(self):
        with self.assertRaises(KeyError):
            self.store.add_message(9999, 'user', 'x', now=T0)

    def test_list_ordered_by_updated_at_desc(self):
        a = self.store.create_conversation('A', now=datetime(2026, 1, 1, 9, 0, 0))
        b = self.store.create_conversation('B', now=datetime(2026, 1, 1, 12, 0, 0))
        c = self.store.create_conversation('C', now=datetime(2026, 1, 1, 10, 0, 0))
        ids = [x['id'] for x in self.store.list_conversations()]
        self.assertEqual(ids, [b['id'], c['id'], a['id']])
        self.store.add_message(a['id'], 'user', 'hi', now=datetime(2026, 1, 1, 13, 0, 0))
        ids = [x['id'] for x in self.store.list_conversations()]
        self.assertEqual(ids, [a['id'], b['id'], c['id']])

    def test_list_ties_broken_by_id_desc(self):
        a = self.store.create_conversation('A', now=T0)
        b = self.store.create_conversation('B', now=T0)
        c = self.store.create_conversation('C', now=T0)
        ids = [x['id'] for x in self.store.list_conversations()]
        self.assertEqual(ids, sorted([a['id'], b['id'], c['id']], reverse=True))

    def test_list_returns_conversation_dicts(self):
        self.store.create_conversation('A', now=T0)
        lst = self.store.list_conversations()
        self.assertEqual(len(lst), 1)
        self.assertEqual(set(lst[0].keys()), CONV_KEYS)
        self.assertIs(lst[0]['is_deleted'], False)


class TestF1FileDatabase(unittest.TestCase):
    def test_file_db_persists(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'chat.db')
            s = ChatStore(p)
            c = s.create_conversation('Persist', now=T0)
            s.add_message(c['id'], 'assistant', 'ok', now=T0)
            s.close()
            s2 = ChatStore(p)
            try:
                self.assertEqual(s2.get_conversation(c['id'])['title'], 'Persist')
                self.assertEqual(len(s2.list_conversations()), 1)
            finally:
                s2.close()


if __name__ == '__main__':
    unittest.main()
