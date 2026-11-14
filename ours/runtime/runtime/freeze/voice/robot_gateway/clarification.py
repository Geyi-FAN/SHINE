"""Bound dialogue evidence. The model writes instructions; this module never does."""
import re
import copy
import hashlib
import json
import time
import uuid
from interaction import classify_utterance
from semantics import confirmation_answer, confirmation_filler
from grounding import mentions, explicit_object_correction
from dialogue_evidence import dialogue_evidence

CHOICE_PATTERN=re.compile(r'(?:the\s+)?(cream cheese|wine bottle|bowl|plate|cheese|bottle|奶油奶酪|奶酪|酒瓶|盘子|碗)[\s,.;:!?，。；：！？]*(?:\bor\b|或者|还是)[\s,.;:!?，。；：！？]*(?:the\s+)?(cream cheese|wine bottle|bowl|plate|cheese|bottle|奶油奶酪|奶酪|酒瓶|盘子|碗)',re.I)

def unresolved_object_choice(text):
    return bool(CHOICE_PATTERN.search(text) and re.search(r'\b(?:could mean|might mean|may mean|undecided|not sure|unsure|either)\b|还没决定|不确定|可能指|没选好',text,re.I))

def bound_object_answer(evidence,text,normalized=None):
    """Validate an Agent-selected answer; never choose a referent or plan."""
    if normalized is not None and (not isinstance(normalized,str) or len(normalized)>80):
        raise ValueError('invalid_normalized_answer')
    if question_slot(evidence['question'],evidence['missing_slot'])!='object':
        if normalized:raise ValueError('normalized_answer_requires_object_question')
        return None
    choices=CHOICE_PATTERN.search(evidence['original_utterance'])
    correction = explicit_object_correction(text)
    if correction and normalized:
        object_only = r'(?:the\s+)?(?:cream cheese|wine bottle|cheese|bottle|bowl|plate)[.! ]*'
        selected = {entity for _, entity in mentions(normalized) if entity}
        if not re.fullmatch(object_only, normalized, re.I) or selected != {correction['object_entity']}:
            raise ValueError('normalized_answer_not_supported_by_current_user')
        if choices and not selected <= {entity for _, entity in mentions(choices.group()) if entity}:
            raise ValueError('answer_outside_user_choices')
        # Keep the actual positive placement clause as well as its object;
        # replacing the whole answer with a noun would lose the destination.
        return correction['positive_text']
    if not choices:
        if normalized:
            # Open questions may bind the user's literal object answer. This
            # does not authorize a guessed referent, ASR repair or destination.
            object_only=r'(?:the\s+)?(?:cream cheese|wine bottle|bowl|plate|cheese|bottle|奶油奶酪|奶酪|酒瓶|盘子|碗)[.!。！ ]*'
            supplied={entity for _,entity in mentions(text) if entity}
            selected={entity for _,entity in mentions(normalized) if entity}
            if not re.fullmatch(object_only,text,re.I) or not re.fullmatch(object_only,normalized,re.I) or len(supplied)!=1 or supplied!=selected:
                raise ValueError('normalized_answer_not_literal_current_user_object')
            return text
        return None
    offered={e for _,e in mentions(choices.group()) if e}
    supplied={e for _,e in mentions(text) if e}
    if normalized:
        if not re.fullmatch(r'(?:the\s+)?(?:cream cheese|wine bottle|bowl|plate|cheese|bottle|奶油奶酪|奶酪|酒瓶|盘子|碗)[.! ]*',normalized,re.I):
            raise ValueError('normalized_answer_must_be_only_an_object')
        if re.search(r'\b(?:no|not|instead)\b|不是|不要',text,re.I):
            raise ValueError('normalized_answer_not_supported_by_current_user')
        selected={e for _,e in mentions(normalized) if e}
        if len(selected)!=1 or not selected<=offered:raise ValueError('answer_outside_user_choices')
        if selected!=supplied:
            # A bounded ASR repair, explicitly chosen by the audio Agent, only
            # while answering the user's bowl/bottle choice. General ball
            # commands and explicit "not bowl" corrections still fail closed.
            if not (selected=={'bowl'} and re.fullmatch(r'(?:the\s+)?ball[.! ]*',text,re.I)
                    and re.fullmatch(r'(?:the\s+)?bowl[.! ]*',normalized,re.I)):
                raise ValueError('normalized_answer_not_supported_by_current_user')
        return normalized
    if len(supplied)==1 and supplied<=offered:return text
    return None

