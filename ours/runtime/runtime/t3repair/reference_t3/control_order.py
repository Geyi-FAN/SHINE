"""Order control and physics from real receipts, never from delayed video IO."""
from score_preflight import lines


def command_step(directory, event, episode):
    step = event.get("simulation_step")
    if type(step) is int and step >= 0:
        return step
    request_id = event.get("request_id")
    if not request_id:
        return None
    for row in lines(directory / "recordings/api.jsonl"):
        response = row.get("response", {})
        if (row.get("path") == "/tool" and isinstance(response, dict)
                and response.get("request_id") == request_id
                and response.get("episode_id") == episode
                and response.get("status") == "accepted"):
            step = response.get("simulation_steps")
            if type(step) is int and step >= 0:
                return step
    return None


def action_after(tick, event, applied_step):
    if not tick.get("policy_action"):
        return False
    if applied_step is not None and type(tick.get("step")) is int:
        return tick["step"] > applied_step
    # Legacy artifacts without a matching receipt remain conservative; do
    # not invent a frame or silently call missing evidence a success.
    return tick["time"] > event["time"] + 0.05
