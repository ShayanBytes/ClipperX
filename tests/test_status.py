import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from engine.common import dump, load

class StatusTests(unittest.TestCase):
    def test_atomic_status_writes_remain_valid_json(self):
        path=Path(tempfile.mkdtemp())/'status.json'
        failures=[]
        def writer(worker):
            try:
                for progress in range(40): dump(path,{'worker':worker,'progress':progress})
            except Exception as exc: failures.append(exc)
        workers=[threading.Thread(target=writer,args=(i,)) for i in range(3)]
        [worker.start() for worker in workers]
        [worker.join() for worker in workers]
        self.assertEqual(failures,[])
        self.assertIsInstance(load(path),dict)

    def test_transient_windows_replace_denial_is_retried(self):
        path=Path(tempfile.mkdtemp())/'status.json'
        from engine import common
        real_replace=common.os.replace
        attempts={'count':0}
        def occasionally_denied(source,target):
            attempts['count']+=1
            if attempts['count']<=3: raise PermissionError(13,'Access is denied')
            return real_replace(source,target)
        with patch.object(common.os,'replace',side_effect=occasionally_denied):
            dump(path,{'progress':78})
        self.assertEqual(load(path)['progress'],78)
        self.assertEqual(attempts['count'],4)

if __name__=='__main__': unittest.main()
