"""Read-only task selection with explicit temporal evidence and ambiguity."""

import re
from grounding import mentions


def select_tasks(tasks, query, current_id):
    query = query.lower().strip()
    wanted = {e for _, e in mentions(query) if e}
    matches = []
    for record in tasks:
        instruction = record.get("complete_instruction", "").lower()
        if wanted and not wanted <= {e for _, e in mentions(instruction) if e}:
            continue
        if (
            re.search(r"之前|刚才|上一个|previous|earlier", query)
            and record["task_id"] == current_id
        ):
            continue
        if re.search(r"已完成|已经完成|完成过|completed", query) and not record.get(
            "ever_completed"
        ):
            continue
        if re.search(r"取消过|已取消|cancelled|canceled", query) and not record.get(
            "ever_cancelled"
        ):
            continue
        if "中间" in query and "middle" not in instruction:
            continue
        if re.search(r"上层|顶层", query) and "top" not in instruction:
            continue
        if (
            not wanted
            and re.search(r"[a-z]{3}", query)
            and not re.search(r"previous|earlier|completed|cancelled|task", query)
        ):
            if query not in instruction:
                continue
        matches.append(record)
    if not matches and not wanted and re.search(r'之前|刚才|previous|earlier',query) and not re.search(r'上一个|previous one before',query):
        # Only a sole same-episode paused task; do not choose among alternatives.
        if len(tasks)==1 and tasks[0]['task_id']==current_id and tasks[0].get('state')=='paused':
            matches=[tasks[0]]
    return {
        "candidates": matches[:20],
        "resolution": "none" if not matches else "unique" if len(matches) == 1 else "ambiguous",
        "note": "Historical completion is not current physical evidence. Ambiguous references need clarification or an exact proposal.",
    }
