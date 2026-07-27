from __future__ import annotations

def detect_scenes(video_path: str, duration: float):
    try:
        from scenedetect import detect, AdaptiveDetector,ContentDetector
        adaptive=detect(video_path,AdaptiveDetector(adaptive_threshold=2.7,min_scene_len=8))
        hard=detect(video_path,ContentDetector(threshold=24.0,min_scene_len=8))
        points={0.0,float(duration)}
        for rows in (adaptive,hard):
            for start,end in rows:points.add(start.get_seconds());points.add(end.get_seconds())
        ordered=[]
        for point in sorted(max(0,min(float(duration),value)) for value in points):
            if not ordered or point-ordered[-1]>=.28:ordered.append(point)
            else:ordered[-1]=point
        result=[{'id':i,'start':a,'end':b} for i,(a,b) in enumerate(zip(ordered,ordered[1:])) if b-a>=.12]
        return result or [{'id':0,'start':0.0,'end':duration}]
    except Exception:
        return [{'id':i,'start':s,'end':min(duration,s+12)} for i,s in enumerate(_frange(0,duration,12))]

def _frange(start, stop, step):
    while start < stop:
        yield start; start += step
