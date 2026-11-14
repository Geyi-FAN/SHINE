"""Read-only wording preparation with exact queue-to-successor ownership.

No position, state, completion or next subgoal is predicted before handoff.
The prepared result never authorizes execution or changes a pending task.
"""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import re
import threading
from pathlib import Path
from types import SimpleNamespace


def slot_key(state, slot: dict) -> tuple:
    transaction = state.dialogue_transactions.get(slot["deferred_id"])
    revision = transaction["revision"] if transaction else None
    canonical = json.dumps(
        {
            key: slot.get(key)
            for key in (
                "episode_id",
                "predecessor_task_id",
                "deferred_id",
                "instruction",
                "candidate_utterance",
                "authorized_request_id",
                "voice_input_id",
            )
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        state.episode,
        slot["deferred_id"],
        revision,
        hashlib.sha256(canonical.encode()).hexdigest(),
    )


def install(bridge, state) -> None:
    import instructions
    import task_language
    import text_transport
    from t3repair.wording import reused_task

    spec = importlib.util.spec_from_file_location(
        "_t7_readonly_language_template", Path(task_language.__file__)
    )
    if spec is None or spec.loader is None:
        raise ImportError("Wording template loader unavailable")
    direct = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(direct)
    # Deliberately bypass the kernel-owned network wrapper for this text-only
    # background call. This has no captured retired bridge/kernel closure.
    setattr(direct, "request_json", text_transport.request_json)
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="t7-pending-wording"
    )
    lock = threading.RLock()
    entries = {}
    bound = {}
    consuming: list[tuple | None] = [None]

    def observe() -> None:
        with state.lock:
            slot = copy.deepcopy(state.deferred_task)
            previous = state.instruction
            key = slot_key(state, slot) if slot else None
        with lock:
            for old_key, entry in list(entries.items()):
                if (
                    old_key != key
                    and old_key != consuming[0]
                    and old_key not in {b[0] for b in bound.values()}
                ):
                    entry["future"].cancel()
                    del entries[old_key]
                    bridge.log(
                        "pending_preparation_invalidated", deferred_id=old_key[1]
                    )
            if key is None or key in entries:
                return
            raw = instructions.normalize_instruction(slot["instruction"], previous)[0]
            # Existing foreground semantics already preserve verified English
            # verbatim. Do not add an expensive model call to optimize zero work.
            literal = re.fullmatch(r"[\x20-\x7e\n]+", raw) is not None

            def work():
                if literal:
                    return reused_task(raw)
                cfg, secret = text_transport.connection("wording")
                agent = SimpleNamespace(
                    model=cfg["model"], url=cfg["chat_url"], key=secret
                )
                return direct.normalize(agent, raw, None)

            entries[key] = dict(
                raw=raw, future=executor.submit(work), literal_candidate=literal
            )
            bridge.log(
                "pending_preparation_started",
                deferred_id=key[1],
                observed_context_used=False,
                positions_prepared=False,
                planning_started=False,
                possible_verbatim=literal,
            )

    previous_command = state.command

    def command(*args, **kwargs):
        result = previous_command(*args, **kwargs)
        observe()
        return result

    state.command = command
    previous_handoff = state._run_deferred

    def handoff(*args, **kwargs):
        with state.lock:
            slot = copy.deepcopy(state.deferred_task)
            key = slot_key(state, slot) if slot else None
            previous_task = state.task_id
            consuming[0] = key
            try:
                result = previous_handoff(*args, **kwargs)
            finally:
                consuming[0] = None
            if (
                slot
                and state.task_id != previous_task
                and state.mode == "running"
                and state.instruction == slot["instruction"]
                and key in entries
            ):
                bound[state.task_id] = (key, tuple(bridge.token()))
                bridge.log(
                    "pending_preparation_bound",
                    deferred_id=slot["deferred_id"],
                    successor_identity=list(bridge.token()),
                    observation_revalidation=(
                        "live bootstrap gate; no cached physical facts"
                    ),
                )
            return result

    state._run_deferred = handoff
    previous_normalize = task_language.normalize

    def normalize(agent, raw, observed_context=None):
        with lock:
            binding = bound.get(state.task_id)
            entry = entries.get(binding[0]) if binding else None
            identity_matches = binding is not None and binding[1] == tuple(
                bridge.token()
            )
            ready = (
                entry is not None
                and entry["future"].done()
                and not entry["future"].cancelled()
            )
        if (
            binding is not None
            and entry is not None
            and identity_matches
            and ready
            and state.mode == "running"
            and raw == entry["raw"]
            and observed_context is None
        ):
            if entry["literal_candidate"]:
                # Foreground is the authority on allowed verbatim reuse. An
                # English-looking string alone must not waive its validation.
                return previous_normalize(agent, raw, observed_context)
            try:
                answer = copy.deepcopy(entry["future"].result())
            except (ValueError, RuntimeError, OSError, KeyError) as error:
                bridge.log(
                    "pending_preparation_failed", error_type=type(error).__name__
                )
            else:
                if not task_language.wording_errors(
                    raw, answer["output"]["execution_task"]
                ):
                    answer["prepared_for_deferred_id"] = binding[0][1]
                    bridge.log(
                        "pending_preparation_reused",
                        successor_identity=list(bridge.token()),
                    )
                    return answer
        return previous_normalize(agent, raw, observed_context)

    task_language.normalize = normalize
    previous_close = bridge.close

    def close(*args, **kwargs):
        executor.shutdown(wait=False, cancel_futures=True)
        return previous_close(*args, **kwargs)

    bridge.close = close
    bridge.pending_preparation = dict(observe=observe, entries=entries, bound=bound)