def question_slot(question, fallback):
    destination=bool(re.search(r'哪里|哪儿|什么(?:地方|位置)|目的地|where',question,re.I))
    obj=bool(re.search(r'哪个(?:物体|东西|对象)|哪一个|指的是|是什么|什么(?:物体|东西)|(?:which|what)\s+(?:object|item|one)',question,re.I))
    # A compound question must not overwrite the explicitly missing slot.
    if destination and obj:return fallback
    if destination:return 'destination'
    if obj:return 'object'
    return fallback

def answer_slot(evidence, text):
    """Bind user evidence to a slot, never derive an executable instruction."""
    if re.search(r'物体(?:是|指)|对象(?:是|指)|我(?:指|说)的(?:是)?|\b(?:object|item)\s+is\b',text,re.I):
        return 'object'
    if re.search(r'目的地|放到|放在|放进|放入|\b(?:put|place)\b.+\b(?:in|on|to)\b',text,re.I):
        return 'destination'
    correction=re.search(r'不是\s*(.+?)[，,]\s*(?:而)?是',text)
    if correction:
        rejected={e for _,e in mentions(correction.group(1)) if e}
        matches={t.get('slot') for t in evidence['source_utterances'][1:]
                 if rejected and rejected <= {e for _,e in mentions(t['text']) if e}}
        if len(matches)==1 and next(iter(matches)) in ('object','destination'):
            return next(iter(matches))
    return question_slot(evidence['question'],evidence['missing_slot'])

DESTINATION_NOUN = r'(?:the\s+)?(?:stove|bowl|plate|cabinet|wine rack|rack|(?:top|upper|middle)\s+drawer)'
DESTINATION_PHRASE = rf'(?P<location>(?P<relation>on top of|onto|on|into|inside|in|to)\s+(?P<destination>{DESTINATION_NOUN}))'

def _bind_open_object_placeholder(original, answers, evidence):
    """Fill a validation-only source slot using an actual literal answer.

    Raw source_utterances are never edited. This neither writes an executable
    instruction nor changes a named object, destination, action or consent.
    """
    if evidence.get('missing_slot') != 'object':
        return
    object_answers = [turn for turn in answers if turn.get('slot') == 'object']
    if len(object_answers) != 1:
        return
    answer = object_answers[0]
    text = answer['text']
    literal = r'(?:the\s+)?(?:cream cheese|wine bottle|bowl|plate|cheese|bottle|奶油奶酪|奶酪|酒瓶|盘子|碗)[.!。！ ]*'
    entities = {entity for _, entity in mentions(text) if entity}
    if not re.fullmatch(literal, text, re.I) or len(entities) != 1:
        return
    # Exactly one open source slot. Multiple unknown objects need further
    # clarification; do not apply one answer to every manipulation clause.
    pattern = re.compile(
        r'\b(?:put|place|move|pick up|grab|return)\s+'
        r'(?P<object>something|(?:an?|the)\s+(?:object|item))'
        r'(?=\s+(?:on|onto|in|into|inside|to|back|from)\b|[,.!?;\n]|$)',
        re.I,
    )
    matches = list(pattern.finditer(original['text']))
    if len(matches) != 1:
        return
    match = matches[0]
    bound = text.strip(' .!。！')
    raw = original['text']
    original['text'] = raw[:match.start('object')] + bound + raw[match.end('object'):]
    original['slot_bindings'] = [dict(
        slot='object', placeholder=match.group('object'), bound_entity=next(iter(entities)),
        bound_text=bound, answer_input_id=answer['input_id'],
        source='current_clarification_literal_user_answer',
    )]

