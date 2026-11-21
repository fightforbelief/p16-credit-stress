import unittest
from dataclasses import replace

from analysis import Cell, forecast
from review import paired, releases_summary

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.table={v:Cell(600+v,0,tuple(1+(j+v)%8 for j in range(20))) for v in range(65)}

    def test_original_and_matched_weights(self):
        v,age=47,8
        direct=forecast(self.table,v,age,8)
        equal=paired(self.table,v,age,"vintage")
        loan=paired(self.table,v,age,"loan")
        self.assertAlmostEqual(direct["chain"],loan["mult_rr"])
        self.assertAlmostEqual(direct["development"],loan["mult_mm"])
        self.assertAlmostEqual(direct["period"],equal["add_r"])
        self.assertAlmostEqual(direct["mature"],equal["add_m"])
        common={q:replace(c,n=1000) for q,c in self.table.items()}
        for key,value in paired(common,v,age,"loan").items():
            self.assertAlmostEqual(value,paired(common,v,age,"vintage")[key])

    def test_no_post_landmark_cells_in_hybrids(self):
        v,age=47,8
        truncated={q:replace(c,events=tuple(x if q+i<=v+age-1 else 550 for i,x in enumerate(c.events)))
                   for q,c in self.table.items() if q<=v+age-1}
        for w in ("loan","vintage"):
            self.assertEqual(paired(truncated,v,age,w),paired(self.table,v,age,w))

    def test_archive_can_reverse_ranking_and_have_no_age_eight_target(self):
        row=dict(origin="case",program="test",family="add",age=18,truth=.2,
                 archived_recent=.19,archived_mature=.1,revised_recent=.19,revised_mature=.2)
        general,fixed=releases_summary([row])
        self.assertLess(general["archived_delta"],0)
        self.assertGreater(general["revised_delta"],0)
        self.assertEqual(fixed["quarters"],0)
        self.assertIsNone(fixed["revised_delta"])

if __name__=="__main__":
    unittest.main()
