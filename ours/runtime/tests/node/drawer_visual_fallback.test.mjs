import test from 'node:test';
import assert from 'node:assert/strict';
import {drawerStateAnswer} from '../../voice/dist/tools/robot-feedback.js';
for(const question of ['How far open is the middle drawer?','Is the middle drawer shut?','中层抽屉打开了吗？']){
 test('no simulator facts keep visual responsibility: '+question,()=>{
  const state={episode_id:'current',qa_evidence:{drawer_facts:null}};
  assert.equal(drawerStateAnswer(question,state),undefined);
 });
}
test('stale facts do not overwrite current visual answer',()=>{
 assert.equal(drawerStateAnswer('Is the middle drawer closed?',{episode_id:'e',qa_evidence:{drawer_facts:{episode_id:'e',observed_at:Date.now()/1000-20}}}),undefined);
});
test('different episode cannot supply drawer state',()=>{
 assert.equal(drawerStateAnswer('Is the middle drawer shut?',{episode_id:'e',qa_evidence:{drawer_facts:{episode_id:'old',observed_at:Date.now()/1000,drawers:{middle:{open:false,closed_current:true}}}}}),undefined);
});
test('mixed object relation still uses visual model',()=>{
 assert.equal(drawerStateAnswer('Is the bowl inside the open drawer?',{episode_id:'e'}),undefined);
});
test('supported legacy explicit facts retain physical distinction',()=>{
 const state={episode_id:'e',qa_evidence:{drawer_facts:{episode_id:'e',observed_at:Date.now()/1000,drawers:{middle:{open:false,closed_current:false}}}}};
 assert.match(drawerStateAnswer('Is the middle drawer shut?',state),/尚未达到打开条件，也未完全关闭/);
});
