import unittest
from trace_history import amount_change, bridge, field_state


class HistoryTests(unittest.TestCase):
    def test_bridge_rejects_disagreement_and_duplicate_single_anchors(self):
        self.assertEqual(bridge([0,1,None,3,None],[0,None,1,4,None]),
                         [(0,"both"),(None,"collision"),(None,"collision"),(None,"conflict"),(None,"unmatched")])

    def test_date_blank_zero_and_missing_are_distinct(self):
        row = [0,[],None,"PIF",0,None]
        blank = [0,[],None,"PIF",None,None]
        self.assertEqual(field_state(None,"2020-01-01"),("unlinked",)*3)
        self.assertEqual(field_state(row,"2020-01-01"),("blank","PIF","zero"))
        self.assertEqual(amount_change(blank,row),"became_reported")
        self.assertEqual(amount_change(row,row),"same")
