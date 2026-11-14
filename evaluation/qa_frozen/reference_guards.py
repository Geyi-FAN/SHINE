"""Fixed, transparent referent and empty-container consistency checks.

No case IDs, old labels or outcome-specific numbers. A lexical object
substitution is a hard interaction failure; ambiguous containment claims go to
independent review, never an automatic optimistic pass or Codex overwrite.
"""
import re
ALIASES={
 'bowl':[r'\bbowl\b',r'碗'],
 'ball':[r'\b(?:tennis\s+)?ball\b',r'网球',r'球'],
 'plate':[r'\bplate\b',r'盘'],
 'cheese':[r'\b(?:cream\s+)?cheese\b',r'奶酪'],
 'wine_bottle':[r'\b(?:wine\s+)?bottle\b',r'酒瓶'],
 'stove':[r'\bstove\b',r'炉灶'],
}
def entities(text):
 return {e for e,patterns in ALIASES.items()if any(re.search(p,text,re.I)for p in patterns)}
def check(packet,label):
 question=packet['original_question'];expected=entities(question)
 asr=entities(' '.join(packet.get('actual_ASR',[])))
 missing=expected-asr;introduced=asr-expected
 selected={(x['output_id'],x['epoch'])for x in label.get('relevant_output_keys',[])}
 outputs=[x for x in packet['spoken_outputs']if(x['output_id'],x['epoch'])in selected]
 if label.get('verdict')=='pass'and missing and introduced:
  for output in outputs:
   names=entities(output['text'])
   if names&introduced and missing-names:
    return dict(status='fail',reason='explicit_question_object_substitution',expected_missing=sorted(missing-names),
                asr_introduced=sorted(names&introduced),output_key=[output['epoch'],output['output_id']])
 reference=packet.get('reference_facts_at_visual_request')or packet.get('reference_at_question_end')or{}
 empty_top=bool(re.search(r'\btop\s+drawer\b',question,re.I)and re.search(r'\bempty\b',question,re.I))
 contained=reference.get('relations',{}).get('bowl_drawer')is True
 uncertainty=r'(?:无法确认|不能确认|看不到|不清楚|不能判断).{0,50}(?:是否为空|是不是空|空的)|(?:cannot|can.t|not sure|unable).{0,50}(?:empty)'
 if label.get('verdict')=='pass'and empty_top and contained:
  for output in outputs:
   if 'bowl'in entities(output['text'])and re.search(uncertainty,output['text'],re.I):
    return dict(status='review_required',reason='recognized_container_occupant_but_empty_status_uncertain',
                reference_relation='bowl_drawer=true',output_key=[output['epoch'],output['output_id']],
                note='Could describe an occluder in front versus an occupant; independent human review required, not automatic pass/fail.')
 return dict(status='no_conflict')
