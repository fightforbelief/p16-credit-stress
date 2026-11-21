import unittest
from dataclasses import replace
from datetime import date
from analysis import Cell, forecast, margin
from build import parse, quarter

class VintageTests(unittest.TestCase):
    def setUp(self):
        self.flat = {v: Cell(1000, 0, (3,)*20) for v in range(100)}

    def test_release_date_formats_and_quarter_boundary(self):
        for s in ("20200930","09-30-20","09/30/2020","2020-09-30"):
            self.assertEqual(parse(s),date(2020,9,30))
        self.assertEqual(quarter(date(2020,10,1))-quarter(parse("20200930")),1)

    def test_flat_history_and_calibration(self):
        p=forecast(self.flat,50,8,8)
        for m in ("development","mature","period","frontier","historical"):
            self.assertAlmostEqual(p[m],.06)
        self.assertAlmostEqual(margin(self.flat,60,8,8),0)

    def test_forecast_and_margin_ignore_future_events(self):
        origin, age=60,8
        t=origin+age-1
        masked={v:replace(row,events=tuple(x if v+j-1<=t else 75 for j,x in enumerate(row.events,1)))
                for v,row in self.flat.items() if v<=t}
        self.assertEqual(forecast(self.flat,origin,age,8),forecast(masked,origin,age,8))
        self.assertEqual(margin(self.flat,origin,age,8),margin(masked,origin,age,8))

    def test_affine_drift_freshness_gain(self):
        table={v: Cell(10000,0,(v+1,)*20) for v in range(100)}
        p=forecast(table,50,8,8)
        self.assertAlmostEqual(p["period"]-p["mature"],sum(range(12))/10000)
        self.assertAlmostEqual(p["frontier"]-p["period"],3.5*12/10000)

if __name__=="__main__":
    unittest.main()
