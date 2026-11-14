import assert from 'node:assert/strict';
import {uniqueCurrentInstructionReference as bind} from '../../voice/dist/tools/robot-current-reference.js';
const args={episode_id:'ep',expected_task_version:2};
const current={episode_id:'ep',task_id:'t',task_version:2,instruction_memory_id:'actual-id',unique_source_object:false};
const record={task_id:'t',instruction_memory_id:'actual-id',is_current:true,candidate_contract:{entities:['stove'],semantic_check:{decision:'checked'}}};
const memory={episode_id:'ep',current_reference:current,task_selection:{candidates:[record]}};
let n=0;function equal(a,b){assert.equal(a,b);n++;}
equal(bind(memory,args,'Keep it off and open the middle drawer instead.'),'actual-id');
const drawer={...record,candidate_contract:{entities:['cabinet'],semantic_check:{decision:'checked'}}};
equal(bind({...memory,task_selection:{candidates:[drawer]}},args,'Keep it open and put the cheese in the bowl.'),'actual-id');
const bowl={...record,candidate_contract:{entities:['bowl','stove'],semantic_check:{decision:'checked'}}};
equal(bind({...memory,current_reference:{...current,unique_source_object:true},task_selection:{candidates:[bowl]}},args,'Put it on the plate instead.'),'actual-id');
for(const changed of [
 {...memory,episode_id:'other'},
 {...memory,current_reference:{...current,episode_id:'other'}},
 {...memory,current_reference:{...current,task_version:3}},
 {...memory,current_reference:{...current,instruction_memory_id:undefined}},
 {...memory,task_selection:{candidates:[{...record,is_current:false}]}},
 {...memory,task_selection:{candidates:[{...record,task_id:'other'}]}},
 {...memory,task_selection:{candidates:[record,record]}},
 {...memory,task_selection:{candidates:[bowl]}},
 {...memory,task_selection:{candidates:[{...record,candidate_contract:{entities:['stove']}}]}},
 {...memory,task_selection:{candidates:[{...record,candidate_contract:{entities:[],semantic_check:{decision:'checked'}}}]}}
])equal(bind(changed,args,'Keep it off and open the drawer.'),undefined);
equal(bind(memory,{...args,expected_task_version:1},'Keep it off.'),undefined);
equal(bind(memory,args,'Keep it or the other object there.'),undefined);
equal(bind(memory,args,'Keep it at the previous location.'),undefined);
equal(bind(memory,args,'Put it in the bowl.'),undefined);
equal(bind(memory,args,'Keep that ball there.'),undefined);
console.log(`${n} actual-current-reference/ambiguity/stale-version assertions passed; no generated instruction`);