def _bind_open_destination_placeholder(original, answers, evidence):
    """Bind only a real, unambiguous destination answer in the validation view."""
    if evidence.get('missing_slot') != 'destination':
        return
    candidates = [t for t in answers if t.get('slot') == 'destination']
    if len(candidates) != 1:
        return
    answer = candidates[0]
    # This is an evidence grammar, not an instruction generator. A question,
    # negative/conditional answer or multiple destinations cannot fill a slot.
    prefix = r'(?:(?:please\s+)?(?:put|place|move)\s+(?P<object>it|(?:the\s+)?(?:cream cheese|wine bottle|bowl|plate|cheese|bottle))\s+)?'
    match = re.fullmatch(prefix + DESTINATION_PHRASE + r'(?:,?\s+please)?[.! ]*', answer['text'].strip(), re.I)
    if not match:
        return
    from grounding import slots
    sources = [noun for role, noun in slots(original['text']) if role == 'source']
    if len(sources) != 1:
        return
    source_entities = {entity for _, entity in mentions(sources[0]) if entity}
    if len(source_entities) != 1:
        return
    named_object = match.group('object')
    if named_object and named_object.lower() != 'it':
        if {entity for _, entity in mentions(named_object) if entity} != source_entities:
            raise ValueError('instruction_entity_mismatch: 目的地回答不能替换此前已明确的操作对象。')
    pattern = re.compile(r'\b(?:in|into|inside|on|onto|to)\s+(?:a\s+different|another|some)\s+(?:place|location|spot)\b', re.I)
    placeholders = list(pattern.finditer(original['text']))
    if len(placeholders) != 1:
        return
    placeholder = placeholders[0]
    raw = original['text']
    original['text'] = raw[:placeholder.start()] + match.group('location') + raw[placeholder.end():]
    original.setdefault('slot_bindings', []).append(dict(
        slot='destination', placeholder=placeholder.group(), bound_text=match.group('location'),
        bound_entity=next(entity for _, entity in mentions(match.group('destination')) if entity),
        relation=match.group('relation').lower(), answer_input_id=answer['input_id'],
        source='current_clarification_literal_user_destination',
    ))

def _validate_bound_destination(evidence, instruction):
    """A supplied surface target must not become a containment target, or vice versa."""
    family = lambda relation: ('surface' if relation in ('on', 'onto', 'on top of')
                               else 'containment' if relation in ('in', 'into', 'inside') else relation)
    for turn in evidence.get('active_source_utterances', []):
        for binding in turn.get('slot_bindings', []):
            if binding['slot'] != 'destination':
                continue
            matches = [m for m in re.finditer(r'\b' + DESTINATION_PHRASE, instruction, re.I)
                       if binding['bound_entity'] in {entity for _, entity in mentions(m.group('destination')) if entity}]
            if len(matches) != 1 or (binding['relation'] is not None and family(matches[0].group('relation').lower()) != family(binding['relation'])):
                raise ValueError('clarification_destination_relation_mismatch: 生成的任务未保留本轮回答的目的地与放置关系；未下发新动作。')

