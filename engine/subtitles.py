from __future__ import annotations
from pathlib import Path

def _ass_color(value):
    value=str(value or '#ffffff').lstrip('#');value=(value+'ffffff')[:6];return f'&H00{value[4:6]}{value[2:4]}{value[0:2]}'.upper()

def make_ass(words,path,width=1080,height=1920,max_words=5,style=None):
    style=style or {};max_words=int(style.get('maxWords',max_words));font=style.get('fontName','Arial');font_size=int(style.get('fontSize',64));margin_v=int(style.get('marginV',250));margin_h=int(style.get('marginH',86));outline=int(style.get('outline',5));primary=_ass_color(style.get('primaryColor','#ffffff'));secondary=_ass_color(style.get('highlightColor','#ffd700'));groups=[]; current=[]
    for word in words:
        if current and (len(current)>=max_words or word['start']-current[-1]['end']>.45): groups.append(current); current=[]
        current.append(word)
    if current: groups.append(current)
    header=f'''[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{font},{font_size},{primary},{secondary},&H00151515,&H80000000,-1,0,0,0,100,100,0,0,1,{outline},1,2,{margin_h},{margin_h},{margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    lines=[]
    for group in groups:
        text=' '.join(_escape(w['text']) for w in group)
        lines.append(f"Dialogue: 0,{_time(group[0]['start'])},{_time(group[-1]['end'])},Default,,0,0,0,,{text}")
    Path(path).write_text(header+'\n'.join(lines),encoding='utf-8')
    return {'events':len(lines),'path':str(path)}

def _time(seconds):
    h=int(seconds//3600); m=int(seconds%3600//60); s=seconds%60
    return f'{h}:{m:02d}:{s:05.2f}'
def _escape(text): return text.replace('\\','\\\\').replace('{','\\{').replace('}','\\}').replace('\n',' ')
