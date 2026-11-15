"""No network or archive execution: report and boundary contracts."""
import pathlib,tempfile,unittest,json
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pan_machine import write,main
class MachineTests(unittest.TestCase):
 def test_missing_input_nonzero_machine_result(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);code=main(['--input',str(p/'missing'),'--output',str(p/'out'),'--result',str(p/'result.json')])
   self.assertNotEqual(code,0);r=json.loads((p/'result.json').read_text());self.assertEqual(r['schema_version'],1);self.assertEqual(r['status'],'failed')
 def test_private_atomic_result(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'r.json';write(p,{'status':'unknown'});self.assertEqual(p.stat().st_mode&0o777,0o600)
if __name__=='__main__':unittest.main()
