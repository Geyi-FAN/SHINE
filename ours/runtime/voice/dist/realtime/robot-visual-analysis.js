import {requestBoundedReview} from './bounded-visual-review.js';
import {visualReviewPrompt,parseVisualReview,ROBOT_VISUAL_ANSWER_POLICY,MULTIVIEW_COUNT_POLICY} from '../tools/qa-grounding.mjs';
import {appendFileSync,writeFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {appendFileSync as qaAppend,writeFileSync as qaWrite} from 'node:fs';
import {dirname as qaDir,join as qaJoin} from 'node:path';
import { createHash } from 'node:crypto';
export async function analyzeRobotImage(o) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    o.signal?.addEventListener('abort', abort, { once: true });
    if (o.signal?.aborted)
        controller.abort();
    const deadline = Date.now()+14000;
    const timer = setTimeout(abort, 14000);
    try {
        const url = new URL(o.endpoint);
        url.protocol = 'https:';
        url.pathname = '/compatible-mode/v1/chat/completions';
        url.search = '';
        o.onDebug?.('robot_visual.request', { model: 'qwen3.8-max', question: o.question, image_sha256: createHash('sha256').update(Buffer.from(o.image, 'base64')).digest('hex'), requested_at: Date.now() / 1000 });
        if(process.env.VOICE_T6_QA_AUDIT){
 const log=process.env.VOICE_T6_QA_AUDIT,stamp=Date.now(),image=Buffer.from(o.image,'base64'),file=qaJoin(qaDir(log),'qa_model_input_'+stamp+'.jpg');
 qaWrite(file,image);qaAppend(log,JSON.stringify({kind:'model_input',time:stamp/1000,model:'qwen3.8-max',question:o.question,image_file:file,image_sha256:createHash('sha256').update(image).digest('hex')})+'\n');
}
        const response = await fetch(url, {
            method: 'POST',
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${o.apiKey || ''}`,
            },
            body: JSON.stringify({
                model: 'qwen3.8-max',
                enable_thinking: false,
                temperature: 0,
                max_tokens: 500,
                messages: [
                    {
                        role: 'system',
                        content: '你是只读机器人场景问答助手。执行记录不是当前图像，指令不是成功。用“画面中”描述采集到的快照，不把画面采集后的变化当作已知。判断位置先结合CURRENT MAIN、CURRENT WRIST与机器人夹爪读数区分持物和放置：物体仍在手指之间且悬于支撑面上方时，可以回答“仍在夹爪中”；只有实际放下并有支撑证据才说“放在某处”。不要把二维重叠当作接触，不得仅凭夹爪闭合断言持物身份，也不要从单帧臆测运动方向。参考图仅用于物体身份。区分二维上下与物理支撑、容纳关系；遮挡不等于空。明确当前图像、历史验证和不能确认的部分。炉灶状态只看上方CURRENT MAIN：碗可能遮住加热盘中心，注意碗底外围露出的细红环；灰色碗内壁和下方REFERENCE示例炉灶都不是当前加热盘。看到红色加热环时回答看起来开启；完全遮挡时保持不确定，不要臆称红环不存在。禁止输出动作命令。',
                    },
                    {role:'system',content:ROBOT_VISUAL_ANSWER_POLICY+MULTIVIEW_COUNT_POLICY},
                    {
                        role: 'user',
                        content: [
                            { type: 'text', text: o.question },
                            {
                                type: 'image_url',
                                image_url: { url: `data:image/jpeg;base64,${o.image}` },
                            },
                        ],
                    },
                ],
            }),
        });
        if (!response.ok)
            throw new Error(`robot_visual_http_${response.status}`);
        const data = (await response.json());
        let answer = data.choices?.[0]?.message?.content;
        if (typeof answer !== 'string' || !answer.trim() || answer.length > 16000)
            throw new Error('robot_visual_invalid_answer');
        const candidate=answer.trim(),reviewQuestion=visualReviewPrompt(o.question,candidate);
        if(process.env.VOICE_T6_QA_AUDIT){
          const stamp=Date.now(),image=Buffer.from(o.image,'base64'),file=join(dirname(process.env.VOICE_T6_QA_AUDIT),'qa_model_input_'+stamp+'.jpg');
          writeFileSync(file,image);appendFileSync(process.env.VOICE_T6_QA_AUDIT,JSON.stringify({kind:'model_answer',stage:'candidate',time:stamp/1000,answer:candidate})+'\n');
          appendFileSync(process.env.VOICE_T6_QA_AUDIT,JSON.stringify({kind:'model_input',stage:'grounding_review',time:stamp/1000,model:'qwen3.8-max',question:reviewQuestion,image_file:file,image_sha256:createHash('sha256').update(image).digest('hex')})+'\n');
        }
        const checkedData=await requestBoundedReview(url,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${o.apiKey||''}`},body:JSON.stringify({model:'qwen3.8-max',enable_thinking:false,temperature:0,max_tokens:500,response_format:{type:'json_object'},messages:[{role:'system',content:'你是只读图像事实核验器。严格按当前图像检查对象身份和每个关系断言，用户预设和候选答案不是证据。看不到不等于不存在；不确定就简短说明，禁止生成动作命令。只能输出一个符合要求的JSON对象，不输出分析过程或Markdown。answer只写一句直接回答且不超过80字，reason不超过80字。'},{role:'user',content:[{type:'text',text:reviewQuestion},{type:'image_url',image_url:{url:`data:image/jpeg;base64,${o.image}`}}]}]})},{signal:controller.signal,deadline,onRetry:event=>{
          o.onDebug?.('robot_visual.review_retry',event);
          if(process.env.VOICE_T6_QA_AUDIT){
            const stamp=Date.now(),image=Buffer.from(o.image,'base64'),file=join(dirname(process.env.VOICE_T6_QA_AUDIT),'qa_model_input_'+stamp+'.jpg');
            writeFileSync(file,image);appendFileSync(process.env.VOICE_T6_QA_AUDIT,JSON.stringify({kind:'model_retry',time:stamp/1000,...event})+'\n');
            appendFileSync(process.env.VOICE_T6_QA_AUDIT,JSON.stringify({kind:'model_input',stage:'grounding_review_retry',time:stamp/1000,model:'qwen3.8-max',question:reviewQuestion,image_file:file,image_sha256:createHash('sha256').update(image).digest('hex')})+'\n');
          }
        }});
        const raw=checkedData.choices?.[0]?.message?.content;
        if(typeof raw!=='string')throw Error('robot_visual_review_missing_content');
        if(process.env.VOICE_T6_QA_AUDIT)appendFileSync(process.env.VOICE_T6_QA_AUDIT,JSON.stringify({kind:'grounding_review_raw',time:Date.now()/1000,raw,finish_reason:checkedData.choices?.[0]?.finish_reason})+'\n');
        const review=parseVisualReview(raw);answer=review.answer;
        if(process.env.VOICE_T6_QA_AUDIT)appendFileSync(process.env.VOICE_T6_QA_AUDIT,JSON.stringify({kind:'grounding_review',time:Date.now()/1000,candidate,raw,review})+'\n');
        o.onDebug?.('robot_visual.completed', { model: 'qwen3.8-max', answer: answer.trim() });
        if(process.env.VOICE_T6_QA_AUDIT)qaAppend(process.env.VOICE_T6_QA_AUDIT,JSON.stringify({kind:'model_answer',time:Date.now()/1000,answer:answer.trim()})+'\n');
        return { answer: answer.trim() };
    }
    catch(error) {
        if(process.env.VOICE_T6_QA_AUDIT)appendFileSync(process.env.VOICE_T6_QA_AUDIT,JSON.stringify({kind:'model_error',time:Date.now()/1000,name:error?.name,message:String(error?.message??error).slice(0,500)})+'\n');
        throw error;
    }
    finally {
        clearTimeout(timer);
        o.signal?.removeEventListener('abort', abort);
    }
}