def _bind_deictic_placement(original, answers, evidence):
    """Resolve two open slots only from explicit answers in this transaction.

    This modifies a validation copy, not raw speech or the Agent's instruction.
    No scene prior, model-written instruction or earlier episode supplies a slot.
    """
    if evidence.get('missing_slot') not in ('object', 'destination', 'reference'):
        return
    pattern = re.compile(r'\b(?:put|place|move)\s+(?P<object>it|this|that|(?:an?|the)\s+(?:object|item)|something)\s+(?P<location>(?:over\s+)?there|somewhere(?:\s+else)?)\b', re.I)
    matches = list(pattern.finditer(original['text']))
    if len(matches) != 1:
        return
    object_noun = r'(?:the\s+)?(?:cream cheese|wine bottle|bowl|plate|cheese|bottle)'
    literal = object_noun + r'[.! ]*'
    prefix = rf'(?:(?:please\s+)?(?:put|place|move)\s+(?P<object>it|{object_noun})\s+)?'
    order = {turn['input_id']: i for i, turn in enumerate(evidence['source_utterances'])}
    obj = destination = None
    for turn in sorted(answers, key=lambda t: order[t['input_id']]):
        text = turn['text'].strip()
        if turn.get('slot') == 'object' and re.fullmatch(literal, text, re.I):
            obj = (text.strip(' .!'), turn)
        match = re.fullmatch(prefix + DESTINATION_PHRASE + r'(?:,?\s+please)?[.! ]*', text, re.I)
        if match:
            noun = match.group('object')
            if noun and noun.lower() != 'it':
                obj = (noun, turn)
            destination = (match.group('location'), match.group('destination'), match.group('relation').lower(), turn)
        nominal = re.fullmatch(rf'(?:the\s+)?destination\s+is\s+(?P<destination>{DESTINATION_NOUN})[.! ]*', text, re.I)
        if nominal and turn.get('slot') == 'destination':
            # User selected a target but supplied no on/in relation. 'to' is
            # only a neutral validation-slot link, never a generated Task.
            noun = nominal.group('destination')
            destination = ('to ' + noun, noun, None, turn)
    if not obj or not destination:
        return
    object_entities = {entity for _, entity in mentions(obj[0]) if entity}
    target_entities = {entity for _, entity in mentions(destination[1]) if entity}
    if len(object_entities) != 1 or len(target_entities) != 1 or object_entities == target_entities:
        return
    match = matches[0]
    # Replace only those two spans; all other actions, consent and constraints
    # in the original utterance continue through the existing semantic checks.
    raw = original['text']
    original['text'] = (raw[:match.start('object')] + obj[0]
                        + raw[match.end('object'):match.start('location')]
                        + destination[0] + raw[match.end('location'):])
    original.setdefault('slot_bindings', []).extend([
        dict(slot='object', placeholder=match.group('object'), bound_text=obj[0],
             bound_entity=next(iter(object_entities)), answer_input_id=obj[1]['input_id'],
             source='current_clarification_explicit_placement_answer'),
        dict(slot='destination', placeholder=match.group('location'), bound_text=destination[0],
             bound_entity=next(iter(target_entities)), relation=destination[2],
             answer_input_id=destination[3]['input_id'],
             source='current_clarification_explicit_placement_answer'),
    ])

def effective_clarification_turns(evidence):
    turns=evidence['source_utterances'];active={}
    for i,turn in enumerate(turns[1:]):
        slot=turn.get('slot') or question_slot(evidence['questions'][min(i,len(evidence['questions'])-1)],evidence['missing_slot'])
        active[slot if slot in ('object','destination') else slot+':'+str(i)]=turn
    original=copy.deepcopy(turns[0])
    original['text']=original.get('acoustic_normalized_text',original['text'])
    # Explicit self-correction of the one drawer command, not a sequence.
    text=original['text']
    if '说错了' in text:
        before,after=text.rsplit('说错了',1)
        if '抽屉' in after and re.search(r'打开|关上|关闭',after) and not re.search(r'然后|之后|并且|再把|先',before):
            original['text']=after.strip('，。 ,')
    answers=[]
    for turn in active.values():
        turn=copy.deepcopy(turn)
        turn['text']=turn.get('acoustic_normalized_text',turn['text'])
        correction = explicit_object_correction(turn['text'])
        turn['text']=turn.get('normalized_text',turn['text'])
        if correction:
            turn['text'] = correction['positive_text']
            turn['object_correction'] = correction
        # "不是碗，是奶酪" is a corrected slot, not an instruction to move
        # both objects. Raw speech remains unchanged in source_utterances.
        turn['text']=re.sub(r'^(?:不对[，,]\s*)?不是\s*[^，,。;；]+[，,]\s*(?:而)?是\s*','',turn['text'])
        answers.append(turn)
    # Alternatives are options, not a requirement to operate BOTH objects.
    # Replace only the explicit option span using an actually bound user answer.
    for answer in answers:
        if answer.get('slot')=='object':
            supplied={e for _,e in mentions(answer['text']) if e}
            if len(supplied)==1:
                def pick(match):
                    offered={e for _,e in mentions(match.group()) if e}
                    return answer['text'].strip(' .!') if supplied<=offered else match.group()
                # ASR may finalize "bowl. Or the wine bottle." as two
                # sentences. Bind the explicit option span BEFORE splitting;
                # otherwise the unchosen noun remains a false requirement.
                original['text']=CHOICE_PATTERN.sub(pick,original['text'])
                parts=re.split(r'(?<=[.!?。])\s*',original['text'])
                kept=[]
                for part in parts:
                    if CHOICE_PATTERN.search(part) and not re.search(r'\b(?:return|put|place|move|open|close|release)\b|把|归位|放回|打开|关闭',part,re.I):
                        continue # The bound answer replaces this option introduction.
                    if re.fullmatch(r"\s*I(?:\s+am|'m)\s+(?:undecided|not sure|unsure)[.!? ]*",part,re.I):
                        continue
                    kept.append(CHOICE_PATTERN.sub(pick,part))
                original['text']=' '.join(kept)
    _bind_open_object_placeholder(original, answers, evidence)
    _bind_open_destination_placeholder(original, answers, evidence)
    _bind_deictic_placement(original, answers, evidence)
    return [original]+answers

