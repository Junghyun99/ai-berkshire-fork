import tempfile, unittest
from pathlib import Path
from decimal import Decimal as D
from check import compare, unique, xml_sheets
class AuditTests(unittest.TestCase):
    def test_inclusive_boundary_and_missing_dates(self):
        r=compare({"2020-01-01":D("1"),"2020-02-01":D("2")},{"2020-01-01":D("1.0005"),"2020-03-01":D("3")},"2020-01-01","2020-12-31")
        self.assertEqual(r["within_0_0005_usd"],1)
        self.assertEqual(r["yahoo_only_dates"],["2020-02-01"])
        self.assertEqual(r["issuer_only_dates"],["2020-03-01"])
    def test_discrepancy_is_not_rounded_away(self):
        r=compare({"2021-12-17":D("1.633")},{"2021-12-17":D("1.636431")},"2021-01-01","2021-12-31")
        self.assertEqual(r["max_abs_amount_difference_usd"],"0.003431")
        self.assertEqual(len(r["outside_tolerance"]),1)
    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError): unique([("x",D(1)),("x",D(2))])
    def test_xml_sparse_cells_and_ampersand(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"input"
            original='<ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><ss:Worksheet ss:Name="sample"><ss:Table><ss:Row><ss:Cell ss:Index="2" ss:HRef="https://example.org/?a=1&b=2"><ss:Data ss:Type="String">A &amp; B</ss:Data></ss:Cell></ss:Row></ss:Table></ss:Worksheet></ss:Workbook>'
            p.write_text(original)
            sheets,count=xml_sheets(p)
            self.assertEqual(sheets["sample"],[["","A & B"]])
            self.assertEqual(count,1)
            self.assertEqual(p.read_text(),original)
if __name__=="__main__":unittest.main()
