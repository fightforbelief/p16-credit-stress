import unittest
from revision_records import archive_ledger, match
from revision_influence import shapley


class RevisionTests(unittest.TestCase):
    def test_unlinked_duplicates_and_visible_transitions(self):
        v = 8000
        seen, past = (v, 4, "visible", "2000Q4"), (v, 0, "post_cutoff", "2021Q1")
        keys = [(1, str(i), "zip", 3) for i in range(3)]
        a, b, c = keys
        old = {a: [seen], b: [seen, seen], c: [None]}
        new = {a: [past], b: [seen], c: [(v + 1, 0, "blank", "")]}
        ledger, transitions, n, dates = archive_ledger(old, new)
        self.assertEqual(ledger["visible_to_post_cutoff", v, 4], -1)
        self.assertEqual(ledger["visible_to_post_cutoff", v, 0], 0)
        self.assertEqual(ledger["unlinked", v, 4], -1)
        self.assertEqual(ledger["entry_or_vintage", v+1, 0], 1)
        self.assertEqual(dates["visible_to_post_cutoff", "2000Q4", "2021Q1"], 1)
        self.assertEqual(n["unlinked_2020"], 2)
        self.assertEqual(transitions["unlinked", "outside", "visible"], 1)

    def test_secondary_links_require_consistency_and_uniqueness(self):
        old = [((1, 2, 3, 4), None), ((2, 5, 6, 7), None), ((3, 8, 9, 10), None)]
        new = [((4, 2, 3, 4), None), ((5, 11, 6, 7), None), ((6, 8, 12, 13), None),
               ((7, 14, 9, 10), None)]
        self.assertEqual(match(old,new), {0: ("normalized_name",0), 1: ("address_and_disbursement",1)})

    def test_interactions_are_shared(self):
        scores = {0: 1, 1: 2, 2: 3, 3: 6}
        self.assertEqual([r[-1] for r in shapley(scores, ["a", "b"])], [2, 3])


if __name__ == "__main__":
    unittest.main()
