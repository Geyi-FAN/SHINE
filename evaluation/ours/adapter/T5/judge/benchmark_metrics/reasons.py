"""Stable machine codes plus Chinese explanations for audit and review UI."""
REASONS = {
 'restore_episode_start': ('RESTORE_NOT_CONFIRMED', '未确认位置、松手、支撑及明确要求的稳定／撤离条件全部满足'),
 'close_event': ('CLOSE_NOT_CONFIRMED', '未确认抽屉在允许间隙内连续满足关闭窗口'),
 'preserve_position': ('POSITION_PRESERVATION_VIOLATED', '物体相对指令切换位置超过保持容差'),
 'preserve_articulation_state': ('JOINT_PRESERVATION_VIOLATED', '关节相对指令切换状态超过保持容差'),
 'preserve_containment': ('CONTAINMENT_VIOLATED', '明确要求保留在容器内的物体离开容器'),
 'native_target': ('TARGET_NOT_REACHED', '策略执行阶段未达到原生目标'),
 'completion_order': ('COMPLETION_ORDER_VIOLATED', '前置完成事件未早于后续首次完成事件'),
}
