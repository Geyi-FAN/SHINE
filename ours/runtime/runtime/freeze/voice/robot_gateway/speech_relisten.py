"""Narrow evidence reconciliation, never an object alias or a task planner."""
import re
from grounding import mentions,slots,validate_grounding

def _tokens(s):return re.findall(r"[a-z]+(?:'[a-z]+)?",s.lower())
def _edits(a,b):
 row=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  new=[i]
  for j,y in enumerate(b,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(x!=y)))
  row=new
 return row[-1]

def validated_source_listen(primary,evidence,inventory):
 if not isinstance(evidence,dict) or evidence.get('kind') not in ('audio_only_relisten.v1','audio_only_grounding.v2','scene_vocab_audio_review.v3') or evidence.get('primary')!=primary:return None
 alt=evidence.get('transcript')
 if not isinstance(alt,str) or not alt or len(alt)>4000 or not inventory:return None
 contextual=evidence.get('kind')=='scene_vocab_audio_review.v3'
 if evidence.get('reference_sent') is not False:return None
 if contextual:
  ids=sorted(x['id']for x in inventory.get('entities',[]))
  if evidence.get('scene_sent')is not True or evidence.get('vocabulary_ids')!=ids or evidence.get('decision')!='acoustically_supported':return None
  if not re.fullmatch(r'[0-9a-f]{64}',str(evidence.get('audio_sha256',''))):return None
  if re.search(r"\b(?:not|never|don.t|instead of|rather than)\b",primary,re.I):return None
  if not any(role=='source'and re.fullmatch(r'(?:the |a |an )?ball',noun,re.I)for role,noun in slots(primary)):return None
 elif evidence.get('scene_sent') is not False:return None
 a,b=_tokens(primary),_tokens(alt)
 if len(a)!=len(b):return None
 changed=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
 if not changed or len(changed)>2:return None
 # Only an unresolved manipulated noun can use new acoustic evidence. A known
 # scene noun, explicit absent object, action, destination, or negation cannot.
 sources=[noun for role,noun in slots(primary) if role=='source' and not mentions(noun)]
 unknown_words={t for noun in sources for t in _tokens(noun)}-{'the','a','an','it','there','its','their'}
 known_words={t for _,noun in slots(alt) for _,entity in mentions(noun) if entity for t in _tokens(noun)}-{'the','a','an'}
 for i in changed:
  if a[i] not in unknown_words or b[i] not in known_words:return None
  if abs(len(a[i])-len(b[i]))>2 or _edits(a[i],b[i])>2 or _edits(a[i],b[i])/max(len(a[i]),len(b[i]))>.5:return None
 if not any(role=='source' and any(entity for _,entity in mentions(noun)) for role,noun in slots(alt)):return None
 return alt

def validated_relisten(primary,evidence,instruction,inventory):
 alt=validated_source_listen(primary,evidence,inventory)
 if alt is None:return None
 try:validate_grounding(alt,instruction,inventory)
 except ValueError:return None
 return alt
