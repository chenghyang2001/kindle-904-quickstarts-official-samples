import unittest
from datetime import datetime

from chat_store import ChatStore, group_by_date

NOW = datetime(2026, 3, 10, 0, 5, 0)


def conv(i, updated_at):
    return {'id': i, 'title': 'c%d' % i, 'created_at': updated_at,
            'updated_at': updated_at, 'is_deleted': False}


def names(groups):
    return [g['group'] for g in groups]


def ids_of(groups, name):
    for g in groups:
        if g['group'] == name:
            return [c['id'] for c in g['conversations']]
    return None


class TestF5GroupByDate(unittest.TestCase):
    def test_cross_midnight_yesterday(self):
        groups = group_by_date([conv(1, '2026-03-09T23:59:00'), conv(2, '2026-03-10T00:00:00')], NOW)
        self.assertEqual(names(groups), ['Today', 'Yesterday'])
        self.assertEqual(ids_of(groups, 'Today'), [2])
        self.assertEqual(ids_of(groups, 'Yesterday'), [1])

    def test_exactly_7_days_is_previous_7_days(self):
        groups = group_by_date([conv(1, '2026-03-03T00:00:00'), conv(2, '2026-03-03T23:59:59')], NOW)
        self.assertEqual(names(groups), ['Previous 7 days'])
        self.assertEqual(ids_of(groups, 'Previous 7 days'), [1, 2])

    def test_two_days_is_previous_7_days(self):
        groups = group_by_date([conv(1, '2026-03-08T12:00:00')], NOW)
        self.assertEqual(names(groups), ['Previous 7 days'])

    def test_8_days_is_older(self):
        groups = group_by_date([conv(1, '2026-03-02T23:59:59'), conv(2, '2025-01-01T00:00:00')], NOW)
        self.assertEqual(names(groups), ['Older'])
        self.assertEqual(ids_of(groups, 'Older'), [1, 2])

    def test_future_is_today(self):
        groups = group_by_date([conv(1, '2026-03-12T08:00:00')], NOW)
        self.assertEqual(names(groups), ['Today'])

    def test_fixed_order_and_input_order_kept(self):
        data = [
            conv(1, '2026-01-01T00:00:00'),
            conv(2, '2026-03-09T10:00:00'),
            conv(3, '2026-03-10T00:01:00'),
            conv(4, '2026-03-05T10:00:00'),
            conv(5, '2026-03-10T00:00:30'),
            conv(6, '2026-03-09T00:00:00'),
        ]
        groups = group_by_date(data, NOW)
        self.assertEqual(names(groups), ['Today', 'Yesterday', 'Previous 7 days', 'Older'])
        self.assertEqual(ids_of(groups, 'Today'), [3, 5])
        self.assertEqual(ids_of(groups, 'Yesterday'), [2, 6])
        self.assertEqual(ids_of(groups, 'Previous 7 days'), [4])
        self.assertEqual(ids_of(groups, 'Older'), [1])
        for g in groups:
            self.assertEqual(set(g.keys()), {'group', 'conversations'})

    def test_empty_groups_omitted(self):
        groups = group_by_date([conv(1, '2026-03-10T00:00:00'), conv(2, '2026-02-01T00:00:00')], NOW)
        self.assertEqual(names(groups), ['Today', 'Older'])
        self.assertIsNone(ids_of(groups, 'Yesterday'))
        self.assertIsNone(ids_of(groups, 'Previous 7 days'))

    def test_empty_input(self):
        self.assertEqual(group_by_date([], NOW), [])

    def test_conversation_dicts_passed_through(self):
        c = conv(7, '2026-03-09T23:59:00')
        groups = group_by_date([c], NOW)
        self.assertEqual(groups[0]['conversations'], [c])

    def test_with_store_output(self):
        store = ChatStore(':memory:')
        try:
            a = store.create_conversation('old', now=datetime(2026, 2, 1, 12, 0, 0))
            b = store.create_conversation('yest', now=datetime(2026, 3, 9, 23, 59, 0))
            c = store.create_conversation('today', now=datetime(2026, 3, 10, 0, 1, 0))
            groups = group_by_date(store.list_conversations(), NOW)
            self.assertEqual(names(groups), ['Today', 'Yesterday', 'Older'])
            self.assertEqual(ids_of(groups, 'Today'), [c['id']])
            self.assertEqual(ids_of(groups, 'Yesterday'), [b['id']])
            self.assertEqual(ids_of(groups, 'Older'), [a['id']])
        finally:
            store.close()


if __name__ == '__main__':
    unittest.main()
