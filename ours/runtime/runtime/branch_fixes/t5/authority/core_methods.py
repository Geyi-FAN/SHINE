def record_interaction(self, body):
    """Final transcript telemetry only. No motion or implicit authorization."""
    with self.lock:
        if body.get('episode_id') != self.episode:
            raise TaskError('stale_episode')
        (text, identifier) = (body.get('text'), body.get('input_id'))
        if not isinstance(text, str) or not 0 < len(text) <= 4000:
            raise TaskError('invalid_transcript')
        if not isinstance(identifier, str) or not 0 < len(identifier) <= 256:
            raise TaskError('invalid_input_id')
        prior = self.db.execute('SELECT episode,text,event_id FROM utterances WHERE id=?', (identifier,)).fetchone()
        if prior:
            if prior[0] != self.episode or prior[1] != text:
                raise TaskError('input_id_conflict')
            return {'status': 'recorded', 'event_id': prior[2], 'duplicate': True}
        self._expire_proposal()
        if self.pending_proposal and identifier != self.pending_proposal.get('voice_input_id') and (confirmation_answer(text, (self.pending_proposal or {}).get('instruction')) is None) and (not confirmation_filler(text)) and (classify_utterance(text) not in ('question', 'backchannel', 'non_command')):
            self._clear_proposal('new_user_input')
        kind = classify_utterance(text)
        if self.deferred_task and deferred_update_request(text):
            self._block_deferred_update(identifier, text)
        self.last_interaction = {'text': text, 'classification': kind, 'input_id': identifier, 'observed_at': body.get('observed_at'), 'received_at': time.time()}
        evidence = body.get('asr_evidence')
        if isinstance(evidence, dict) and evidence.get('kind') in ('audio_only_relisten.v1', 'audio_only_grounding.v2') and (evidence.get('primary') == text):
            self.last_interaction['asr_evidence'] = copy.deepcopy(evidence)
        event_id = self.event('speech_classified', {**self.last_interaction, 'source': 'cloud_final_transcript', 'action': 'record_only', 'observed_task_version': body.get('task_version')})
        self.db.execute('INSERT INTO utterances VALUES (?,?,?,?)', (identifier, self.episode, text, event_id))
        self.db.commit()
        result = {'status': 'recorded', 'event_id': event_id, 'classification': kind, 'action': 'record_only'}
        decision = confirmation_answer(text, (self.pending_proposal or {}).get('instruction'))
        if decision and self.pending_proposal and (identifier != self.pending_proposal.get('voice_input_id')) and (body.get('task_version') == self.version):
            result['confirmation'] = {'proposal_id': self.pending_proposal['proposal_id'], 'decision': decision}
        return result

def _resolve_proposal(self, args, request_id, digest):
    self._expire_proposal()
    proposal = self.pending_proposal
    if not proposal or args.get('proposal_id') != proposal['proposal_id']:
        raise TaskError('unknown_or_expired_proposal: 请重新说明需要执行的任务。')
    decision = args.get('decision')
    if decision not in ('confirm', 'reject'):
        raise TaskError('invalid_confirmation_decision')
    if args.get('source') == 'qwen_realtime_current_user':
        if confirmation_answer(args.get('user_utterance', ''), proposal['instruction']) != decision:
            raise TaskError('confirmation_requires_explicit_answer: 当前话语不是对该提议的明确确认或拒绝。')
        if not args.get('voice_input_id') or args['voice_input_id'] == proposal.get('voice_input_id'):
            raise TaskError('confirmation_requires_new_user_input')
    self.pending_proposal = None
    self.event('proposal_resolved', {'proposal_id': proposal['proposal_id'], 'decision': decision, 'instruction': proposal['instruction']})
    if decision == 'reject':
        return self._save_receipt(request_id, digest, {'status': 'proposal_rejected', 'executed': False, **self.snapshot()})
    resolved_args = {'episode_id': self.episode, 'expected_task_version': self.version, 'instruction': proposal['instruction'], 'user_utterance': proposal['user_utterance'], 'source': proposal['source'], 'memory_ids': proposal['memory_ids'], 'voice_input_id': args.get('voice_input_id'), '_clarification_evidence': proposal.get('clarification_evidence'), '_confirmation_source_input_id': proposal.get('voice_input_id')}
    if proposal['memory_id']:
        resolved_args['memory_id'] = proposal['memory_id']
    result = self._command(proposal['operation'], resolved_args, 'confirmed:' + hashlib.sha256(request_id.encode()).hexdigest(), confirmed=proposal['proposal_id'], clarified=bool(proposal.get('clarification_evidence')))
    result = {**result, 'request_id': request_id, 'confirmed_proposal_id': proposal['proposal_id']}
    return self._save_receipt(request_id, digest, result)

