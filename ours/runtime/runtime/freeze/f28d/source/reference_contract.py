"""Describe supplied points and reject invented missing references; never plan."""
import copy

ADDENDUM='''
REFERENCE REQUEST CONTRACT:
physical_state.supplied_reference_ledger restates the SAME reference_availability,
grouped by time. Read every available current reference before asking for it.
A historical grasp does not mean current ownership; if current held_object is none,
you may author a new grasp when its current point and prerequisites are supplied.
For need_observation, add request.evidence_requests (or top-level evidence_requests): a nonempty list of objects with kind
reference|ownership|support|path|relation|drawer_state and a specific reason.
A reference item MUST name entity, keypoint, time_source. Never claim an available
reference is missing. For ownership/support/path/relation/drawer_state name the
entity and the actual uncertain physical fact; point availability alone does NOT
prove these facts. Other statuses need no evidence_requests. This validator does
not choose the next subgoal; regenerate your OWN valid plan or justified request.
'''


def explain(inp):
    out=copy.deepcopy(inp);ledger={}
    for ref in inp.get('reference_availability',[]):
        ledger.setdefault(ref['time_source'],{})[ref['entity']+'.'+ref['keypoint']]=ref.get('available')
    out['physical_state']['supplied_reference_ledger']=dict(points=ledger,
        meaning='Literal index of supplied reference_availability, not a position estimate, action choice, ownership or completion proof')
    return out


def errors(inp,out):
    if not isinstance(out,dict)or out.get('status')!='need_observation':return []
    asks=out.get('evidence_requests')
    nested=out.get('request')
    nested_asks=nested.get('evidence_requests') if isinstance(nested,dict) else None
    if asks is not None and nested_asks is not None and asks!=nested_asks:
        return ['Conflicting top-level and nested evidence_requests; send one consistent request.']
    if asks is None:asks=nested_asks
    if not isinstance(asks,list)or not asks:return ['need_observation requires nonempty evidence_requests; identify the actual missing reference or physical evidence.']
    errors=[]
    for ask in asks:
        if not isinstance(ask,dict)or ask.get('kind')not in('reference','ownership','support','path','relation','drawer_state'):
            errors.append('Each evidence request needs a documented kind.');continue
        if not isinstance(ask.get('reason'),str)or not ask['reason'].strip():errors.append('State the specific missing evidence, not just observe again.')
        if not isinstance(ask.get('entity'),str):errors.append('Name the entity whose evidence is missing.')
        if ask['kind']=='reference':
            ref={k:ask.get(k)for k in('entity','keypoint','time_source')}
            if any(v is None for v in ref.values()):errors.append('A reference request needs entity, keypoint and time_source.');continue
            supplied=next((r for r in inp.get('reference_availability',[])if all(r.get(k)==v for k,v in ref.items())),None)
            if supplied and supplied.get('available')is True:
                errors.append('CONTRADICTION: '+str(ref)+' is explicitly available:true. Do not demand that point; regenerate your own plan or identify a different genuinely uncertain physical fact.')
    return errors
