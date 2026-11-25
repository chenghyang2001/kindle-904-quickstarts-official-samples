import unittest
from datetime import datetime

from chat_store import ChatStore, group_by_date  # noqa: F401

T0 = datetime(2026, 2, 1, 8, 0, 0)
T1 = datetime(2026, 2, 1, 9, 0, 0)
T2 = datetime(2026, 2, 2, 15, 45, 10)


class TestF2Rename(unittest.TestCase):
    def setUp(self):
        self.store = ChatStore(':memory:')

    def tearDown(self):
        self.store.close()

    def test_rename_returns_updated(self):
        c = self.store.create_conversation('Old', now=T0)
        r = self.store.rename_conversation(c['id'], '  新標題  ', now=T2)
        self.assertEqual(set(r.keys()), {'id', 'title', 'created_at', 'updated_at', 'is_deleted'})
        self.assertEqual(r['id'], c['id'])
        self.assertEqual(r['title'], '新標題')
        self.assertEqual(r['updated_at'], '2026-02-02T15:45:10')
        self.assertEqual(r['created_at'], '2026-02-01T08:00:00')
        self.assertIs(r['is_deleted'], False)

    def test_rename_persisted(self):
        c = self.store.create_conversation('Old', now=T0)
        r = self.store.rename_conversation(c['id'], 'New', now=T2)
        self.assertEqual(self.store.get_conversation(c['id']), r)

    def test_rename_moves_to_top(self):
        a = self.store.create_conversation('A', now=T0)
        b = self.store.create_conversation('B', now=T1)
        ids = [x['id'] for x in self.store.list_conversations()]
        self.assertEqual(ids, [b['id'], a['id']])
        self.store.rename_conversation(a['id'], 'A2', now=T2)
        ids = [x['id'] for x in self.store.list_conversations()]
        self.assertEqual(ids, [a['id'], b['id']])

    def test_rename_empty_raises_valueerror(self):
        c = self.store.create_conversation('Keep', now=T0)
        for t in ['', '   ']:
            with self.assertRaises(ValueError):
                self.store.rename_conversation(c['id'], t, now=T2)
        g = self.store.get_conversation(c['id'])
        self.assertEqual(g['title'], 'Keep')
        self.assertEqual(g['updated_at'], '2026-02-01T08:00:00')

    def test_rename_unknown_raises_keyerror(self):
        with self.assertRaises(KeyError):
            self.store.rename_conversation(9999, 'X', now=T2)

    def test_rename_deleted_raises_keyerror(self):
        c = self.store.create_conversation('A', now=T0)
        self.store.delete_conversation(c['id'], now=T1)
        with self.assertRaises(KeyError):
            self.store.rename_conversation(c['id'], 'X', now=T2)


if __name__ == '__main__':
    unittest.main()
