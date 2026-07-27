import tempfile,unittest
from pathlib import Path
import cv2,numpy as np
from engine.render import render_dynamic
class RenderProgressTests(unittest.TestCase):
 def test_full_render_reports_progress(self):
  folder=Path(tempfile.mkdtemp());source=folder/'source.mp4';writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),10,(160,90))
  for frame in range(20): writer.write(np.full((90,160,3),(frame*5,60,150),dtype=np.uint8))
  writer.release();updates=[];keys={'keyframes':[{'time':0,'centerX':.5,'centerY':.5,'cropWidth':.316,'cropHeight':1.0},{'time':2,'centerX':.5,'centerY':.5,'cropWidth':.316,'cropHeight':1.0}]};render_dynamic(str(source),keys,str(folder/'output.mp4'),folder,None,90,160,updates.append);self.assertGreater(len(updates),2);self.assertEqual(updates[-1],1.0)
