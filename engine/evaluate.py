from __future__ import annotations
from .common import load,iou,dump

def evaluate(prediction_path,truth_path,out_path):
    pred=load(prediction_path,{}).get('keyframes',[]); truth=load(truth_path,{}).get('frames',[]); rows=[]
    for gt in truth:
        nearest=min(pred,key=lambda k:abs(k['time']-gt['time'])) if pred else None
        if not nearest: continue
        rows.append({'time':gt['time'],'centerError':((nearest['centerX']-gt['centerX'])**2+(nearest['centerY']-gt['centerY'])**2)**.5,'zoomError':abs(nearest['cropHeight']-gt['cropHeight']),'requiredVisible':_contains(nearest,gt.get('requiredPoints',[]))})
    result={'samples':len(rows),'meanCenterError':sum(x['centerError'] for x in rows)/max(1,len(rows)),'meanZoomError':sum(x['zoomError'] for x in rows)/max(1,len(rows)),'requiredVisibilityRate':sum(x['requiredVisible'] for x in rows)/max(1,len(rows))}
    dump(out_path,result); return result

def _contains(k,points):
    x1=k['centerX']-k['cropWidth']/2;x2=k['centerX']+k['cropWidth']/2;y1=k['centerY']-k['cropHeight']/2;y2=k['centerY']+k['cropHeight']/2
    return int(all(x1<=p[0]<=x2 and y1<=p[1]<=y2 for p in points))
