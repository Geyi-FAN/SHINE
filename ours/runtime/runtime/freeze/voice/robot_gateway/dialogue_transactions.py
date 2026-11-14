"""Persistent lifecycle and concurrency guard shared by all dialogue slots.

Legacy slots remain payload adapters. This ledger owns revision/status checks;
it never generates instructions or restores physical work after a restart.
"""
import copy
import json
import sqlite3
import time


ACTIVE = {'awaiting_input', 'awaiting_confirmation', 'queued', 'revalidating', 'approved'}
SLOTS = {
    'clarification': ('pending_clarification', 'clarification_id', 'awaiting_input'),
    'confirmation': ('pending_proposal', 'proposal_id', 'awaiting_confirmation'),
    'deferred': ('deferred_task', 'deferred_id', 'queued'),
}


class DialogueConnection(sqlite3.Connection):
    """Keep nested event/receipt writes in one public command's SQLite commit."""
    unit_open = False

    def begin_unit(self):
        # Observation/task persistence may have staged writes outside a command.
        # They precede this operation and must not be rolled back with it.
        if self.in_transaction:
            super().commit()
        self.execute('BEGIN IMMEDIATE')
        self.unit_open = True

    def commit(self):
        if not self.unit_open:
            super().commit()

    def finish_unit(self, success):
        self.unit_open = False
        if success:
            super().commit()
        else:
            super().rollback()


class DialogueTransactions:
    def __init__(self, db):
        self.db = db
        db.execute('CREATE TABLE IF NOT EXISTS dialogue_transactions '
                   '(id TEXT PRIMARY KEY, episode TEXT, status TEXT, payload TEXT)')
        # No outstanding intent is silently reactivated in a new process.
        for (raw,) in db.execute('SELECT payload FROM dialogue_transactions').fetchall():
            row = json.loads(raw)
            if row['status'] in ACTIVE:
                self.finish(row['transaction_id'], 'cancelled', reason='process_restarted')
        db.commit()

    def get(self, identifier):
        row = self.db.execute('SELECT payload FROM dialogue_transactions WHERE id=?', (identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, row):
        row['updated_at'] = time.time()
        self.db.execute('INSERT OR REPLACE INTO dialogue_transactions VALUES (?,?,?,?)',
                        (row['transaction_id'], row['episode_id'], row['status'], json.dumps(row, ensure_ascii=False)))

    def finish(self, identifier, status, **fields):
        row = self.get(identifier)
        if not row:
            return
        row.update(fields)
        row['revision'] += 1
        row['status'] = status
        self.save(row)

    def register(self, state, kind):
        attr, id_key, status = SLOTS[kind]
        payload = getattr(state, attr)
        identifier = payload[id_key]
        row = self.get(identifier)
        sources = payload.get('source_utterances') or [dict(
            input_id=payload.get('voice_input_id'),
            text=payload.get('original_utterance', payload.get('user_utterance', '')))]
        row = dict(row or {}, transaction_id=identifier, kind=kind,
                   episode_id=state.episode, revision=(row['revision'] + 1 if row else 1),
                   status=status, bound_task_id=state.task_id,
                   predecessor_task_id=payload.get('predecessor_task_id'),
                   task_intent_revision=state.task_intent_revision,
                   observed_execution_version=state.version,
                   source_utterances=copy.deepcopy(sources),
                   source_input_ids=[s['input_id'] for s in sources if s.get('input_id')],
                   resolved_instruction=payload.get('instruction'),
                   question=payload.get('question'), created_at=payload['created_at'],
                   dispatch_blocked_by_input=payload.get('dispatch_blocked_by_input'),
                   expires_at=payload['expires_at'], consumed_by_task_id=None)
        self.save(row)
        payload.update(transaction_id=identifier, transaction_revision=row['revision'])

    def check(self, state, name, args):
        mapping = {
            'robot_answer_clarification': 'clarification', 'robot_cancel_clarification': 'clarification',
            'robot_resolve_proposal': 'confirmation', 'robot_replace_deferred': 'deferred',
            'robot_cancel_deferred': 'deferred',
        }
        kind = mapping.get(name)
        if not kind:
            return
        attr, key, status = SLOTS[kind]
        payload = getattr(state, attr)
        identifier = args.get(key)
        row = self.get(identifier)
        if not payload or payload[key] != identifier or not row or row['status'] != status:
            raise ValueError({'confirmation': 'unknown_or_expired_proposal', 'clarification': 'unknown_or_expired_clarification', 'deferred': 'unknown_or_stale_deferred_task'}[kind])
        if row['episode_id'] != state.episode or row['bound_task_id'] != state.task_id:
            raise ValueError('stale_dialogue_task_binding')
        if time.time() >= row['expires_at']:
            raise ValueError('expired_dialogue_transaction')
        expected = args.get('expected_transaction_revision')
        supplied_id = args.get('transaction_id')
        if supplied_id is not None and supplied_id != identifier:
            raise ValueError('dialogue_transaction_id_mismatch')
        if supplied_id is not None and expected is None:
            raise ValueError('expected_transaction_revision_required')
        if expected is not None and (type(expected) is not int or expected != row['revision']):
            raise ValueError('stale_transaction_revision: read fresh status; never guess')

    def on_event(self, state, kind, payload):
        creates = {'clarification_created': 'clarification', 'clarification_answer_bound': 'clarification',
                   'proposal_created': 'confirmation', 'deferred_scheduled': 'deferred',
                   'deferred_update_requested': 'deferred'}
        if kind in creates:
            self.register(state, creates[kind])
        for prefix, key in [('clarification', 'clarification_id'), ('proposal', 'proposal_id'), ('deferred', 'deferred_id')]:
            if kind == prefix + '_invalidated':
                reason = payload.get('reason', '')
                self.finish(payload[key], 'expired' if 'expired' in reason else 'cancelled', reason=reason)
        if kind == 'clarification_resolved':
            self.finish(payload['clarification_id'], 'resolved',
                        source_utterances=payload['source_utterances'],
                        source_input_ids=[s['input_id'] for s in payload['source_utterances']],
                        resolved_instruction=payload['resolved_instruction'],
                        consumed_by_task_id=payload.get('consumed_by_task_id'),
                        successor_transaction_id=payload.get('successor_transaction_id'))
        if kind == 'proposal_resolved':
            self.finish(payload['proposal_id'], 'approved' if payload['decision'] == 'confirm' else 'rejected')
        if kind == 'task_instruction' and payload.get('confirmed_proposal_id'):
            self.finish(payload['confirmed_proposal_id'], 'consumed', consumed_by_task_id=state.task_id)
        if kind == 'deferred_rechecked':
            self.finish(payload['deferred_id'], 'revalidating')
        if kind == 'deferred_started':
            self.finish(payload['deferred_id'], 'consumed', consumed_by_task_id=payload['new_task_id'])
        if kind == 'deferred_blocked':
            self.finish(payload['deferred_id'], 'blocked', reason=payload['reason'])

    def snapshot(self, episode):
        rows = [json.loads(r[0]) for r in self.db.execute(
            'SELECT payload FROM dialogue_transactions WHERE episode=? ORDER BY rowid DESC LIMIT 30', (episode,))]
        return {'active': [r for r in rows if r['status'] in ACTIVE],
                'recent_terminal': [r for r in rows if r['status'] not in ACTIVE][:10]}