def _command(self, name, args, request_id, confirmed=None, clarified=False):
    if name == 'robot_get_status':
        value = self.snapshot()
        histories = self.task_history()
        value['current_reference'] = self._current_instruction_reference(histories)
        value['dialogue_evidence'] = dialogue_evidence(self)
        value['qa_evidence'] = {'source': 'episode_execution_records_not_current_object_pose', 'episode_id': self.episode, 'drawer_facts': getattr(self, 'qa_drawers', None), 'warning': 'Requested/accepted is NOT success. Verified completion is historical, not proof of current position. Compare later tasks and CURRENT images; never infer absence from occlusion.', 'recent_tasks': [{k: t.get(k) for k in ('task_id', 'complete_instruction', 'instruction_memory_id', 'state', 'completion', 'ever_verified_completed', 'last_event_at', 'is_current')} for t in histories[:8]]}
        return value
    if name == 'robot_query_memory':
        histories = self.task_history()
        return {'episode_id': self.episode, 'current_reference': self._current_instruction_reference(histories), 'events': self.memory(args.get('query', ''), args.get('limit', 12)), 'task_selection': select_tasks(histories, args.get('query', ''), self.task_id)}
    if name not in self.MUTATIONS:
        raise TaskError('Unknown robot tool')
    if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
        raise TaskError('request_id required')
    with self.lock:
        digest = hashlib.sha256(json.dumps([name, args], sort_keys=True).encode()).hexdigest()
        row = self.db.execute('SELECT digest,result FROM receipts WHERE id=?', (request_id,)).fetchone()
        if row:
            if row[0] != digest:
                raise TaskError('request_id reused with different arguments')
            return json.loads(row[1])
        if args.get('episode_id') != self.episode:
            raise TaskError('stale_episode: call robot_get_status again')
        if type(args.get('expected_task_version')) is not int or args['expected_task_version'] != self.version:
            if not self._same_completed_deferred_update(name, args):
                raise TaskError('stale_task_version: call robot_get_status; do not guess a new version')
            self.event('deferred_update_execution_revalidated', dict(deferred_id=args['deferred_id'], expected_execution_version=args['expected_task_version'], current_execution_version=self.version, task_intent_revision=self.task_intent_revision, reason='same_recorded_input_and_transaction_after_predecessor_completion'))
        if not self.ready:
            raise TaskError('policy_or_environment_not_ready')
        correction_ids = args.get('correction_input_ids')
        if correction_ids is not None:
            context = dialogue_evidence(self)['correction_context']
            if name not in ('robot_start_task', 'robot_revise_task', 'robot_propose_task', 'robot_schedule_task') or args.get('source') != 'qwen_realtime_current_user' or (not context) or (correction_ids != context['correction_input_ids']) or (args.get('voice_input_id') != correction_ids[-1]) or (args.get('user_utterance') != context['source_utterances'][-1]['text']):
                raise TaskError('correction_context_stale_or_unbound')
            try:
                validate_correction_instruction(context, str(args.get('instruction', '')))
            except ValueError as exc:
                raise TaskError(str(exc)) from exc
            args = {**args, 'user_utterance': '\n'.join((t['text'] for t in context['source_utterances'])), '_speech_correction_evidence': copy.deepcopy(context)}
            self.event('speech_correction_bound', dict(correction_input_ids=correction_ids, source_utterances=context['source_utterances']))
        try:
            self.dialogue_transactions.check(self, name, args)
        except ValueError as exc:
            raise TaskError(str(exc)) from exc
        if name in ('robot_begin_clarification', 'robot_answer_clarification', 'robot_cancel_clarification'):
            try:
                return self._clarification_command(name, args, request_id, digest)
            except ValueError as exc:
                raise TaskError(str(exc)) from exc
        if name == 'robot_resolve_proposal':
            return self._resolve_proposal(args, request_id, digest)
        if args.get('source') == 'qwen_realtime_current_user':
            if confirmation_answer(args.get('user_utterance', '')) and (not confirmed):
                raise TaskError('speech_does_not_authorize_this_action: 确认或拒绝只能处理当前有效提议。')
            speech_kind = classify_utterance(args.get('user_utterance', ''))
            if not allowed_voice_action(speech_kind, name):
                raise TaskError('speech_does_not_authorize_this_action: ' + speech_kind)
            if not clarified and name in ('robot_start_task', 'robot_revise_task', 'robot_restore_task', 'robot_schedule_task', 'robot_replace_deferred', 'robot_propose_task', 'robot_resume') and unresolved_object_choice(args.get('user_utterance', '')):
                raise TaskError('unresolved_user_choice: 用户明确表示对象未选定，必须先澄清，未下发动作。')
        if name in ('robot_schedule_task', 'robot_replace_deferred', 'robot_cancel_deferred'):
            return self._deferred_command(name, args, request_id, digest)
        if name == 'robot_start_task' and self.mode in ('running', 'verifying'):
            raise TaskError('task_already_running: use robot_revise_task')
        if name in ('robot_resume', 'robot_revise_task', 'robot_cancel_task') and (not self.task_id):
            raise TaskError('no_current_task')
        if name == 'robot_resume' and self.mode not in ('paused', 'budget_exhausted'):
            raise TaskError('only_a_paused_task_can_resume')
        if name == 'robot_pause' and self.mode not in ('running', 'verifying', 'paused', 'budget_exhausted'):
            raise TaskError('no_running_or_paused_task')
        if name == 'robot_finish_task' and self.mode not in ('running', 'verifying', 'paused', 'budget_exhausted', 'needs_review'):
            raise TaskError('no_active_task_to_finish')
        instruction = args.get('instruction', '')
        source_memory = None
        if name == 'robot_restore_task':
            row = self.db.execute('SELECT payload FROM events WHERE id=? AND episode=? AND kind=?', (args.get('memory_id'), self.episode, 'task_instruction')).fetchone()
            if not row:
                raise TaskError('unknown_instruction_memory_in_this_episode')
            instruction = json.loads(row[0])['instruction']
            source_memory = args['memory_id']
        if name in ('robot_start_task', 'robot_revise_task', 'robot_restore_task', 'robot_propose_task'):
            if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 900:
                raise TaskError('instruction must be complete English text, 1..900 characters')
            if len(instruction.split()) > 100:
                raise TaskError('instruction_too_long: retain constraints in a concise complete instruction')
            refs = args.get('memory_ids', [])
            if not isinstance(refs, list) or len(refs) > 10:
                raise TaskError('invalid_memory_references')
            for ref in refs:
                if not isinstance(ref, str) or not self.db.execute('SELECT 1 FROM events WHERE id=? AND episode=? AND kind="task_instruction"', (ref, self.episode)).fetchone():
                    raise TaskError('memory_reference_not_in_current_episode')
            if refs and args.get('source') == 'qwen_realtime_current_user':
                from grounding import validate_pronoun_source
                memory_instructions = [json.loads(self.db.execute('SELECT payload FROM events WHERE id=? AND episode=? AND kind="task_instruction"', (ref, self.episode)).fetchone()[0])['instruction'] for ref in refs]
                try:
                    validate_pronoun_source(args.get('user_utterance', ''), instruction, memory_instructions)
                except ValueError as exc:
                    raise TaskError(str(exc)) from exc
            requested_instruction = instruction.strip()
            (instruction, normalization) = normalize_instruction(requested_instruction, self.instruction)
            semantic_check = None
            if args.get('source') == 'qwen_realtime_current_user' or name == 'robot_propose_task':
                try:
                    from speech_relisten import validated_relisten
                    grounding_text = None
                    speech_input_id = args.get('voice_input_id')
                    if confirmed:
                        speech_input_id = args.get('_confirmation_source_input_id') or speech_input_id
                    speech = self.db.execute('SELECT u.text,e.payload FROM utterances u JOIN events e ON e.id=u.event_id WHERE u.id=? AND u.episode=?', (speech_input_id, self.episode)).fetchone()
                    if speech and speech[0] == args.get('user_utterance', ''):
                        evidence = json.loads(speech[1]).get('asr_evidence')
                        grounding_text = validated_relisten(speech[0], evidence, instruction, self.scene_inventory)
                        if grounding_text:
                            args = {**args, '_speech_correction_evidence': dict(kind='validated_acoustic_source.v1', source_input_id=speech_input_id, primary=speech[0], audio_only_alternative=grounding_text, reference_sent=False, scene_sent=False)}
                            self.event('speech_acoustic_evidence_used', dict(voice_input_id=args.get('voice_input_id'), source_input_id=speech_input_id, primary=speech[0], audio_only_alternative=grounding_text, candidate_instruction=instruction))
                    semantic_check = inspect_semantics(args.get('user_utterance', ''), instruction, self.scene_inventory, referenced=bool(source_memory or refs or clarified), previous=self.instruction, grounding_utterance=grounding_text)
                except ValueError as exc:
                    raise TaskError(str(exc)) from exc
                if source_memory and args.get('source') == 'qwen_realtime_current_user':
                    selection = select_tasks(self.task_history(), args.get('user_utterance', ''), self.task_id)
                    if not any((t.get('instruction_memory_id') == source_memory for t in selection['candidates'])):
                        raise TaskError('memory_reference_does_not_match_temporal_query')
                    if selection['resolution'] == 'ambiguous':
                        semantic_check['uncertainties'].append('历史任务指代存在多个候选，请确认具体指令')
                        semantic_check['decision'] = 'needs_confirmation'
                self.event('semantic_checked', {'instruction': instruction, 'semantic_check': semantic_check})
            contract = candidate_contract(self.episode, self.version, name, instruction, args, semantic_check, self.observed_at)
            self.event('task_candidate_checked', {'candidate': contract})
            if name == 'robot_propose_task' or (semantic_check and semantic_check['decision'] == 'needs_confirmation' and (not confirmed)):
                return self._create_proposal(name, args, instruction, semantic_check, request_id, digest)
            self._hold('superseded', name)
            if self.task_id:
                self.event('task_superseded', {'next_operation': name})
            self.task_intent_revision += 1
            self.task_id = uuid.uuid4().hex
            self.instruction = instruction.strip()
            self.normalization = normalization
            self.last_error = None
            self.completion_monitor = CompletionMonitor(self.instruction)
            self.latest_evidence = {}
            self.task_record = build_task_record(self.task_id, self.episode, name, self.instruction, requested_instruction, {**args, '_request_id': request_id}, self.completion_monitor, self.observed_at)
            self.task_record['candidate_contract'] = contract
            self.task_record['semantic_check'] = semantic_check
            self.task_record['confirmed_proposal_id'] = confirmed
            self.task_record['speech_correction_evidence'] = copy.deepcopy(args.get('_speech_correction_evidence'))
            self.completion_status = 'manual_required' if self.completion_monitor.contract['mode'] == 'manual' else 'pending'
            self.verification_misses = 0
            self.action_steps = 0
            self.running_since = time.monotonic()
            self.mode = 'running'
            self.hold_reason = None
            image_ref = None
            if self.jpeg:
                image_ref = f'{self.episode}_{self.version}.jpg'
                (self.directory / image_ref).write_bytes(self.jpeg)
            memory_id = self.event('task_instruction', {'instruction': self.instruction, 'task_id': self.task_id, 'requested_instruction': requested_instruction, 'normalization': normalization, 'source': args.get('source', 'user_tool_call'), 'user_utterance': str(args.get('user_utterance', ''))[:1000], 'memory_ids': refs, 'restored_from': source_memory, 'semantic_check': semantic_check, 'confirmed_proposal_id': confirmed, 'keyframe': image_ref, 'fact_type': 'requested_action_not_observed_completion'})
            if self.completion_monitor.contract['mode'] == 'user_stop':
                self._hold('completed', 'user_requested_done')
                self.completion_status = 'user_confirmed'
                self.event('task_completed', {'instruction': self.instruction, 'evidence': 'user_requested_done'})
        elif name == 'robot_resume':
            self._hold('paused', 'resume_invalidates_old_results', preserve_deferred=True)
            self.mode = 'running'
            self.hold_reason = None
            if not self.cumulative_task_budget:
                self.running_since = time.monotonic()
                self.action_steps = 0
            if self.completion_monitor:
                self.completion_monitor.final_streak = 0
            self.completion_status = 'manual_required' if self.completion_monitor and self.completion_monitor.contract['mode'] == 'manual' else 'pending'
            memory_id = self.event('task_resumed', {'instruction': self.instruction})
        elif name == 'robot_finish_task':
            self._clear_deferred('manual_completion_not_verified')
            self._hold('completed', 'operator_confirmed_completion')
            self.completion_status = 'user_confirmed'
            memory_id = self.event('task_completed', {'instruction': self.instruction, 'evidence': 'operator_confirmation'})
        else:
            utterance = str(args.get('user_utterance', ''))
            retain_queue = name == 'robot_pause' and bool(re.search('\\bkeep\\b.{0,40}\\b(?:queued|waiting)\\b|保留.{0,10}(?:等待|排队)|保持.{0,10}(?:等待|排队)', utterance, re.I))
            self._hold('cancelled' if name == 'robot_cancel_task' else 'paused', name, preserve_deferred=retain_queue)
            if retain_queue and self.deferred_task:
                self.event('deferred_retained_during_pause', {'deferred_id': self.deferred_task['deferred_id'], 'predecessor_task_id': self.task_id})
            memory_id = self.event('task_cancelled' if name == 'robot_cancel_task' else 'task_paused', {'instruction': self.instruction})
        if name in ('robot_resume', 'robot_pause') and self.deferred_task and args.get('voice_input_id'):
            guards = self.deferred_task.get('speech_input_guards', {})
            for (lease, guard) in list(guards.items()):
                if guard.get('input_id') == args['voice_input_id']:
                    guards.pop(lease)
                    self.event('deferred_audio_guard_resolved', dict(deferred_id=self.deferred_task['deferred_id'], lease_id=lease, input_id=args['voice_input_id'], reason=name + '_committed'))
        result = {'status': 'accepted', 'executed': True, 'completed': self.mode == 'completed', 'request_id': request_id, 'memory_id': memory_id, **self.snapshot()}
        self.db.execute('INSERT INTO receipts VALUES (?,?,?)', (request_id, digest, json.dumps(result, ensure_ascii=False)))
        self.db.commit()
        return result
