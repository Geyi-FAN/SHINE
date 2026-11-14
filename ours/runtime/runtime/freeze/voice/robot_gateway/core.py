"""Thread-safe task authority and episode memory; no direct simulator access."""
import copy
import os
import hashlib
import json
import re
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from instructions import normalize_instruction
from completion import CompletionMonitor
from interaction import classify_utterance, allowed_voice_action
from task_records import build_task_record, task_view
from semantics import inspect_semantics, confirmation_answer, confirmation_filler
from task_contract import candidate_contract, deferred_request, deferred_update_request, deferred_validation_text
from temporal_memory import select_tasks
from dialogue_evidence import dialogue_evidence, validate_correction_instruction
from clarification import ClarificationMixin, unresolved_object_choice
from dialogue_transactions import DialogueTransactions, DialogueConnection

class TaskError(ValueError):
    pass

class RobotState(ClarificationMixin):
    MUTATIONS = {'robot_begin_clarification', 'robot_answer_clarification', 'robot_cancel_clarification', 'robot_start_task', 'robot_revise_task', 'robot_pause', 'robot_resume', 'robot_cancel_task', 'robot_restore_task', 'robot_finish_task', 'robot_propose_task', 'robot_resolve_proposal', 'robot_schedule_task', 'robot_replace_deferred', 'robot_cancel_deferred'}

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.directory / 'episodes.sqlite', check_same_thread=False, factory=DialogueConnection)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, episode TEXT, time REAL, kind TEXT, version INTEGER, payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, digest TEXT, result TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, episode TEXT, updated REAL, payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS utterances (id TEXT PRIMARY KEY, episode TEXT, text TEXT, event_id TEXT)')
        self.db.execute('CREATE INDEX IF NOT EXISTS events_by_episode ON events(episode)')
        self.dialogue_transactions = DialogueTransactions(self.db)
        self.task_intent_revision = 0
        self.episode = uuid.uuid4().hex
        self.version = 0
        self.mode = 'loading'
        self.instruction = ''
        self.task_id = None
        self.step = 0
        self.cumulative_task_budget = os.environ.get('VOICE_CUMULATIVE_TASK_BUDGET') == '1'
        self.action_steps = 0
        self.last_error = None
        self.failure_detail = None
        self.last_gripper = -1.0
        self.hold_pose = None
        self.obs = None
        self.jpeg = None
        self.wrist_jpeg = None
        self.queue = []
        self.running_since = None
        self.ready = False
        self.last_infer_ms = None
        self.stale_results_dropped = 0
        self.reset_count = 0
        self.reset_pending = None
        self.completion_monitor = None
        self.completion_status = 'no_task'
        self.normalization = None
        self.verification_misses = 0
        self.inference_requests = 0
        self.task_record = None
        self.observed_at = None
        self.hold_reason = None
        self.latest_evidence = {}
        self.request_context = {}
        self.last_interaction = None
        self.scene_inventory = None
        self.scene_memory_status = {'state': 'disabled'}
        self.execution_backend = 'legacy'
        self.execution_profile = 'symbolic'
        self.native_handoff_ready = True
        self.policy_metadata = {}
        self.agent_execution = None
        self.pending_proposal = None
        self.pending_clarification = None
        self.deferred_task = None
        self.event('episode_created', {'note': 'Fresh process, fresh episode. Prior physical tasks are never automatically resumed.'})

    def event(self, kind, payload):
        with self.lock:
            identifier = uuid.uuid4().hex
            payload = {'task_id': self.task_id, 'observation_time': self.observed_at, **self.request_context, **payload, 'simulation_step': self.step}
            self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)', (identifier, self.episode, time.time(), kind, self.version, json.dumps(payload, ensure_ascii=False)))
            self.dialogue_transactions.on_event(self, kind, payload)
            self.persist_task()
            self.db.commit()
            return identifier

    def current_task(self):
        if not self.task_record or not self.completion_monitor:
            return None
        return task_view(self.task_record, self.completion_monitor, self.mode, self.completion_status, self.version, self.hold_reason, self.latest_evidence)

    def persist_task(self):
        record = self.current_task()
        if record:
            self.db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?,?)', (self.task_id, self.episode, time.time(), json.dumps(record, ensure_ascii=False)))

    def task_history(self):
        with self.lock:
            self.persist_task()
            records = [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM tasks WHERE episode=? ORDER BY updated DESC LIMIT 100', (self.episode,))]
            rows = [(i, t, k, json.loads(p)) for (i, t, k, p) in self.db.execute('SELECT id,time,kind,payload FROM events WHERE episode=? ORDER BY rowid', (self.episode,))]
            for record in records:
                related = [(i, t, k, p) for (i, t, k, p) in rows if p.get('task_id') == record['task_id']]
                record['ever_completed'] = any((k == 'task_completed' for (_, _, k, _) in related))
                record['ever_verified_completed'] = any((k == 'task_completed' and p.get('evidence') in ('libero_predicates_and_stable_release', 'simulator_v2.5_hybrid_monitor') for (_, _, k, p) in related))
                record['ever_cancelled'] = any((k == 'task_cancelled' for (_, _, k, _) in related))
                record['instruction_memory_id'] = next((i for (i, _, k, _) in related if k == 'task_instruction'), None)
                record['last_event_at'] = related[-1][1] if related else None
                record['is_current'] = record['task_id'] == self.task_id
                record['evidence_scope'] = 'historical_events_not_current_world_state'
            return records

    def timeline(self, after=0, episode=None, limit=100):
        with self.lock:
            reset = episode is not None and episode != self.episode
            if reset:
                after = 0
            limit = max(1, min(int(limit), 200))
            rows = self.db.execute('SELECT rowid,id,time,kind,version,payload FROM events WHERE episode=? AND rowid>? ORDER BY rowid LIMIT ?', (self.episode, max(0, int(after)), limit + 1)).fetchall()
            events = [{'sequence': r[0], 'event_id': r[1], 'time': r[2], 'kind': r[3], 'version': r[4], **json.loads(r[5])} for r in rows[:limit]]
            return {'episode_id': self.episode, 'events': events, 'reset': reset, 'next_cursor': events[-1]['sequence'] if events else 0 if reset else after, 'has_more': len(rows) > limit}

    def record_speech_activity(self, body):
        """Hold only an existing handoff while its authenticated audio is unresolved."""
        with self.lock:
            if body.get('episode_id') != self.episode:
                raise TaskError('stale_episode')
            slot = self.deferred_task
            if not slot or body.get('deferred_id') != slot['deferred_id']:
                raise TaskError('unknown_or_stale_deferred_task')
            lease = body.get('lease_id')
            if not isinstance(lease, str) or not 0 < len(lease) <= 256:
                raise TaskError('invalid_speech_lease')
            phase = body.get('phase')
            guards = slot.setdefault('speech_input_guards', {})
            if phase == 'started':
                if lease not in guards:
                    if len(guards) >= 8:
                        raise TaskError('unresolved_speech_limit')
                    guards[lease] = dict(lease_id=lease, started_at=time.time(), expires_at=time.time() + 60, phase='awaiting_transcript')
                    self.event('deferred_audio_guard_started', dict(deferred_id=slot['deferred_id'], lease_id=lease))
                return dict(status='guarded', executed=False, lease_id=lease, episode_id=self.episode, deferred_id=slot['deferred_id'])
            guard = guards.get(lease)
            if not guard:
                return dict(status='already_resolved', executed=False)
            if phase == 'rejected' and body.get('reason') == 'semantic_vad_rejected':
                guards.pop(lease)
                self.event('deferred_audio_guard_resolved', dict(deferred_id=slot['deferred_id'], lease_id=lease, reason='semantic_vad_rejected'))
                return dict(status='resolved', executed=False)
            if phase != 'transcribed':
                raise TaskError('invalid_speech_phase')
            identifier = body.get('input_id')
            recorded = self.db.execute('SELECT episode,text FROM utterances WHERE id=?', (identifier,)).fetchone()
            if not recorded or recorded[0] != self.episode:
                raise TaskError('speech_transcript_not_recorded')
            text = recorded[1]
            kind = classify_utterance(text)
            safe = bool(slot.get('dispatch_blocked_by_input') == identifier or kind in ('question', 'backchannel', 'non_command') or (kind == 'pause' and self.mode == 'paused'))
            if safe:
                guards.pop(lease)
                self.event('deferred_audio_guard_resolved', dict(deferred_id=slot['deferred_id'], lease_id=lease, input_id=identifier, classification=kind))
                return dict(status='resolved', executed=False)
            guard.update(phase='awaiting_decision', input_id=identifier)
            return dict(status='awaiting_decision', executed=False)

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

    def memory(self, query='', limit=12):
        with self.lock:
            rows = self.db.execute("SELECT id,time,kind,version,payload FROM events WHERE episode=? AND kind NOT IN ('speech_classified','stale_actions_discarded','control_hold','request_rejected') ORDER BY rowid DESC LIMIT 100", (self.episode,)).fetchall()
            entries = [{'memory_id': r[0], 'time': r[1], 'kind': r[2], 'version': r[3], **json.loads(r[4])} for r in rows]
            if query:
                matched = [e for e in entries if query.casefold() in json.dumps(e, ensure_ascii=False).casefold()]
                entries = matched or entries
            histories = {t['task_id']: t for t in self.task_history()}
            for entry in entries:
                task = histories.get(entry.get('task_id'), {})
                entry['task_status'] = {k: task.get(k) for k in ('state', 'completion', 'ever_completed', 'ever_verified_completed', 'ever_cancelled', 'last_event_at', 'is_current')}
            return entries[:max(1, min(int(limit), 20))]

    def snapshot(self):
        with self.lock:
            self._expire_clarification()
            self._expire_proposal()
            self._expire_deferred()
            proprio = {}
            if self.obs is not None:
                for key in ('robot0_eef_pos', 'robot0_gripper_qpos'):
                    proprio[key] = self.obs[key].tolist()
            return {'episode_id': self.episode, 'task_version': self.version, 'task_intent_revision': self.task_intent_revision, 'dialogue_transactions': self.dialogue_transactions.snapshot(self.episode), 'task_id': self.task_id, 'state': self.mode, 'ready': self.ready, 'execution_readiness': dict(getattr(self, 'execution_readiness', {})), 'failure_detail': self.failure_detail, 'instruction': self.instruction, 'simulation_steps': self.step, 'policy_action_steps': self.action_steps, 'queued_actions': len(self.queue), 'reset_count': self.reset_count, 'scene_memory': dict(self.scene_memory_status), 'execution_backend': self.execution_backend, 'execution_profile': self.execution_profile, 'policy_metadata': copy.deepcopy(self.policy_metadata), 'agent_execution': copy.deepcopy(self.agent_execution), 'last_error': self.last_error, 'reset_pending': self.reset_pending is not None, 'last_infer_ms': self.last_infer_ms, 'policy_inference_requests': self.inference_requests, 'stale_results_dropped': self.stale_results_dropped, 'gripper_command': self.last_gripper, 'proprioception': proprio, 'completion': self.completion_status, 'completion_mode': self.completion_monitor.contract['mode'] if self.completion_monitor else 'none', 'completion_stage': self.completion_monitor.stage + 1 if self.completion_monitor and self.completion_monitor.contract['stages'] else 0, 'completion_stages': len(self.completion_monitor.contract['stages']) if self.completion_monitor else 0, 'instruction_normalization': copy.deepcopy(self.normalization), 'task': self.current_task(), 'hold_reason': self.hold_reason, 'observation_time': self.observed_at, 'last_interaction': copy.deepcopy(self.last_interaction), 'scene_inventory': copy.deepcopy(self.scene_inventory), 'pending_proposal': copy.deepcopy(self.pending_proposal), 'pending_clarification': copy.deepcopy(self.pending_clarification), 'deferred_task': copy.deepcopy(self.deferred_task), 'checkpoint_step': 11050 if self.execution_backend == 'legacy' else 30000, 'control_hz_target': 20, 'note': 'Legacy P1 executor' if self.execution_backend == 'legacy' else 'Agent planning + simulator v2.5 phase judgment + YOLO/M1 coordinates + configured action policy; not fully non-Oracle.'}

    def _hold(self, mode, reason, preserve_deferred=False):
        if mode in ('superseded', 'resetting', 'running', 'completed'):
            self.failure_detail = None
        self._clear_clarification('task_version_changed')
        self._clear_proposal('task_version_changed')
        if mode in ('superseded', 'paused', 'cancelled', 'resetting', 'needs_review', 'error', 'budget_exhausted'):
            if not (mode == 'paused' and preserve_deferred):
                self._clear_deferred(reason)
        self.version += 1
        self.queue.clear()
        self.mode = mode
        self.hold_reason = reason if mode not in ('running', 'idle') else None
        if self.obs is not None:
            self.hold_pose = (self.obs['robot0_eef_pos'].copy(), self.obs['robot0_eef_quat'].copy())
        self.event('control_hold', {'reason': reason, 'gripper_command': self.last_gripper})

    def interrupt(self, reason='user_speech'):
        with self.lock:
            self._clear_proposal(reason)
            self._clear_deferred(reason)
            if self.mode in ('running', 'verifying'):
                self._hold('paused', reason)
            return self.snapshot()

    def command(self, name, args, request_id):
        with self.lock:
            if not isinstance(args, dict):
                raise TaskError('invalid_arguments')
            if any((str(k).startswith('_') for k in args)):
                raise TaskError('private_argument_not_allowed')
            if name in ('robot_replace_deferred', 'robot_cancel_deferred') and self.deferred_task and (args.get('episode_id') == self.episode) and (args.get('expected_task_version') == self.version) and (args.get('deferred_id') == self.deferred_task['deferred_id']) and (args.get('source') == 'qwen_realtime_current_user') and deferred_update_request(args.get('user_utterance', '')):
                recorded = self.db.execute('SELECT episode,text FROM utterances WHERE id=?', (args.get('voice_input_id'),)).fetchone()
                if recorded == (self.episode, args.get('user_utterance')) and self.deferred_task.get('dispatch_blocked_by_input') in (None, args.get('voice_input_id')):
                    self._block_deferred_update(args['voice_input_id'], args['user_utterance'])
            atomic = name in self.MUTATIONS and (not self.db.unit_open)
            backup = None
            if atomic:
                excluded = {'db', 'lock', 'dialogue_transactions', 'directory', 'obs', 'jpeg', 'wrist_jpeg', 'scene_inventory', 'request_context'}
                backup = {k: copy.deepcopy(v) for (k, v) in vars(self).items() if k not in excluded}
                self.db.begin_unit()
            previous = self.request_context
            self.request_context = {'request_id': str(request_id)[:256], 'operation': name, 'voice_input_id': args.get('voice_input_id'), 'source': args.get('source', 'operator_tool'), 'user_utterance': str(args.get('user_utterance', ''))[:1000]}
            try:
                result = self._command(name, args, request_id)
                if atomic:
                    self.db.finish_unit(True)
                return result
            except Exception as exc:
                if atomic:
                    self.db.finish_unit(False)
                    for (key, value) in backup.items():
                        setattr(self, key, value)
                self.event('request_rejected', {'reason': str(exc)[:300], 'user_utterance': str(args.get('user_utterance', ''))[:1000]})
                raise
            finally:
                self.request_context = previous

    def _current_instruction_reference(self, tasks):
        """Expose an actual current instruction ID, never resolve a new goal."""
        from grounding import slots, mentions
        current = [t for t in tasks if t.get('is_current') and t.get('instruction_memory_id')]
        if len(current) != 1:
            return None
        record = current[0]
        actors = {e for (role, noun) in slots(record.get('complete_instruction', '')) if role == 'source' for (_, e) in mentions(noun) if e}
        return dict(episode_id=self.episode, task_id=self.task_id, task_version=self.version, instruction_memory_id=record['instruction_memory_id'], complete_instruction=record.get('complete_instruction', ''), source_entities=sorted(actors), unique_source_object=len(actors) == 1, scope='actual_current_instruction_memory; not physical completion or new permission')

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

    def _clear_proposal(self, reason):
        if self.pending_proposal:
            old = self.pending_proposal
            self.pending_proposal = None
            self.event('proposal_invalidated', {'proposal_id': old['proposal_id'], 'reason': reason})

    def _expire_proposal(self):
        if self.pending_proposal and (time.time() >= self.pending_proposal['expires_at'] or self.pending_proposal['task_version'] != self.version):
            self._clear_proposal('expired_or_stale_version')

    def _save_receipt(self, request_id, digest, result):
        self.db.execute('INSERT INTO receipts VALUES (?,?,?)', (request_id, digest, json.dumps(result, ensure_ascii=False)))
        self.db.commit()
        return result

    def _create_proposal(self, name, args, instruction, check, request_id, digest):
        if self.pending_clarification and (not args.get('_clarification_evidence')):
            raise TaskError('resolve_existing_clarification_first')
        self._clear_proposal('replaced_by_new_proposal')
        operation = ('robot_revise_task' if self.task_id else 'robot_start_task') if name == 'robot_propose_task' else name
        candidate = build_task_record('proposal', self.episode, operation, instruction, instruction, args, CompletionMonitor(instruction), self.observed_at)
        summary = '，然后'.join((stage['label'] for stage in candidate['stages'])) or instruction
        self.pending_proposal = {'proposal_id': uuid.uuid4().hex, 'episode_id': self.episode, 'task_version': self.version, 'created_at': time.time(), 'expires_at': time.time() + 60, 'voice_input_id': args.get('voice_input_id'), 'operation': operation, 'instruction': instruction, 'summary': summary, 'question': '请确认是否执行：' + summary + '？请说“确认执行”或“不执行”。', 'candidate_contract': candidate_contract(self.episode, self.version, operation, instruction, args, check, self.observed_at), 'semantic_check': check, 'user_utterance': args.get('user_utterance', ''), 'memory_ids': args.get('memory_ids', []), 'memory_id': args.get('memory_id'), 'source': args.get('source', 'operator_tool'), 'clarification_evidence': copy.deepcopy(args.get('_clarification_evidence'))}
        self.event('proposal_created', {'proposal_id': self.pending_proposal['proposal_id'], 'instruction': instruction, 'question': self.pending_proposal['question'], 'expires_at': self.pending_proposal['expires_at']})
        return self._save_receipt(request_id, digest, {'status': 'needs_confirmation', 'executed': False, 'request_id': request_id, **self.snapshot(), 'note': 'No new motion was started. Read the exact proposal question and await a NEW user answer. A running previous task continues unless explicitly paused.'})

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

    def _same_completed_deferred_update(self, name, args):
        slot = self.deferred_task
        if name not in ('robot_replace_deferred', 'robot_cancel_deferred') or not slot or self.mode != 'completed' or (self.completion_status != 'verified') or (args.get('source') != 'qwen_realtime_current_user') or (type(args.get('expected_task_version')) is not int) or (slot.get('predecessor_task_id') != self.task_id) or (args.get('deferred_id') != slot['deferred_id']) or (not slot.get('dispatch_blocked_by_input')) or (slot['dispatch_blocked_by_input'] != args.get('voice_input_id')) or (slot.get('update_utterance') != args.get('user_utterance')):
            return False
        row = self.dialogue_transactions.get(slot['deferred_id'])
        return bool(row and row['status'] == 'queued' and (row['episode_id'] == self.episode) and (row['bound_task_id'] == self.task_id) and (row['task_intent_revision'] == self.task_intent_revision) and (row['observed_execution_version'] == args['expected_task_version']) and (args.get('transaction_id') == row['transaction_id']) and (type(args.get('expected_transaction_revision')) is int) and (args['expected_transaction_revision'] == row['revision']))

    def _block_deferred_update(self, identifier, text):
        if not self.deferred_task or self.deferred_task.get('dispatch_blocked_by_input') == identifier:
            return
        self.deferred_task.update(dispatch_blocked_by_input=identifier, update_utterance=text, update_requested_at=time.time(), state='update_pending')
        self.event('deferred_update_requested', dict(deferred_id=self.deferred_task['deferred_id'], input_id=identifier, reason='awaiting_explicit_cancel_or_replacement'))

    def _clear_deferred(self, reason):
        if self.deferred_task:
            (old, self.deferred_task) = (self.deferred_task, None)
            self.event('deferred_invalidated', {'deferred_id': old['deferred_id'], 'reason': reason})

    def _expire_deferred(self):
        if self.deferred_task and time.time() >= self.deferred_task['expires_at']:
            self._clear_deferred('expired')

    def _deferred_command(self, name, args, request_id, digest):
        self._expire_deferred()
        if name in ('robot_replace_deferred', 'robot_cancel_deferred'):
            if not self.deferred_task or args.get('deferred_id') != self.deferred_task['deferred_id']:
                raise TaskError('unknown_or_stale_deferred_task')
        elif self.deferred_task:
            raise TaskError('deferred_slot_occupied: 使用替换工具并绑定现有候选 ID。')
        if name in ('robot_replace_deferred', 'robot_cancel_deferred'):
            blocked_input = self.deferred_task.get('dispatch_blocked_by_input')
            if args.get('source') == 'qwen_realtime_current_user':
                if blocked_input and args.get('voice_input_id') != blocked_input:
                    raise TaskError('superseded_deferred_update_input')
                raw_update = args.get('user_utterance', '')
                explicit_update = deferred_update_request(raw_update) or (name == 'robot_replace_deferred' and deferred_request(raw_update, replacing=self.deferred_task['instruction']))
                if not explicit_update:
                    raise TaskError('deferred_update_requires_explicit_user_request')
        if name == 'robot_cancel_deferred':
            self._clear_deferred('user_cancelled')
            return self._save_receipt(request_id, digest, {'status': 'deferred_cancelled', 'executed': False, **self.snapshot()})
        completed_update = bool(name == 'robot_replace_deferred' and self.deferred_task and self.deferred_task.get('dispatch_blocked_by_input') and (self.mode == 'completed') and (self.completion_status == 'verified'))
        # The actual predecessor may finish between listening and scheduling.
        # Keep the explicit conditional request as a versioned queue operation;
        # normal semantic, consent, cancellation and handoff guards still apply.
        completed_schedule = bool(name == 'robot_schedule_task' and self.mode == 'completed' and self.completion_status == 'verified'
                                  and (self.agent_execution or {}).get('completion_current_verified') is True)
        if self.mode not in ('running', 'verifying') and not(completed_update or completed_schedule) or not self.task_id:
            raise TaskError('deferred_requires_active_predecessor')
        instruction = args.get('instruction', '')
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 900 or (len(instruction.split()) > 100):
            raise TaskError('invalid_deferred_instruction')
        raw = args.get('user_utterance', '')
        candidate_text = deferred_request(raw, replacing=(self.deferred_task or {}).get('instruction') if name == 'robot_replace_deferred' else None)
        if args.get('source') == 'qwen_realtime_current_user' and (not candidate_text):
            raise TaskError('deferred_requires_explicit_completion_request')
        (instruction, _) = normalize_instruction(instruction.strip(), self.instruction)
        try:
            if candidate_text:
                candidate_text = deferred_validation_text(raw, candidate_text, self.instruction, instruction)
            check = inspect_semantics(candidate_text or instruction, instruction, self.scene_inventory, previous=self.instruction)
        except ValueError as exc:
            raise TaskError(str(exc)) from exc
        if check['decision'] != 'checked':
            raise TaskError('deferred_requires_clarification: 请先明确延迟任务的全部对象和位置。')
        contract = candidate_contract(self.episode, self.version, name, instruction, args, check, self.observed_at)
        self.event('task_candidate_checked', {'candidate': contract})
        self._clear_deferred('replaced_by_user')
        self.deferred_task = {'deferred_id': uuid.uuid4().hex, 'episode_id': self.episode, 'predecessor_task_id': self.task_id, 'instruction': instruction, 'candidate_contract': contract, 'candidate_utterance': candidate_text or instruction, 'original_utterance': raw, 'authorized_request_id': request_id, 'voice_input_id': args.get('voice_input_id'), 'created_at': time.time(), 'expires_at': time.time() + 900, 'state': 'waiting_for_verified_completion'}
        self.event('deferred_scheduled', copy.deepcopy(self.deferred_task))
        if completed_update or completed_schedule:
            predecessor = self.task_id
            self._run_deferred()
            return self._save_receipt(request_id, digest, dict(status='accepted' if self.task_id != predecessor else 'scheduled', executed=self.task_id != predecessor, **self.snapshot()))
        return self._save_receipt(request_id, digest, {'status': 'scheduled', 'executed': False, **self.snapshot()})

    def _run_deferred(self):
        self._expire_deferred()
        slot = self.deferred_task
        if not slot:
            return
        guards = slot.get('speech_input_guards', {})
        if guards:
            for guard in guards.values():
                if time.time() >= guard['expires_at'] and guard['phase'] != 'needs_input':
                    guard['phase'] = 'needs_input'
                    self.event('deferred_audio_guard_expired', dict(deferred_id=slot['deferred_id'], lease_id=guard['lease_id'], action='keep_handoff_blocked'))
            return
        if slot.get('dispatch_blocked_by_input'):
            return
        if slot['episode_id'] != self.episode or slot['predecessor_task_id'] != self.task_id or (not self.ready) or (self.mode != 'completed') or (self.completion_status != 'verified'):
            self._clear_deferred('predecessor_not_verified')
            return
        if self.execution_backend in ('agent', 'qwen', 'codex') and self.agent_execution.get('completion_current_verified') is not True:
            return
        if self.execution_profile == 'native_libero_goal' and self.native_handoff_ready is not True:
            if slot.get('state') != 'waiting_for_native_release':
                slot['state'] = 'waiting_for_native_release'
                self.event('deferred_handoff_waiting_for_release', dict(deferred_id=slot['deferred_id']))
            return
        self.deferred_task = None
        try:
            check = inspect_semantics(slot['candidate_utterance'], slot['instruction'], self.scene_inventory, previous=self.instruction)
            if check['decision'] != 'checked':
                raise TaskError('deferred_recheck_uncertain')
            self.event('deferred_rechecked', {'deferred_id': slot['deferred_id'], 'semantic_check': check})
            result = self.command('robot_revise_task', {'episode_id': self.episode, 'expected_task_version': self.version, 'instruction': slot['instruction'], 'user_utterance': slot['candidate_utterance'], 'source': 'qwen_realtime_current_user', 'voice_input_id': slot['voice_input_id']}, 'deferred:' + slot['deferred_id'])
            if result.get('status') != 'accepted':
                raise TaskError('deferred_dispatch_not_accepted')
            self.event('deferred_started', {'deferred_id': slot['deferred_id'], 'authorized_request_id': slot['authorized_request_id'], 'new_task_id': result['task_id']})
        except (TaskError, ValueError) as exc:
            self.event('deferred_blocked', {'deferred_id': slot['deferred_id'], 'reason': str(exc)})

    def observe_completion(self, evidence):
        """Only the simulator worker calls this; no task-action generation here."""
        with self.lock:
            if self.mode not in ('running', 'verifying') or self.completion_monitor is None:
                return
            previous_stage = self.completion_monitor.stage
            self.latest_evidence = dict(evidence)
            verdict = self.completion_monitor.update(evidence)
            if self.completion_monitor.stage != previous_stage:
                self.event('task_stage_verified', {'stage_index': previous_stage, 'stage_label': self.task_record['stages'][previous_stage]['label'] if self.task_record else '', 'evidence': 'libero_supervisor'})
            if verdict == 'complete':
                self._hold('completed', 'stable_goal_verified')
                self.completion_status = 'verified'
                self.event('task_completed', {'instruction': self.instruction, 'evidence': 'libero_predicates_and_stable_release', 'stable_frames': self.completion_monitor.stable_frames})
                self._run_deferred()
            elif verdict == 'order_violation':
                self._hold('needs_review', 'ordered_constraint_violated')
                self.completion_status = 'order_violation'
                self.event('task_needs_review', {'instruction': self.instruction, 'reason': 'A later goal was reached before required cleanup; stopped without claiming completion.'})
            elif verdict == 'candidate':
                self.verification_misses = 0
                self.completion_status = 'verifying'
                if self.mode == 'running':
                    self._hold('verifying', 'checking_stable_completion')
            elif verdict == 'progress' and self.mode == 'verifying':
                self.verification_misses += 1
                if self.verification_misses >= 3:
                    self.completion_status = 'pending'
                    self._hold('running', 'completion_not_stable_continue_current_task')

    def request_reset(self, args, request_id):
        """Explicit operator-only reset, never exposed as a cloud model tool."""
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            raise TaskError('request_id required')
        with self.lock:
            digest = hashlib.sha256(json.dumps(['operator_reset', args], sort_keys=True).encode()).hexdigest()
            row = self.db.execute('SELECT digest,result FROM receipts WHERE id=?', (request_id,)).fetchone()
            if row:
                if row[0] != digest:
                    raise TaskError('request_id reused with different arguments')
                return json.loads(row[1])
            if args.get('episode_id') != self.episode:
                raise TaskError('stale_episode')
            if type(args.get('expected_task_version')) is not int or args['expected_task_version'] != self.version:
                raise TaskError('stale_task_version')
            if self.reset_pending:
                raise TaskError('reset_already_pending')
            if not self.ready:
                raise TaskError('environment_not_ready')
            self._hold('resetting', 'operator_reset')
            self.ready = False
            self.reset_pending = request_id
            result = {'status': 'accepted', 'completed': False, 'request_id': request_id, **self.snapshot()}
            self.db.execute('INSERT INTO receipts VALUES (?,?,?)', (request_id, digest, json.dumps(result)))
            self.db.commit()
            return result

    def finish_reset(self, obs):
        with self.lock:
            if not self.reset_pending:
                raise TaskError('no_pending_reset')
            previous = self.episode
            self.mode = 'ended'
            self.event('episode_ended', {'reason': 'operator_reset'})
            self.deferred_task = None
            self.episode = uuid.uuid4().hex
            self.version += 1
            self.task_id = None
            self.instruction = ''
            self.scene_memory_status = {'state': 'awaiting_episode_initialization'}
            self.execution_profile = 'symbolic'
            self.native_handoff_ready = True
            self.queue.clear()
            self.step = 0
            self.action_steps = 0
            self.running_since = None
            self.last_error = None
            self.last_infer_ms = None
            self.last_gripper = -1.0
            self.completion_monitor = None
            self.completion_status = 'no_task'
            self.normalization = None
            self.task_record = None
            self.latest_evidence = {}
            self.hold_reason = None
            self.last_interaction = None
            self.observed_at = time.time()
            self.jpeg = None
            self.wrist_jpeg = None
            self.obs = obs
            self.hold_pose = (obs['robot0_eef_pos'].copy(), obs['robot0_eef_quat'].copy())
            self.reset_count += 1
            self.reset_pending = None
            self.ready = True
            self.mode = 'idle'
            self.event('episode_created', {'reason': 'operator_reset', 'previous_episode': previous, 'reset_count': self.reset_count})

    def accept_actions(self, version, actions, elapsed_ms, observed_at):
        with self.lock:
            if version != self.version or self.mode != 'running':
                self.stale_results_dropped += 1
                self.event('stale_actions_discarded', {'inference_version': version})
                return False
            if time.monotonic() - observed_at > 3.0:
                self.event('old_observation_discarded', {'age_seconds': time.monotonic() - observed_at})
                return False
            self.last_infer_ms = elapsed_ms
            execute_steps = 4 if self.policy_metadata.get('executor') == 'smolvla_e3_v4' else 3
            self.queue = [(version, a.copy()) for a in actions[:execute_steps]]
            return True

    def next_action(self):
        with self.lock:
            if self.mode != 'running':
                return None
            while self.queue:
                (version, action) = self.queue.pop(0)
                if version == self.version:
                    self.action_steps += 1
                    self.last_gripper = float(action[-1])
                    return action
            return None
