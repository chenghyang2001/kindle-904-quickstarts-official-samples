import unittest
from datetime import datetime

from chat_store import ChatStore, group_by_date  # noqa: F401

BS = chr(92)


def t(h, m=0):
    return datetime(2026, 4, 1, h, m, 0)


class TestF4Search(unittest.TestCase):
    def setUp(self):
        self.store = ChatStore(':memory:')

    def tearDown(self):
        self.store.close()

    def ids(self, q):
        return [x['id'] for x in self.store.search_conversations(q)]

    def test_percent_is_literal(self):
        a = self.store.create_conversation('折扣 50% 優惠', now=t(1))
        self.store.create_conversation('折扣 500 元', now=t(2))
        self.store.create_conversation('5 and 0', now=t(3))
        self.assertEqual(self.ids('50%'), [a['id']])

    def test_percent_in_message_content(self):
        a = self.store.create_conversation('X', now=t(1))
        self.store.add_message(a['id'], 'user', 'progress is 50% done', now=t(1))
        b = self.store.create_conversation('Y', now=t(2))
        self.store.add_message(b['id'], 'user', 'progress is 500 units', now=t(2))
        self.assertEqual(self.ids('50%'), [a['id']])
        self.assertEqual(self.ids('%'), [a['id']])

    def test_underscore_is_literal(self):
        a = self.store.create_conversation('a_b', now=t(1))
        self.store.create_conversation('axb', now=t(2))
        self.assertEqual(self.ids('a_b'), [a['id']])
        self.assertEqual(self.ids('_'), [a['id']])

    def test_backslash_is_literal(self):
        a = self.store.create_conversation('C:' + BS + 'temp', now=t(1))
        self.store.create_conversation('C:temp', now=t(2))
        self.assertEqual(self.ids('C:' + BS), [a['id']])
        self.assertEqual(self.ids(BS + 'temp'), [a['id']])

    def test_chinese_title(self):
        a = self.store.create_conversation('週會紀錄', now=t(1))
        self.store.create_conversation('Weekly', now=t(2))
        self.assertEqual(self.ids('會紀'), [a['id']])

    def test_chinese_message_content(self):
        a = self.store.create_conversation('Trip', now=t(1))
        self.store.add_message(a['id'], 'user', '請幫我規劃台北三日遊', now=t(1))
        self.store.create_conversation('Other', now=t(2))
        self.assertEqual(self.ids('台北'), [a['id']])

    def test_ascii_case_insensitive(self):
        a = self.store.create_conversation('Hello World', now=t(1))
        b = self.store.create_conversation('Z', now=t(2))
        self.store.add_message(b['id'], 'assistant', 'say HELLO back', now=t(2))
        self.assertEqual(self.ids('hello'), [b['id'], a['id']])

    def test_each_conversation_once(self):
        a = self.store.create_conversation('python tips', now=t(1))
        self.store.add_message(a['id'], 'user', 'python one', now=t(1, 1))
        self.store.add_message(a['id'], 'assistant', 'python two', now=t(1, 2))
        self.assertEqual(self.ids('python'), [a['id']])

    def test_ordering_same_as_list(self):
        a = self.store.create_conversation('topic A', now=t(1))
        b = self.store.create_conversation('topic B', now=t(3))
        c = self.store.create_conversation('topic C', now=t(2))
        d = self.store.create_conversation('topic D', now=t(3))
        self.assertEqual(self.ids('topic'), [d['id'], b['id'], c['id'], a['id']])
        self.store.add_message(a['id'], 'user', 'bump', now=t(5))
        self.assertEqual(self.ids('topic'), [a['id'], d['id'], b['id'], c['id']])

    def test_returns_conversation_dicts(self):
        self.store.create_conversation('dict check', now=t(1))
        r = self.store.search_conversations('dict')
        self.assertEqual(set(r[0].keys()), {'id', 'title', 'created_at', 'updated_at', 'is_deleted'})

    def test_empty_query_returns_empty(self):
        self.store.create_conversation('anything', now=t(1))
        self.assertEqual(self.store.search_conversations(''), [])
        self.assertEqual(self.store.search_conversations('   '), [])

    def test_query_is_stripped(self):
        a = self.store.create_conversation('折扣 50% 優惠', now=t(1))
        self.store.create_conversation('折扣 500 元', now=t(2))
        self.assertEqual(self.ids('  50%  '), [a['id']])

    def test_no_match(self):
        self.store.create_conversation('abc', now=t(1))
        self.assertEqual(self.store.search_conversations('xyz'), [])

    def test_deleted_not_returned(self):
        a = self.store.create_conversation('會議 A', now=t(1))
        b = self.store.create_conversation('會議 B', now=t(2))
        self.store.add_message(a['id'], 'user', '只在 A 裡', now=t(3))
        self.store.delete_conversation(a['id'], now=t(4))
        self.assertEqual(self.ids('會議'), [b['id']])
        self.assertEqual(self.ids('只在'), [])


if __name__ == '__main__':
    unittest.main()
