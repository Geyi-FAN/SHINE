/** A second correction is allowed only for a proven pre-dispatch parameter fault. */
export const MAX_ROBOT_PARAMETER_REPAIRS = 2;
export const ROBOT_PARAMETER_REPAIR_WINDOW_MS = 15_000;
const PARAMETER_CODES = new Set([
    'robot_invalid_json',
    'robot_constraints_missing',
    'robot_unexpected_argument',
    'robot_missing_identity',
    'robot_stale_task_version',
]);
export function parameterRepairReceipt(receipt) {
    return (!!receipt && ['rejected','error'].includes(receipt['status']) &&
        receipt['executed'] === false &&
        (receipt['dispatch_attempted'] === false ||
            (receipt['code'] === 'robot_stale_task_version' && receipt['status'] === 'rejected' && receipt['transport_attempted'] === true)) &&
        PARAMETER_CODES.has(String(receipt['code'])));
}
