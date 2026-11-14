"""Narrow intake-bound revalidation across automatic task completion only."""
import copy,time

def bind(bridge,name,args,intake):
    s=bridge.state;record=intake.get(args.get('voice_input_id'));decision=bridge.acceptance_decision or {}
    if not(record and name in('robot_revise_task','robot_schedule_task') and args.get('source')=='qwen_realtime_current_user' and
           args.get('episode_id')==s.episode==record['episode_id'] and args.get('user_utterance')==record['text'] and
           record['task_id']==s.task_id and record['semantic_revision']==s.task_intent_revision and
           record['mode']=='running' and s.mode=='completed' and s.completion_status=='verified' and
           type(args.get('expected_task_version'))is int and args['expected_task_version']==record['version'] and
           s.version==record['version']+1 and 0<=time.monotonic()-record['monotonic']<=30 and
           decision.get('accepted') is True and tuple(decision.get('subject',[]))==bridge.token()[:3]):return args
    updated=copy.deepcopy(args);updated['expected_task_version']=s.version
    bridge.log('same_task_completion_race_revalidated',input_id=args['voice_input_id'],original_expected_version=args['expected_task_version'],revalidated_version=s.version,semantic_revision=s.task_intent_revision,reason='actual recorded input preceded automatic completion of same task; normal authorization still required')
    return updated
