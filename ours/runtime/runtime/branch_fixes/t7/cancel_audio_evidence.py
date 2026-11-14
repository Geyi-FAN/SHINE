"""One unknown cancellation noun may use SAME-input, image-free ASR evidence."""
import re

def tokens(text):return re.findall(r"[a-z]+(?:'[a-z]+)?",text.lower())
def edits(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        new=[i]
        for j,y in enumerate(b,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=new
    return row[-1]

def verified_cancel(primary,evidence,pending):
    # Token matching may ignore ASR punctuation, but quoted speech/questions
    # must never become a cancellation through an acoustic noun correction.
    if not isinstance(primary,str)or re.search(r'[?？"“”「」]',primary):return None
    if not isinstance(evidence,dict)or evidence.get('kind')not in ['audio_only_relisten.v1','audio_only_grounding.v2']or evidence.get('primary')!=primary:return None
    if evidence.get('reference_sent')is not False or evidence.get('scene_sent')is not False:return None
    alternate=evidence.get('transcript')
    if not isinstance(alternate,str)or not pending or re.search(r'[?？"“”「」]',alternate):return None
    pattern=r'(?:please )?(cancel|skip) (?:the )?(.+?) task(?: keep going| carry on| keep working)?'
    a=tokens(primary);b=tokens(alternate)
    source=re.fullmatch(pattern,' '.join(a));target=re.fullmatch(pattern,' '.join(b))
    if not source or not target or len(a)!=len(b):return None
    from grounding import mentions
    if any(entity for _,entity in mentions(source[2])):return None
    named={entity for _,entity in mentions(target[2])if entity};known={entity for _,entity in mentions(pending)if entity}
    if not named or not named<=known:return None
    changed=[i for i,(x,y)in enumerate(zip(a,b))if x!=y]
    if len(changed)!=1:return None
    i=changed[0]
    if a[i]not in tokens(source[2])or b[i]not in tokens(target[2]):return None
    if edits(a[i],b[i])>2 or edits(a[i],b[i])/max(len(a[i]),len(b[i]))>.5:return None
    return alternate