def bind_clarification_acoustics(state,evidence):
    """Carry stored same-input acoustic evidence across clarification turns.

    Raw utterances stay intact. Only the existing narrow unknown-source-noun
    check may supply a validation view; Agent questions/options never do.
    The complete instruction still passes the existing consent/semantic gates.
    """
    from speech_relisten import validated_source_listen
    for turn in evidence['source_utterances']:
        row=state.db.execute('SELECT u.text,e.payload FROM utterances u JOIN events e ON e.id=u.event_id WHERE u.id=? AND u.episode=?',
                             (turn['input_id'],state.episode)).fetchone()
        if not row or row[0]!=turn['text']:continue
        proof=json.loads(row[1]).get('asr_evidence')
        if not isinstance(proof,dict) or proof.get('scene_sent')is not False:continue
        resolved=validated_source_listen(row[0],proof,state.scene_inventory)
        if resolved is None:continue
        turn['acoustic_normalized_text']=resolved
        turn['acoustic_source_evidence']=dict(source_input_id=turn['input_id'],primary=row[0],
            transcript=resolved,reference_sent=False,scene_sent=False,kind='stored_same_input_acoustic_evidence')

class ClarificationMixin:
    def _clear_clarification(self, reason):
        if self.pending_clarification:
            old,self.pending_clarification=self.pending_clarification,None
            self.event('clarification_invalidated',dict(clarification_id=old['clarification_id'],reason=reason))

    def _expire_clarification(self):
        p=self.pending_clarification
        if p and (p['episode_id']!=self.episode or p['task_version']!=self.version or time.time()>=p['expires_at']):
            self._clear_clarification('expired_or_stale')

    def _clarification_command(self,name,args,request_id,digest):
        # The caller has already checked receipt deduplication, episode and version.
        self._expire_clarification()
        text=str(args.get('user_utterance','')).strip()
        input_id=args.get('voice_input_id')
        if not text or len(text)>1000 or not isinstance(input_id,str) or not input_id:
            raise ValueError('clarification_requires_user_text_and_input_id')
        if name=='robot_begin_clarification':
            if classify_utterance(text)!='cloud_decision' or confirmation_answer(text):
                raise ValueError('clarification_requires_task_request')
            if self.pending_proposal or self.deferred_task:
                raise ValueError('resolve_existing_proposal_or_waiting_first')
            question=args.get('question');slot=args.get('missing_slot')
            if not isinstance(question,str) or not 1<=len(question)<=500 or slot not in ('object','destination','order','constraint','reference'):
                raise ValueError('invalid_clarification_question')
            self._clear_clarification('replaced')
            self.pending_clarification=dict(clarification_id=uuid.uuid4().hex,episode_id=self.episode,
                task_version=self.version,task_id=self.task_id,created_at=time.time(),expires_at=time.time()+120,
                original_utterance=text,source_utterances=[dict(input_id=input_id,text=text)],question=question,
                missing_slot=slot,questions=[question],status='awaiting_answer')
            context=dialogue_evidence(self)['correction_context']
            if context and context['correction_input_ids'][-1]==input_id:
                turns=context['source_utterances']
                self.pending_clarification.update(original_utterance=turns[0]['text'],
                    source_utterances=[dict(input_id=t['input_id'],text=t['text'],**({'slot':'object'} if i else {})) for i,t in enumerate(turns)],
                    speech_correction_evidence=copy.deepcopy(context))
            self.event('clarification_created',copy.deepcopy(self.pending_clarification))
            return self._save_receipt(request_id,digest,dict(status='needs_clarification',executed=False,**self.snapshot()))
        p=self.pending_clarification
        if not p or args.get('clarification_id')!=p['clarification_id']:
            raise ValueError('unknown_or_expired_clarification')
        if name=='robot_cancel_clarification':
            if classify_utterance(text)!='cancel' and args.get('source')=='qwen_realtime_current_user':
                raise ValueError('clarification_cancel_requires_explicit_cancel')
            self._clear_clarification('user_cancelled')
            return self._save_receipt(request_id,digest,dict(status='clarification_cancelled',executed=False,**self.snapshot()))
        if input_id in [x['input_id'] for x in p['source_utterances']]:
            raise ValueError('clarification_requires_new_answer')
        if confirmation_answer(text) or confirmation_filler(text) or classify_utterance(text)!='cloud_decision':
            raise ValueError('clarification_requires_content_not_confirmation_or_control')
        if len(p['source_utterances'])>=6:raise ValueError('clarification_turn_limit')
        evidence=copy.deepcopy(p)
        normalized=bound_object_answer(p,text,args.get('resolved_answer'))
        evidence['source_utterances'].append(dict(input_id=input_id,text=text,slot=answer_slot(p,text),
            **({'normalized_text':normalized,'normalization_source':'Agent answer bound to current user object evidence'} if normalized else {})))
        instruction=args.get('instruction');question=args.get('question')
        if bool(instruction)==bool(question):raise ValueError('supply_instruction_or_followup_question')
        if question:
            if not isinstance(question,str) or not 1<=len(question)<=500:raise ValueError('invalid_clarification_question')
            evidence['question']=question;evidence['questions'].append(question)
            self.pending_clarification=evidence
            self.event('clarification_answer_bound',dict(clarification_id=p['clarification_id'],input_id=input_id,text=text,question=question))
            return self._save_receipt(request_id,digest,dict(status='needs_clarification',executed=False,**self.snapshot()))
        if not isinstance(instruction,str) or not 1<=len(instruction)<=2000:raise ValueError('invalid_resolved_instruction')
        # User turns only; never include the agent question/options as authorization.
        bind_clarification_acoustics(self,evidence)
        evidence['active_source_utterances']=effective_clarification_turns(evidence)
        combined='\n'.join(x['text'] for x in evidence['active_source_utterances'])
        supplied={e for _,e in mentions(combined) if e}
        proposed={e for _,e in mentions(instruction) if e}
        if proposed-supplied:
            raise ValueError('clarification_invented_entity: answer must ground every task object/destination')
        _validate_bound_destination(evidence, instruction)
        evidence['resolved_instruction']=instruction;evidence['status']='resolved'
        candidate=dict(episode_id=self.episode,expected_task_version=self.version,instruction=instruction,
            user_utterance=combined,voice_input_id=input_id,source='qwen_realtime_current_user',
            _clarification_evidence=evidence)
        # Existing semantic/confirmation rules still apply. No bypass of consent.
        result=self._command('robot_revise_task' if self.task_id else 'robot_start_task',candidate,
            'clarified:'+hashlib.sha256(request_id.encode()).hexdigest(), clarified=True)
        self._clear_clarification('resolved')
        self.event('clarification_resolved',dict(clarification_id=p['clarification_id'],source_utterances=evidence['source_utterances'],resolved_instruction=instruction, consumed_by_task_id=result.get('task_id') if result.get('status')=='accepted' else None, successor_transaction_id=(self.pending_proposal or {}).get('proposal_id')))
        return self._save_receipt(request_id,digest,dict(result,**self.snapshot(),request_id=request_id,clarification_id=p['clarification_id']))
