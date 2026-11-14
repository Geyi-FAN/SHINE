import { explicitObjectSelection } from './robot-object-evidence.js';
import { repairableServerValidation } from './robot-validation-repair.js';
import { robotTaskQuestionKind } from './robot-task-question.js';
import { controlIntent } from './robot-control-semantics.js';
import { MAX_ROBOT_PARAMETER_REPAIRS, parameterRepairReceipt } from './robot-parameter-repair.js';
/** Speech is evidence-gated; this module never executes a robot operation. */
export const ROBOT_ACCEPTED_SPEECH = '任务指令已下发。';
export const ROBOT_QUEUED_SPEECH = '已排队。';
const SETTLED_ROBOT_STATUSES = new Set([
    'accepted',
    'scheduled',
    'replaced',
    'deferred_cancelled',
    'proposal_rejected',
    'clarification_cancelled',
    'needs_confirmation',
    'needs_clarification',
]);
/** Per-input gateway evidence survives a later rejected duplicate/model call. */
export function settledRobotReceipt(turn) {
    return SETTLED_ROBOT_STATUSES.has(String(turn.receipt?.['status']));
}
export function rememberRobotReceipt(turn, receipt) {
    if (settledRobotReceipt(turn))
        return;
    // A later local JSON error proves nothing about an earlier timed-out POST.
    if (turn.receipt?.['status'] === 'unknown' &&
        !SETTLED_ROBOT_STATUSES.has(String(receipt['status'])))
        return;
    turn.receipt = receipt;
}
export function robotExplicitConfirmation(text) {
    return /^(?:确认执行|确认|开始执行|同意执行|执行吧|confirm|confirm execution|(?:yes[,.!;，。；：\s]+)?(?:execute (?:that|this|the) task|do (?:the )?(?:corrected|latest) task|go ahead))[。！!.\s]*$/i.test(text.trim());
}
export function robotCurrentPermission(text) {
  const s=text.trim();
  if (/[?？“”「」"']/.test(s) || /\b(?:if|suppose|do not|don't|never)\b/i.test(s)) return false;
  const action='(?:put|place|move|pick up|grab|open|close|return|turn on|turn off)';
  return new RegExp('^you\\s+(?:can|may)\\s+(?:now\\s+(?:please\\s+)?'+action+'\\b[^.!?]{1,180}|(?:please\\s+)?'+action+'\\b[^.!?]{1,180}\\s+now)[.!\\s]*$','i').test(s);
}
export function robotActionRequest(text) {
    if (['protected', 'deferred_stop'].includes(controlIntent(text) ?? ''))
        return false;
    // A narrow admission rule for requesting another MODEL planning pass, never
    // for deriving tool arguments. Questions/quotes/negations get no repair.
    if (/[？?]|如果|假如|不要|别|为什么|怎么|是否|现在.*哪|他说|你说|“|「/.test(text))
        return false;
    if (/\b(?:if|suppose|do not|don't|never)\b|\?/.test(text.toLowerCase()))
        return false;
    if (explicitObjectSelection(text)) return true;
    if (robotCurrentPermission(text)) return true;
    if (/^\s*(?:please\s+)?(?:keep|maintain|leave)\b[^.!?;]{1,150}(?:\band\s+|;\s*|\bthen\s+)(?:please\s+)?(?:put|place|move|push|slide|open|close|return|turn|switch)\b/i.test(text)) return true;
    // A preservation clause followed by a new imperative is still an action
    // request. This only requests another model pass; it never writes a task.
    if (/^\s*(?:please\s+)?(?:keep|leave)\b[^.!?]{1,140}\b(?:and|then)\s+(?:then\s+)?(?:please\s+)?(?:put|place|move|push|slide|open|close|return|turn|switch)\b/i.test(text)) return true;
    if (/(?:^|[.!]\s*)(?:please\s+)?(?:put|place|move|push|slide|pick up|grab|open|close|return|turn on|turn off|pause|stop|resume|continue|cancel|switch|change the destination)\b/i.test(text) ||
        /^\s*(?:after|once|when)\s+.{1,150}[,;]\s*(?:then\s+)?(?:put|place|move|push|slide|open|close|return|turn)\b/i.test(text))
        return true;
    return /确认.*(?:执行|开始)|(?:放|拿|取|开|关|恢复|切换|暂停|停止|取消|继续|安排|替换).*(?:碗|盘|抽屉|任务|执行)|(?:把|将).*(?:放|拿|取|开|关)|^(?:暂停|停下|停止|继续|取消)(?:一下|任务|执行)?[。！!\s]*$/.test(text);
}
export function robotCancelledConfirmation(turn) {
  const s=turn.status;
  if (!robotExplicitConfirmation(turn.text) || !s || s['state'] !== 'idle' ||
      !s['episode_id'] || s['task_id'] || s['pending_proposal'] ||
      s['pending_clarification'] || s['deferred_task'] ||
      !Number.isInteger(s['task_version']) || !Number.isInteger(s['task_intent_revision'])) return false;
  if (turn.receipt && !(turn.receipt['status'] === 'rejected' && turn.receipt['executed'] === false)) return false;
  const tx=s['dialogue_transactions'];
  const t=tx?.recent_terminal?.[0];
  return !!t && !tx?.active?.length && t['kind'] === 'confirmation' &&
    t['status'] === 'rejected' && t['episode_id'] === s['episode_id'] &&
    t['task_intent_revision'] === s['task_intent_revision'] &&
    t['observed_execution_version'] === s['task_version'] &&
    !t['consumed_by_task_id'];
}
export function robotReceiptSpeech(turn) {
    if (robotCancelledConfirmation(turn))
        return '之前的待确认请求已取消，这句确认不会启动旧任务。如需执行，请重新说明完整任务。';
    const r = turn.receipt;
    if (!r)
        return undefined;
    if (r['reason'] === 'user_transcript_unavailable')
        return '没有获得完整的语音转写，本次没有下发新任务。请完整重说一次。';
    if (r['status'] === 'needs_clarification') {
        const p = r['pending_clarification'];
        return p?.question
            ? (/[\u3400-\u9fff]/u.test(p.question) ? `尚未下发新任务。${p.question}` : p.question)
            : '澄清记录无效，请重新说明任务。';
    }
    if (r['status'] === 'clarification_cancelled')
        return '已取消这次任务澄清，未下发新任务。';
    if (r['status'] === 'needs_confirmation') {
        const p = r['pending_proposal'];
        return p?.question
            ? (/[\u3400-\u9fff]/u.test(p.question) ? `新任务尚未执行。${p.question}`.slice(0, 256) : p.question)
            : '没有建立有效的待确认任务，请重新说明。';
    }
    if (r['status'] === 'accepted') {
        if (r['state'] === 'paused')
            return '已暂停机械臂，保持当前位置。';
        if (r['state'] === 'cancelled')
            return '已取消任务，机械臂保持当前位置。';
        if (turn.operation === 'robot_resume' && r['state'] === 'running')
            return '已恢复当前任务，继续执行原目标。';
        return ROBOT_ACCEPTED_SPEECH;
    }
    if (r['status'] === 'scheduled')
        return ROBOT_QUEUED_SPEECH;
    if (r['status'] === 'replaced')
        return '已记录等待任务，当前任务通过完成检查后才会执行。';
    if (r['status'] === 'deferred_cancelled')
        return '已取消等待任务，当前任务保持原状态。';
    if (r['status'] === 'proposal_rejected')
        return '已拒绝这条待确认任务，未下发新任务。';
    if (r['status'] === 'rejected' &&
        r['deferred_update']?.blocked)
        return '本次等待任务更新未完成；旧等待任务已暂停交接，请明确新的后续任务。原任务状态请查看页面。';
    if (r['code'] === 'robot_invalid_json' && r['dispatch_attempted'] === false)
        return '任务参数未能完整生成，自动补救仍未完成下发。这不是场景缺少物体，本轮没有启动新任务。';
    if (r['status'] === 'unknown')
        return '没有收到操作回执，执行结果暂不确定，请查看任务状态；不会自动重发。';
    if (/robot_waiting_not_requested|deferred_requires_explicit_completion_request/.test(JSON.stringify(r)))
        return '排队请求被拒绝：你没有要求等待当前任务完成。本次新任务未下发，原任务未因此切换。';
    if (/only_a_paused_task_can_resume|no_current_task/.test(JSON.stringify(r)))
        return '恢复请求未被受理：当前没有可直接恢复的暂停任务。请查看当前任务状态。';
    if (/mixed_action_observation_unsupported/.test(JSON.stringify(r)))
        return '当前暂不支持动作完成后自动接续观察，请将动作和提问分开下达；本次新任务未下发，也没有改成打开炉灶。';
    if (/observation_is_not_action/.test(JSON.stringify(r)))
        return '查看炉灶是观察要求，不能替换成打开炉灶。请明确先执行哪项动作；本次没有切换任务。';
    if (/unsupported_recovery_goal/.test(JSON.stringify(r)))
        return '当前执行器尚未验证倒瓶扶正技能，不能省略扶正要求后继续执行。这次新任务未下发。';
    if (/spatial_target_needs_clarification/.test(JSON.stringify(r)))
        return '炉灶旁还没有明确前后左右，请说明目标位置；本次没有改成炉灶前方执行。';
    if (/temporal_request_needs_clarification/.test(JSON.stringify(r)))
        return '时间表达还不明确，请说明是现在执行，还是等当前任务完成后执行；这次未下发新任务。';
    if (/object_not_in_scene/.test(JSON.stringify(r)))
        return '场景清单没有你明确指定的物体，这条指令未下发。';
    if (/^clarification_destination_relation_mismatch(?::|$)/.test(String(r['error'] ?? '')))
        return '生成的任务没有保留你指定的目的地或放置方式，已阻止下发。请明确完整要求。';
    if (/^(?:destination_reference_unresolved|clarification_missing_destination)(?::|$)/.test(String(r['error'] ?? '')))
        return '还不能确定你要放到哪个位置，这条新指令未下发；这不表示操作对象不存在。请明确目的地。';
    if (/object_reference_unresolved|robot_reference_requires_memory/.test(JSON.stringify(r)))
        return '还不能确定你指的是哪个物体，这条新指令未下发；这不表示现场没有该物体。';
    if (/instruction_entity_mismatch/.test(JSON.stringify(r)))
        return '生成的任务没有完整保留你指定的对象或目的地，已阻止下发，请明确完整要求。';
    return '这次操作没有成功受理，请查看任务状态并重新说明指令。';
}
export function robotMissingReceiptSpeech(turn) {
    if (turn.status?.['state'] === 'paused')
        return '没有取得有效操作回执，当前任务仍处于暂停状态，尚未恢复执行。';
    return '没有取得有效操作回执，本次请求尚未确认下发；不会自动重发。';
}
/** Reuse already-generated audio only when its full transcript equals evidence. */
export function robotReceiptMatchesSpeech(turn, text) {
    const normalize = (value) => value
        .normalize('NFKC')
        .toLowerCase()
        .replace(/[\p{P}\p{Z}\s]/gu, '');
    const expected = robotReceiptSpeech(turn);
    if (!expected || !text.trim())
        return false;
    if (normalize(text) === normalize(expected))
        return true;
    if (!['needs_confirmation', 'needs_clarification'].includes(String(turn.receipt?.['status'])))
        return false;
    const proposal = turn.receipt?.[turn.receipt?.['status'] === 'needs_clarification'
        ? 'pending_clarification'
        : 'pending_proposal'];
    return (!!proposal?.question && normalize(text) === normalize(proposal.question));
}
/** Only affirmative robot completion claims; questions/negations are not claims. */
export function robotCompletionClaim(text) {
    if (/[?？]|是不是|是否|尚未|还没|没有|未完成|not yet|not completed/i.test(text))
        return false;
    return /(?:任务|操作).*(?:已完成|已经完成|完成了|成功了)|(?:已经|已)(?:经)?(?:把.{0,24})?(?:放在|放到|放进|放入|归位|关闭|打开)|(?:碗|奶酪|酒瓶|抽屉).*(?:放好了|已归位)|(?:task|operation) (?:is |has )?(?:completed|finished)|already (?:placed|returned|closed|opened)/i.test(text);
}
export function robotClarificationAnswer(turn) {
    return (!!turn.status?.['pending_clarification'] &&
        !/[?？]|如果|假如|先不要|不要执行|暂停|停止|取消|确认执行|现在.*哪/.test(turn.text) &&
        !/^(?:嗯|呃|哦|好|好的|谢谢|对)[。！!\s]*$/.test(turn.text.trim()));
}
export function robotReplyDecision(turn, text) {
    const status = turn.status;
    if (robotCancelledConfirmation(turn)) return 'receipt';
    if (!turn.receipt &&
        !/[?？]|尚未|没有|不能|不会/.test(text) &&
        /已(?:经)?暂停|已经停(?:止|下)|已停住/.test(text) &&
        status?.['state'] !== 'paused')
        return robotActionRequest(turn.text) && !turn.attempted && !turn.repaired
            ? 'repair'
            : 'missing';
    // Even a self-consistent spoken promise is not evidence of a resume. This
    // also covers hallucinated claims after a backchannel, which cannot repair
    // or authorize any mutation.
    if (!turn.receipt &&
        status?.['state'] === 'paused' &&
        !/[?？]|没有|尚未|不能|不会|未能/.test(text) &&
        /已经?恢复|正在恢复|恢复了|已继续执行/.test(text))
        return robotActionRequest(turn.text) && !turn.attempted && !turn.repaired
            ? 'repair'
            : 'missing';
    const transactions = status?.['dialogue_transactions'];
    const confirmation = transactions?.recent_terminal?.find((row) => row['kind'] === 'confirmation');
    const consumed = confirmation?.['status'] === 'consumed' &&
        confirmation['episode_id'] === status?.['episode_id'] &&
        confirmation['consumed_by_task_id'] === status?.['task_id'];
    const duplicateRejection = turn.receipt?.['status'] === 'rejected' &&
        /unknown_or_expired_proposal/.test(String(turn.receipt['error']));
    if (robotExplicitConfirmation(turn.text) &&
        !status?.['pending_proposal'] &&
        !!status?.['task_id'] &&
        consumed &&
        (!turn.receipt || duplicateRejection)) {
        if (['running', 'verifying'].includes(String(status?.['state'])))
            return 'already_running';
        if (status?.['state'] === 'paused')
            return 'already_paused';
        if (status?.['state'] === 'completed' &&
            status?.['completion'] === 'verified') {
            const current = status['agent_execution']?.['completion_current_verified'];
            return ['agent', 'qwen', 'codex'].includes(String(status['execution_backend'])) && current !== true
                ? 'completion_unverified'
                : 'completed';
        }
    }
    // An explicit continue-current request needs no new mutation when that very
    // task is already running. Do not demand a fabricated operation receipt.
    if (!turn.receipt &&
        !turn.attempted &&
        (/^(?:嗯|哦|啊|，|,|请|你|帮我|麻烦|\s)*(?:继续|接着)(?:执行)?(?:当前|现在|这个|的|任务|执行|吧|。|！|!|\s)*$/.test(turn.text.trim()) ||
            /^(?:please\s+)?(?:continue|resume)(?:\s+executing)?\s+(?:(?:the|that|this)\s+)?(?:current|same)\s+task[.!\s]*$/i.test(turn.text.trim())) &&
        ['running', 'verifying'].includes(String(turn.status?.['state'])) &&
        !!turn.status?.['task_id'] &&
        !!turn.status?.['instruction'])
        return 'already_running';
    // A new task cannot borrow an old pre-input proposal as speech authority.
    if (!turn.receipt && robotActionRequest(turn.text) && /请确认(?:是否)?执行|请确认.*(?:新任务|这个任务)|please confirm (?:whether|to execute|this task)/i.test(text))
        return !turn.attempted && !turn.repaired ? 'repair' : 'missing';
    const contradictsCompleted = turn.status?.['state'] === 'completed' &&
        !/[?？]|没有|尚未|并非|不是/.test(text) &&
        /正在(?:执行|把|将|放|抓|拿|打开|关闭|归位)/.test(text);
    if ((robotCompletionClaim(text) || contradictsCompleted) && !turn.receipt) {
        const current = turn.status?.['agent_execution']?.['completion_current_verified'];
        if (['agent', 'qwen', 'codex'].includes(String(turn.status?.['execution_backend'])) &&
            current !== true)
            return 'completion_unverified';
        if (turn.status?.['state'] !== 'completed' ||
            turn.status?.['completion'] !== 'verified')
            return 'missing';
        // A destination/current-task answer is not an attempt to start a new action.
        // Retain its content; the terminal watcher independently announces completion.
        return !turn.attempted && robotTaskQuestionKind(turn.text)
            ? 'original'
            : 'completed';
    }
    if (turn.receipt) {
        if (repairableServerValidation(turn.receipt) && !turn.attempted && (turn.repairAttempts ?? 0) < MAX_ROBOT_PARAMETER_REPAIRS)
            return 'repair';
        if ([
            'robot_invalid_json',
            'robot_unresolved_user_choice',
            'robot_transaction_stale',
            'robot_stale_task_version',
            'robot_clarification_answer_missing',
            'robot_unexpected_argument',
            'robot_constraints_missing',
            'historical_task_requires_memory',
            'robot_missing_identity',
            'robot_waiting_not_requested',
            'robot_reference_requires_memory',
        ].includes(String(turn.receipt['code'])) &&
            turn.receipt['dispatch_attempted'] === false &&
            !turn.attempted &&
            (!turn.repaired ||
                (parameterRepairReceipt(turn.receipt) &&
                    (turn.repairAttempts ?? 1) < MAX_ROBOT_PARAMETER_REPAIRS)) &&
            (robotActionRequest(turn.text) || ['robot_begin_clarification', 'robot_answer_clarification'].includes(turn.operation ?? '')))
            return 'repair';
        return 'receipt';
    }
    if (robotClarificationAnswer(turn) && !turn.attempted)
        return turn.repaired ? 'missing' : 'repair';
    const rejected = /没有|不存在|无法|不能|不支持|未找到/.test(text);
    const alreadyPaused = /暂停|停下|停止/.test(turn.text) && turn.status?.['state'] === 'paused';
    if (robotActionRequest(turn.text) && !alreadyPaused && (!rejected || robotCurrentPermission(turn.text))) {
        return !turn.attempted && !turn.repaired ? 'repair' : 'missing';
    }
    // Unsupported promises are never surfaced, including hallucinated replies to
    // frustration/backchannels. Read-only factual status answers remain allowed.
    if (!turn.status &&
        /已经?开始|正在.*(?:放|拿|开|关)|已下发|已安排|请确认是否执行|马上.*(?:执行|放|开|关)/.test(text))
        return 'missing';
    return 'original';
}
