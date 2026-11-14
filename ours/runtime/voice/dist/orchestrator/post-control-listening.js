/** A played receipt reopens input; a silent continuation is not playback.
 * Never changes response ownership, task leases, microphone mute, tools or
 * playback receipts. Only start/revise acceptance qualifies; not pause,
 * waiting, clarification or an unverified/model-written acknowledgement.
 */
export const POST_CONTROL_LISTENING_VERSION = 'played-control-listening-v1';

function currentScope(context, scope) {
    return !!scope && !!context.robotTurn &&
        context.epoch === scope.epoch &&
        context.realtimeGeneration === scope.generation &&
        context.taskInputVersion === scope.inputVersion &&
        context.latestTaskInputId === scope.inputId &&
        context.robotTurn.inputId === scope.inputId &&
        context.robotTurn.generation === scope.generation &&
        context.robotTurn.version === scope.inputVersion;
}

export function controlReceiptScope(context, turn, receipt, key) {
    if (context.robotTurn !== turn || !turn.fixedReceiptSpoken ||
        receipt?.status !== 'accepted' || receipt.executed !== true ||
        !['running', 'verifying'].includes(receipt.state)) return undefined;
    let fields;
    try { fields = JSON.parse(key); } catch { return undefined; }
    if (!Array.isArray(fields) || fields.length !== 5 ||
        fields[0] !== turn.inputId || fields[1] !== receipt.episode_id ||
        fields[2] !== receipt.task_id || fields[3] !== receipt.task_version ||
        !['robot_start_task', 'robot_revise_task'].includes(fields[4])) return undefined;
    const scope = {inputId: turn.inputId, inputVersion: turn.version,
        generation: turn.generation, epoch: context.epoch, operation: fields[4], key};
    return currentScope(context, scope) ? scope : undefined;
}

export function rememberPlayedControl(context, receipt, call) {
    if (context.stopping || context.transportRecovering || context.speechInProgress ||
        call.epoch !== context.epoch || call.outputId !== receipt?.outputId ||
        !currentScope(context, receipt.t07Scope)) return false;
    context.t07PlayedControlReceipt = {...receipt.t07Scope, outputId: receipt.outputId};
    return true;
}

export function canListenAfterPlayedControl(context, event) {
    if (event.authority !== 'tool_continuation' || context.stopping ||
        context.transportRecovering || context.speechInProgress || context.playbackSuppressed ||
        !currentScope(context, context.t07PlayedControlReceipt) ||
        !context.robotTurn.fixedReceiptSpoken || context.controlReceiptPlayback) return false;
    if (event.inputItemId && event.inputItemId !== context.t07PlayedControlReceipt.inputId) return false;
    for (const item of [context.resultSpeech, context.activePeerReport,
                        context.activeSearchResult, context.activeProactiveDelivery]) {
        if (item?.audioForwarded && !item.playbackCompleted) return false;
    }
    return true;
}

/** A completed local receipt cannot cancel a newer task's model response. */
export function controlPlaybackOwnsCurrentTurn(context, playback) {
    const turn=context.robotTurn;
    if (!turn || context.speechInProgress || context.stopping ||
        playback.epoch!==context.epoch || playback.generation!==context.realtimeGeneration ||
        playback.inputVersion!==context.taskInputVersion || turn.version!==playback.inputVersion ||
        turn.generation!==playback.generation) return false;
    if (turn.inputId===playback.inputId) return true;
    // A pure stop may reuse the independently committed pause receipt. A Stop
    // plus replacement utterance does NOT set turn.operation=robot_pause.
    return playback.operation==='robot_pause' && turn.operation==='robot_pause' &&
        !!playback.requestId && turn.receipt?.request_id===playback.requestId;
}
