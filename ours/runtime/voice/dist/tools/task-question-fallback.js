/** A stalled pure task-record query may use fresh read-only task metadata. */
import {robotTaskQuestionKind} from './robot-task-question.js';
import {robotStatusQuestionAnswer} from './robot-feedback.js';
import {dispatchRobotTool} from './robot.js';

export function armTaskQuestionFallback(session, context, turn, deps = {}) {
    const kind = robotTaskQuestionKind(turn.text);
    if (!kind || turn.t6TaskFallbackArmed) return false;
    turn.t6TaskFallbackArmed = true;
    const now = deps.now ?? Date.now;
    const sleep = deps.sleep ?? (ms => new Promise(r => setTimeout(r, ms)));
    const current = () => session.active === context && !context.stopping &&
        context.robotTurn === turn && context.taskInputVersion === turn.version &&
        context.realtimeGeneration === turn.generation && !context.speechInProgress &&
        !context.transportRecovering && !turn.attempted && !turn.receipt &&
        !turn.visualRequested && !turn.replyAudioDelivered &&
        turn.replyOutputId === undefined && !turn.replyDeliveryFailed && !context.resultSpeech;
    const timer = (deps.setTimer ?? setTimeout)(async () => {
        if (!current()) return;
        try {
            if (await turn.record === false || !current()) return;
            const read = deps.readStatus ?? (() => dispatchRobotTool('robot_get_status', '{}',
                `${context.callId}:readonly-task-fallback:${turn.inputId}`));
            const result = await read();
            if (!result.ok || !current()) return;
            const status = JSON.parse(result.receipt);
            const text = kind === 'task' ? robotStatusQuestionAnswer(turn.text, status) :
                status.task_id && status.instruction
                    ? (/[a-z]/i.test(turn.text)&&!/[\p{Script=Han}]/u.test(turn.text)?`The accepted task is: ${String(status.instruction).slice(0,200)}.`:`本次已受理任务的目标是“${String(status.instruction).slice(0, 200)}”。`)
                    : '当前没有已受理的任务，无法从当前任务记录确认目的地。';
            if (!text) return;
            const deadline = now() + 4000;
            const yielded = new Set();
            while (current() && now() < deadline) {
                if (context.responseInFlight || context.pendingToolCalls?.size) {
                    const id = context.currentResponseId;
                    const authority = context.responseAuthorities?.get(id);
                    const lease = context.taskActionLeases?.get(id);
                    if (!context.pendingToolCalls?.size && id && !yielded.has(id) &&
                        ['direct','tool_continuation'].includes(authority) &&
                        lease?.inputId === turn.inputId && lease.inputVersion === turn.version &&
                        lease.generation === turn.generation) {
                        yielded.add(id);
                        // Fence late buffered speech BEFORE cancelResponse(), whose
                        // callback may be synchronous. This cancels only an unheard
                        // read-only model reply, never the running robot task.
                        turn.t6TaskFallbackActive = true;
                        context.t6ReadonlyYieldedResponses ??= new Set();
                        context.t6ReadonlyYieldedResponses.add(id);
                        const accepted = context.realtime?.cancelResponse?.() === true;
                        if (!accepted) {
                            turn.t6TaskFallbackActive = false;
                            context.t6ReadonlyYieldedResponses.delete(id);
                        }
                        session.log.write('realtime.protocol', {type:'robot.task_record_fallback',
                            phase:'readonly_continuation_yield_requested',inputId:turn.inputId,
                            responseId:id,accepted,noMutation:true});
                    }
                    await sleep(50);continue;
                }
                turn.status = status;
                if (session.startResultSpeech(context, text, 'task_result', {fixedAnnouncement:text})) {
                    turn.t6TaskFallbackActive = true;
                    session.log.write('realtime.protocol', {type:'robot.task_record_fallback',
                        phase:'speech_reserved',inputId:turn.inputId,kind,
                        taskId:status.task_id,source:'fresh_authorized_task_record',noMutation:true});
                    return;
                }
                await sleep(50);
            }
            session.log.write('realtime.protocol', {type:'robot.task_record_fallback',
                phase:'channel_busy_no_speech',inputId:turn.inputId,noMutation:true});
        } catch (error) {
            session.log.write('realtime.protocol', {type:'robot.task_record_fallback',
                phase:'unavailable',inputId:turn.inputId,error:String(error?.message ?? error)});
        }
    }, 5000);
    timer?.unref?.();
    return true;
}
