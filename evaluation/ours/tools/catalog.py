import json
from pathlib import Path
B=Path('/mnt/disk_4/geyi/audio_switch_benchmark')
R=B/'regressions/c3r_pi05_70_serial_20261108'
def read(p):return json.loads(Path(p).read_text())
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def item_for(cid):
    catalog=[json.loads(s)for s in (B/'distribution/current/catalog/CASES.jsonl').read_text().splitlines()]
    c=next(x for x in catalog if x['case_id']==cid);b=c['branch'];root=B/b/'current'
    if b=='T1':case=next(x for x in read(R/'data/T1/selected.private.json')if x['case_id']==cid)
    elif b=='T2':case=next(x for x in read(R/'data/T2_ALL.json')if x['case_id']==cid)
    elif b=='T3':case=read(R/'data/T3/specs'/(cid+'.json'))
    elif b in ('T4','T8'):case=next(x for x in read(R/f'data/{b}/data/selected.private.json')if x['case_id']==cid)
    elif b=='T5':case=next(x for x in read(R/'data/T5/selected.private.json')if x['case_id']==cid)
    elif b=='T6':case=next(x for x in read(root/'dataset/selected90.private.json')if x['case_id']==cid)
    elif b=='T7':
        m=next(x for x in read(root/'dataset/CASE_ID_MAP.json')if x['case_id']==cid)
        case=next(x for x in read(R/'data/T7'/m['condition']/'cases.private.json')if x['case_id']==m['runtime_case_id'])
    else:raise ValueError(b)
    return dict(c,case=case,public_case_id=cid,preflight_id='CLOUD04_'+cid)
