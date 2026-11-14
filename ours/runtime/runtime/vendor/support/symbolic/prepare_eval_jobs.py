import argparse
import json
from sym_paths import BASE_DATA,DATA
from common import write_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--shards',type=int,default=8);p.add_argument('--smoke',action='store_true');a=p.parse_args()
    cases=[json.loads(s) for s in (BASE_DATA/'mini/cases.jsonl').read_text().splitlines()]
    if a.smoke:
        groups=['new_training_scene','legacy_explicit_return','current_bowl_location','close_then_switch','direct_switch','normal_libero']
        cases=[next(c for c in cases if c['group']==g) for g in groups]
    tag='smoke' if a.smoke else 'full'
    directory=DATA/'eval_jobs'/tag
    for i in range(a.shards):write_json(directory/f'{i:02d}.json',cases[i::a.shards])
    write_json(directory/'manifest.json',dict(cases=len(cases),shards=a.shards,smoke=a.smoke,
        case_ids=[c['case_id'] for c in cases],source_manifest=str(BASE_DATA/'mini/cases.jsonl')))
    print(directory)

if __name__=='__main__':main()

