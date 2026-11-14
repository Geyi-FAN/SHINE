/** Evaluator-only publication barrier. This module never moves the robot. */
export function freshPausedSnapshot(snapshot, receipt, previousSequence) {
  return receipt?.status === 'accepted' && receipt?.state === 'paused'
    && Boolean(receipt.episode_id && receipt.task_id)
    && Number.isSafeInteger(receipt.task_version)
    && Number.isSafeInteger(snapshot?.publication_sequence)
    && snapshot.publication_sequence > previousSequence
    && snapshot.episode_id === receipt.episode_id
    && snapshot.task_id === receipt.task_id
    && snapshot.task_version === receipt.task_version
    && snapshot.task_intent_revision === receipt.task_intent_revision
    && snapshot.mode === 'paused';
}

export function frozenPauseAudit(before, after) {
  const checks = {
    both_paused: before.mode === 'paused' && after.mode === 'paused',
    same_episode: Boolean(before.episode_id) && before.episode_id === after.episode_id,
    same_task: Boolean(before.task_id) && before.task_id === after.task_id,
    same_version: before.task_version === after.task_version
      && before.task_intent_revision === after.task_intent_revision,
    fresh_after_publication: Number.isSafeInteger(after.publication_sequence)
      && after.publication_sequence > before.publication_sequence,
    physics_step_unchanged: before.physics_step === after.physics_step,
    control_step_unchanged: before.control_step === after.control_step,
    simulation_time_unchanged: before.simulation_time === after.simulation_time,
    physical_state_unchanged: Boolean(before.physical_state_sha256)
      && before.physical_state_sha256 === after.physical_state_sha256,
  };
  return {before, after, checks, passed: Object.values(checks).every(Boolean)};
}
