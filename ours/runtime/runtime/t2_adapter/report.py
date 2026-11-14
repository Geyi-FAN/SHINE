"""One complete frozen MX10 round, paired with the previous repaired R8 MX10."""
import csv
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
A = Path(__file__).resolve().parent
sys.path[:0] = [str(A/'analysis'), str(A/'tools')]
from audited_score import aggregate, audible_r8
from run import check_freeze, read, put


def main(root):
    s = aggregate(root)
    previous_root = Path('/mnt/disk_4/geyi/audio_switch_t2_control_repair_20261102/originalMX10_v3')
    old = read(previous_root/'reports_final/summary.json')
    old_rows = {r['case_id']:r for r in old['rows']}
    specs = {r['case_id']:r for r in read(A/'dataset/selected.private.json')}
    rows = []
    errors = []
    audio = []
    lines = ['# C3r T2 原MX10：整轮配对回归', '',
        '本轮10个任务各1例；沿用此前中英混合音频、初态、暂停点、预算和独立三指标。两张卡、两个环境进程，账户租约内一个真实语音会话；不拼接跨轮成功。', '',
        '|方法|Interaction 交互|Target 目标曾达|Instruction 完整物理指令|',
        '|---|---:|---:|---:|',
        '|此前R8＋T2修复v3|10/10，100%|10/10，100%|10/10，100%|',
        '|C3r recovery＋提前推理＋共同R8/T2修复＋简短启动回执|'+'|'.join(f"{s['metrics'][k]['success']}/10，{s['metrics'][k]['rate']*100:.0f}%" for k in ['interaction','target','instruction'])+'|', '',
        '当前权重SmolVLA E3v4 raw30000，YOLO/M1、图像与8维state不变。新增完整C3r/R7-T3.2、提前推理与已验证CUDA Graph动作服务；这些条件与此前R8执行层不同，不能将变化全部归因于某一个模块。首任务Native路由不代表实际用了全部C3r四角色或代码恢复。', '',
        '暂停≤5秒、保持3秒、恢复受理≤20秒、实际首动作≤45秒、真实PCM回执≤10秒；原任务600秒／1200策略动作，恢复不续预算；终态40物理步及适用释放／支撑／稳定不变。', '',
        '|任务|交互|目标|完整指令|未通过检查|', '|---|---|---|---|---|']
    for v in s['rows']:
        cid = v['case_id']
        d = root/'cases'/cid/'formal'
        sp = specs[cid]
        x = read(d/'result.json')
        prev_spec = read(previous_root/'cases'/cid/'formal/spec.json')
        matched = sp['fixture']['assets'] == prev_spec['fixture']['assets'] and all(
            a['audio_sha256'] == b['audio_sha256'] and hashlib.sha256(Path(a['audio_ref']['file']).read_bytes()).hexdigest() == a['audio_sha256']
            for a,b in zip(sp['turns'], prev_spec['turns']))
        ready = read(d/'readiness.json')
        identity = ready['policy_metadata']
        verified = ready['execution_kernel']=='C3r' and ready['c3r_profile']=='recovery' and ready['native_scheduler']=='prefetch-frame-aligned-v1'
        verified = verified and identity['weights_sha256']=='30a620085ba28b8faec160ae68a9276d705ec0fb6d2fc9237e706379d0c5eebc'
        verified = verified and identity['normalization_sha256']=='d4e03a22ef5d89a910e32c233a509465ad0d265381a06745917d69fd8924a635'
        if not matched or not verified:
            errors.append(cid+':identity_or_input_mismatch')
        q = read(d/'AUDIO_QUALITY.json')
        if not q['passed']:
            errors.append(cid+':audio_delivery')
        audio.extend(dict(case_id=cid, **r) for r in q['clips'])
        voice = [json.loads(l) for p in (d/'voice/sessions').glob('*.jsonl') for l in p.read_text().splitlines()]
        heard = audible_r8(voice, x['messages'], d)
        heard_keys = {(e['ts'],e.get('payload',{}).get('text'),e.get('payload',{}).get('receipt_key')) for e,_ in heard}
        transcripts = []
        for e in voice:
            if e.get('type') in ['transcript.user','transcript.assistant']:
                p=e.get('payload',{})
                transcripts.append(dict(time=e['ts']/1000, role=e['type'], text=p.get('text'),
                    audible=(e['ts'],p.get('text'),p.get('receipt_key')) in heard_keys))
        row = dict(case_id=cid, goal_id=sp['goal_id_private'], task=sp['turns'][0]['text'],
            pause=sp['turns'][1]['text'],resume=sp['turns'][2]['text'],state_id=sp['state_id'],
            **{k:v[k] for k in ['interaction','target','instruction','joint','failures','runner_errors']},
            previous={k:old_rows[cid][k] for k in ['interaction','target','instruction']},
            same_audio_and_state=matched, verified_execution_identity=verified,
            environment_video=v['video'], case_directory=str(d), transcripts=transcripts)
        rows.append(row)
        data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',v['video']],text=True))
        if not any(t['codec_type']=='video' for t in data['streams']):
            errors.append(cid+':video_missing')
        lines.append('|'+row['task']+'|'+'|'.join(row[k] for k in ['interaction','target','instruction'])+'|'+', '.join(row['failures'])+'|')
    check_freeze()
    if len(rows)!=10 or len({r['case_id'] for r in rows})!=10:
        errors.append('missing_duplicate_or_unexpected_case')
    paired={k:dict(gained=sum(r['previous'][k]!='pass' and r[k]=='pass' for r in rows),
                   lost=sum(r['previous'][k]=='pass' and r[k]!='pass' for r in rows))
            for k in ['interaction','target','instruction']}
    aligned=all(s['metrics'][k]['success']==10 for k in ['interaction','target','instruction'])
    lines += ['', f"首次到暂停点：{s['preparation']['first_attempt_trigger_covered']}/10；共{s['preparation']['total_attempts']}次准备。实际{len(audio)}段输入；音频质量异常{sum(not a['passed'] for a in audio)}。身份／源码／视频审计异常{len(errors)}。", '',
        '同脚本入组之后不重跑；如需修复，另开新冻结整轮。本轮为已知场景合成语音开发回归，尚不代表真人或独立泛化。主8787、其他分支和旧结果不替换。', '',
        '## 逐例原话、实际识别、播报与证据']
    for r in rows:
        d=Path(r['case_directory'])
        lines += ['', '### '+r['case_id'], '起始：'+r['task'], '暂停：'+r['pause']+'；恢复：'+r['resume'],
                  '未通过：'+str(r['failures'])+'；运行记录：'+str(r['runner_errors']),
                  f"[环境／腕部视频]({r['environment_video']}) · [实际结果]({d/'result.json'}) · [独立评分]({d/'score_r8_audited.json'})"]
        for t in r['transcripts']:
            label='用户识别' if t['role']=='transcript.user' else '实际收到播报' if t['audible'] else '生成文字／未证实播出'
            lines.append('- '+datetime.datetime.fromtimestamp(t['time']).astimezone().isoformat(timespec='seconds')+' '+label+'：'+str(t['text']))
    dest=root/'reports_final'
    dest.mkdir(exist_ok=True)
    summary=dict(time=__import__('time').time(),method='C3r recovery + R7-T3.2 + NativePrefetch-v1 + R8/T2-v3 + ShortAcceptedReceipt-v1',
        metrics=s['metrics'],paired=paired,aligned_with_previous_MX10=aligned,preparation=s['preparation'],
        input_audio_segments=len(audio),audit_errors=errors,rows=rows)
    put(dest/'summary.json',summary)
    put(dest/'AUDIO_AUDIT.json',audio)
    put(dest/'AUDIT.json',dict(unique_cases=len(rows),errors=errors,code_drift=[],
        original_audio_state_all_identical=all(r['same_audio_and_state'] for r in rows)))
    (dest/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    flat=[{k:v for k,v in r.items() if k not in ['transcripts','previous']} for r in rows]
    with (dest/'all10_cases.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    put(root/'FINAL_COMPLETED.json',dict(time=__import__('time').time(),aligned=aligned,
        metrics=s['metrics'],audit_errors=errors,report=str(dest/'RESULTS.md')))
    print(json.dumps(dict(aligned=aligned,metrics=s['metrics'],audit_errors=errors),ensure_ascii=False))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
