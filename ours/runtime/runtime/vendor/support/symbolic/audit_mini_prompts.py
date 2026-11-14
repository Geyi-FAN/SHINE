"""Check every mini task/stage, valid+unavailable coordinates, and wide state bins."""
import json
import numpy as np
from sym_paths import ROOT,DATA,BASE_DATA
from common import write_json
from sym_contract import prompt,ROLES
from openpi.models.tokenizer import PaligemmaTokenizer

def main():
    tok=PaligemmaTokenizer(200)._tokenizer
    plans=json.loads((DATA/'mini_plans.json').read_text())
    cases=[json.loads(x) for x in (BASE_DATA/'mini/cases.jsonl').read_text().splitlines()]
    nums={i:len(tok.encode(str(i))) for i in range(-1,256)}
    coord=max(range(224),key=nums.get);state=max(nums,key=nums.get)
    n=0;longest=0;worst=None;normals=0
    def check(cid,stage,flag,raw):
        nonlocal n,longest,worst
        full=f"Task: {raw.strip().replace('_',' ').replace(chr(10),' ')}, State: {' '.join([str(state)]*8)};\nAction: "
        length=len(tok.encode(full,add_bos=True));assert length<=200,(cid,stage,length)
        if length>longest:longest=length;worst=[cid,stage,flag]
        n+=1
    for cid,p in plans.items():
        for s in range(len(p['stages'])):
            for flag in [True,False]:
                raw=prompt(p,'V3R',s,np.full((len(ROLES),2),coord,np.float32),np.full(len(ROLES),flag))
                check(cid,s,flag,raw)
    for c in cases:
        if c['kind']=='normal':check(c['case_id'],None,None,c['instruction']);normals+=1
    report=dict(passed=True,non_normal_cases=len(plans),normal_cases=normals,
        stage_and_validity_combinations=n,max_tokens=longest,worst_case=worst,
        pixel_integer=coord,state_integer=state,overflow=0,
        note='Long integer token stress check; the online server also rejects overflow on every actual request.')
    write_json(ROOT/'reports/mini_prompt_lengths.json',report);print(json.dumps(report,indent=2))

if __name__=='__main__':main()
