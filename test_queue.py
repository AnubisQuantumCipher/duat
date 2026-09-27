import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from queue_store import edit, update

class QueueTests(unittest.TestCase):
 def test_concurrent_state_updates_preserve_entries(self):
  with tempfile.TemporaryDirectory() as tmp:
   directory=Path(tmp)
   with edit(directory) as entries:
    entries.extend([{'id':'alpha','state':'queued'},{'id':'beta','state':'queued'}])
   with ThreadPoolExecutor() as pool:
    futures=[pool.submit(update,directory,key,state='needs-review',error='review required') for key in ('alpha','beta')]
    for future in futures:future.result()
   result=json.loads((directory/'offload-queue.json').read_text())
   self.assertEqual({x['id'] for x in result},{'alpha','beta'})
   self.assertTrue(all(x['state']=='needs-review' for x in result))
