"""Human review: actual dataset RGB, exact policy overlays, role and prompt sidecars."""
import html,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from sym_paths import ROOT
from dataset import P1Data
from common import write_json
from sym_contract import prompt
from v3_markers import marker_info,render_numpy

def image_at(data,idx,key):
    old=data.preparation['old_switch_anchors'];rev=data.preparation['revision_anchors']
    if idx<old:return np.array(data.images[key][0][idx])
    if idx<rev:return np.array(data.images[key][1][idx-old])
    pos=idx-rev;split=len(data.images[key][2]);return np.array(data.images[key][2 if pos<split else 3][pos if pos<split else pos-split])

def main():
    data=P1Data();out=ROOT/'previews';out.mkdir(exist_ok=True)
    categories=[('return_bowl',lambda p,s:p['stages'][s]['kind']=='return' and p['restore_object']=='akita_black_bowl_1'),
      ('return_bottle',lambda p,s:p['stages'][s]['kind']=='return' and p['restore_object']=='wine_bottle_1'),
      ('return_cheese',lambda p,s:p['stages'][s]['kind']=='return' and p['restore_object']=='cream_cheese_1'),
      ('grasp_cheese',lambda p,s:p['stages'][s]['kind']=='grasp' and p['target']==6),
      ('place_cheese_in_current_bowl',lambda p,s:p['stages'][s]['kind']=='target' and p['target']==6),
      ('close_middle_drawer',lambda p,s:p['stages'][s]['kind']=='close' and p['stages'][s].get('joint')=='middle'),
      ('open_middle_drawer',lambda p,s:p['stages'][s]['kind']=='target' and p['target']==0),
      ('place_bowl_on_stove',lambda p,s:p['stages'][s]['kind']=='target' and p['target']==1),
      ('place_bowl_on_plate',lambda p,s:p['stages'][s]['kind']=='target' and p['target']==8),
      ('place_inside_top_drawer',lambda p,s:p['stages'][s]['kind']=='target' and p['target']==3)]
    selected=[]
    for label,predicate in categories:
        candidates=[]
        for i in np.flatnonzero(data.anchors['revision']):
            plan=data.plans[int(data.anchors['episode'][i])];s=int(data.stages[i])
            if predicate(plan,s):
                info=marker_info(plan,s,data.points[i],data.point_valid[i])
                if info['valid'] and all(15<v<208 for v in info['yx']):candidates.append(int(i))
        if not candidates:continue
        # An interior frame of one contiguous stage; not a handpicked future success.
        ei=int(data.anchors['episode'][candidates[0]])
        candidates=[i for i in candidates if int(data.anchors['episode'][i])==ei]
        selected.append((label,candidates[len(candidates)//3]))
    # Also expose the newly collected layouts, rather than only old fixed scenes.
    new_candidates={}
    for i in np.flatnonzero(data.anchors['revision']):
        ei=int(data.anchors['episode'][i]);p=data.plans[ei];s=int(data.stages[i])
        if not p['new'] or p['stages'][s]['kind']!='return':continue
        info=marker_info(p,s,data.points[i],data.point_valid[i])
        if not info['valid']:continue
        xyz=p['initial_xyz'][p['restore_object']]
        key=(p['restore_object'],tuple(np.round(xyz,3)))
        new_candidates.setdefault(key,[]).append(int(i))
    count={}
    for (obj,xyz),indices in new_candidates.items():
        short={'akita_black_bowl_1':'bowl','wine_bottle_1':'bottle','cream_cheese_1':'cheese'}[obj]
        count.setdefault(short,0)
        if count[short]>=3:continue
        count[short]+=1;ei=int(data.anchors['episode'][indices[0]])
        same=[i for i in indices if int(data.anchors['episode'][i])==ei]
        selected.append((f'new_return_{short}_layout{count[short]}',same[len(same)//3]))
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
    small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',12)
    cards=[];records=[]
    for number,(label,i) in enumerate(selected,1):
        plan=data.plans[int(data.anchors['episode'][i])];stage=int(data.stages[i])
        raw=image_at(data,i,'image');wrist=image_at(data,i,'wrist_image')
        info=marker_info(plan,stage,data.points[i],data.point_valid[i]);marked=render_numpy(raw,info)
        prefix=f'{number:02d}_{label}';Image.fromarray(raw).save(out/(prefix+'_raw.png'));Image.fromarray(marked).save(out/(prefix+'_point.png'))
        Image.fromarray(wrist).save(out/(prefix+'_wrist.png'))
        text=prompt(plan,'V3R',stage,data.points[i],data.point_valid[i])
        record=dict(label=label,anchor=i,episode=int(data.anchors['episode'][i]),frame=int(data.anchors['frame'][i]),
                    stage=stage,marker=info,prompt=text,raw=prefix+'_raw.png',point=prefix+'_point.png',wrist=prefix+'_wrist.png')
        if plan['stages'][stage]['kind']=='return':
            old=data.preparation['old_switch_anchors'];rev=data.preparation['revision_anchors']
            reference=np.asarray(data.newrefs[data.refidx[i]] if old<=i<rev else data.refs[data.refidx[i]])
            Image.fromarray(reference).save(out/(prefix+'_initial_reference_audit_only.png'))
            audit=Image.new('RGB',(688,280),'white');d=ImageDraw.Draw(audit)
            d.text((8,3),f'{number:02d} Return target: historical position | y,x={info["yx"]}',fill='black',font=font)
            for x,title,img in [(8,'EPISODE START / audit only',reference),(232,'CURRENT MAIN / raw',raw),(456,'CURRENT MAIN / V3R input',marked)]:
                d.text((x,25),title,fill='black',font=small);audit.paste(Image.fromarray(img),(x,45))
            record['historical_audit']=prefix+'_historical_audit.png';audit.save(out/record['historical_audit'])
            record['historical_reference_is_policy_input']=False
        write_json(out/(prefix+'.json'),record);records.append(record)
        card=Image.new('RGB',(688,290),'white');draw=ImageDraw.Draw(card)
        draw.text((8,3),f'{number:02d} {label} | y,x={info["yx"]}',fill='black',font=font)
        for x,title,img in [(8,'MAIN / raw',raw),(232,'MAIN / exact V3R input',marked),(456,'WRIST / unchanged',wrist)]:
            draw.text((x,25),title,fill='black',font=small);card.paste(Image.fromarray(img),(x,45))
        draw.text((8,272),f'anchor={i} episode={record["episode"]} frame={record["frame"]} | role={info["role"]}',fill='black',font=small)
        card.save(out/(prefix+'_comparison.png'));cards.append(card)
    for filename,group in [('overview.png',cards[:10]),('overview_new_layouts.png',cards[10:])]:
        if not group:continue
        sheet=Image.new('RGB',(1376,290*((len(group)+1)//2)),(225,225,225))
        for i,card in enumerate(group):sheet.paste(card,((i%2)*688,(i//2)*290))
        sheet.save(out/filename)
    write_json(out/'manifest.json',records)
    focus=[cards[10],cards[4],cards[5]] if len(cards)>10 else cards[:3]
    focus_sheet=Image.new('RGB',(688,290*len(focus)),'white')
    for i,card in enumerate(focus):focus_sheet.paste(card,(0,290*i))
    focus_sheet.save(out/'review_focus.png')
    doc=['<!doctype html><meta charset="utf-8"><title>V3R point review</title><style>body{font-family:sans-serif;max-width:1100px;margin:30px auto}img{image-rendering:pixelated;max-width:100%}pre{white-space:pre-wrap;background:#eee;padding:15px}</style><h1>V3R: exact policy-input previews</h1><p>Left: raw MAIN; middle: V3R MAIN; right: unchanged WRIST. A red arrow identifies the current subgoal reference, not a motion direction.</p>']
    for r in records:
        prefix=r['point'].removesuffix('_point.png');doc+=[f'<h2>{html.escape(r["label"])}</h2>',f'<img src="{prefix}_comparison.png">',f'<pre>{html.escape(r["prompt"])}</pre>']
        if 'historical_audit' in r:doc+=[f'<p>Historical reference audit only: the episode-start image below is NOT provided to V3R.</p><img src="{r["historical_audit"]}">']
    (out/'index.html').write_text('\n'.join(doc));print(out/'overview.png')

if __name__=='__main__':main()
