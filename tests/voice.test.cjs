const {test,mock}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/static/voice.js'),'utf8');
const phrase=(transcript,isFinal=true)=>Object.assign([{transcript}],{isFinal});
const textarea=value=>({isConnected:true,type:'textarea',value,maxLength:2000,dispatchEvent(){}});
function setup({supported=true,secure=true}={}){
 mock.timers.reset();mock.timers.enable({apis:['setTimeout']});
 const listeners={},instances=[],spoken=[];
 let dialog;
 const el=()=>({isConnected:true,textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v;},dispatchEvent(){},querySelectorAll(){return[];}});
 const status=el(),button=el();
 const root={...el(),querySelector(s){if(s==='.voice-status')return status;return null;},
  cloneNode(){return{querySelectorAll(){return[];},textContent:'첫 번째 질문입니다. 두 번째 질문입니다.'};}};
 const agree=el(),cancel=el();
 const doc={hidden:false,body:{append(e){dialog=e;}},querySelector(s){return s==='#voice-consent'?dialog:null;},
  querySelectorAll(){return[button];},addEventListener(k,cb){listeners[k]=cb;},
  createElement(){return{...el(),showModal(){this.open=true;},close(){this.open=false;},querySelector(s){return s==='[data-voice-agree]'?agree:cancel;}};}};
 class Rec{constructor(){instances.push(this);this.starts=0;}
  start(){if(this.running)throw new Error('InvalidStateError');this.running=true;this.starts++;this.onstart?.();}
  end(){this.running=false;this.onend?.();}
  abort(){this.aborted=true;this.onerror?.({error:'aborted'});this.end();}}
 const synth={cancel(){this.canceled=true;},getVoices(){return[{lang:'ko-KR'}];},speak(u){spoken.push(u);}};
 const window={SpeechRecognition:supported?Rec:undefined,speechSynthesis:synth,isSecureContext:secure,addEventListener(k,cb){listeners[k]=cb;}};
 const ctx={window,document:doc,Event:class{},SpeechSynthesisUtterance:class{constructor(t){this.text=t;}},console,setTimeout,clearTimeout};
 window.SpeechSynthesisUtterance=ctx.SpeechSynthesisUtterance;
 vm.runInNewContext(source.replace('roots().forEach(mount);','window.testVoice={listen,read,stopAll,applyTranscript,SILENCE_MS,FIRST_WORDS_MS};'),ctx);
 const api=window.testVoice;
 function consent(target=null){api.listen(root,target,button);agree.onclick();return instances.at(-1);}
 function result(rec,text){rec.onresult({results:[phrase(text)]});}
 return{api,root,status,button,instances,agree,listeners,spoken,synth,result,consent,doc};
}
test('no microphone is started before explicit consent',()=>{
 const s=setup();s.api.listen(s.root,null,s.button);assert.equal(s.instances.length,0);assert.equal(s.doc.querySelector('#voice-consent').open,true);
 s.agree.onclick();assert.equal(s.instances.length,1);assert.equal(s.instances[0].lang,'ko-KR');
});
test('unsupported and insecure contexts keep manual input available',()=>{
 for(const options of [{supported:false},{secure:false}]){const s=setup(options);s.api.listen(s.root,null,s.button);assert.equal(s.instances.length,0);assert.ok(s.status.textContent);}
});
test('dictation appends once without submitting and ignores late results after stop',()=>{
 const s=setup();s.consent();s.api.stopAll();
 const target={isConnected:true,type:'text',value:'기존 이야기',maxLength:2000,events:[],dispatchEvent(e){this.events.push(e);}};
 s.api.listen(s.root,target,s.button);const rec=s.instances.at(-1);
 s.result(rec,'택시비가 부담돼요');s.result(rec,'택시비가 부담돼요');
 assert.equal(target.value,'기존 이야기 택시비가 부담돼요');
 s.api.stopAll();s.result(rec,'늦게 도착한 말');assert.equal(target.value,'기존 이야기 택시비가 부담돼요');assert.equal(rec.aborted,true);
});
test('screen navigation aborts recording and ignores detached targets',()=>{
 const s=setup();s.consent();const rec=s.instances[0];s.listeners['iumon:leave']();assert.equal(rec.aborted,true);
 const target={isConnected:false,type:'text',value:'보존'};assert.equal(s.api.applyTranscript(s.root,target,'변경',''),false);assert.equal(target.value,'보존');
});
test('permission error gives actionable feedback and returns button to idle',()=>{
 const s=setup();s.consent();const rec=s.instances[0];rec.onerror({error:'not-allowed'});rec.onend();assert.match(s.status.textContent,/권한/);assert.equal(s.button.attrs['aria-pressed'],'false');
});
test('spoken ages must be numeric and text respects maxlength',()=>{
 const s=setup();const target={isConnected:true,type:'number',value:'',maxLength:-1,dispatchEvent(){}};
 assert.equal(s.api.applyTranscript(s.root,target,'65세',''),true);assert.equal(target.value,'65');
 assert.equal(s.api.applyTranscript(s.root,target,'예순다섯',''),false);assert.equal(target.value,'65');
 const text={...target,type:'text',maxLength:5};s.api.applyTranscript(s.root,text,'긴 이야기입니다','');assert.equal(text.value.length,5);
});
test('only an unambiguous exact choice is selected',()=>{
 const s=setup();let clicks=0;const choice={querySelector(){return{textContent:'청양읍'};},click(){clicks++;}};
 s.root.querySelectorAll=()=>[choice];assert.equal(s.api.applyTranscript(s.root,null,'청양읍',''),true);assert.equal(clicks,1);
 assert.equal(s.api.applyTranscript(s.root,null,'서울',''),false);assert.equal(clicks,1);
 s.root.querySelectorAll=()=>[choice,choice];assert.equal(s.api.applyTranscript(s.root,null,'청양읍',''),false);
});
test('reading uses Korean, stops microphone, and cannot restart after stop',()=>{
 const s=setup();s.consent();s.api.read(s.root);assert.equal(s.instances[0].aborted,true);assert.equal(s.spoken[0].lang,'ko-KR');
 const utterance=s.spoken[0],count=s.spoken.length;s.api.stopAll();utterance.onend();assert.equal(s.spoken.length,count);
});
test('hidden page cancels speech and microphone',()=>{
 const s=setup();s.consent();s.doc.hidden=true;s.listeners.visibilitychange();assert.equal(s.instances[0].aborted,true);assert.equal(s.synth.canceled,true);
});
test('repeated final recognition cannot toggle a choice off',()=>{
 const s=setup();let clicks=0;
 s.root.querySelectorAll=()=>[{querySelector(){return{textContent:'건강'};},click(){clicks++;}}];
 s.consent();const rec=s.instances[0];s.result(rec,'건강');s.result(rec,'건강');assert.equal(clicks,1);
});
test('a browser end after a pause restarts listening and the next phrase follows the first once',()=>{
 const s=setup();const target=textarea('기존 이야기');const rec=s.consent(target);assert.equal(rec.continuous,true);
 rec.onresult({results:[phrase('택시비가',false)]});
 rec.onresult({results:[phrase('택시비가 부담돼요'),phrase('병원이',false)]});
 rec.onresult({results:[phrase('택시비가 부담돼요'),phrase('병원이 멀어요')]});
 mock.timers.tick(s.api.SILENCE_MS-1);rec.end();
 assert.equal(rec.starts,2);assert.equal(s.button.attrs['aria-pressed'],'true');
 rec.onresult({results:[phrase('버스가 없어요')]});
 assert.equal(target.value,'기존 이야기 택시비가 부담돼요 병원이 멀어요 버스가 없어요');
});
test('silence after the last recognized words ends listening and returns the button to idle',()=>{
 const s=setup();const target=textarea('');const rec=s.consent(target);
 s.result(rec,'택시비가 부담돼요');
 mock.timers.tick(s.api.SILENCE_MS-1);rec.onresult({results:[phrase('택시비가 부담돼요'),phrase('병원',false)]});
 mock.timers.tick(s.api.SILENCE_MS-1);assert.equal(s.button.attrs['aria-pressed'],'true');
 mock.timers.tick(1);
 assert.equal(rec.aborted,true);assert.equal(rec.starts,1);
 assert.equal(s.button.attrs['aria-pressed'],'false');assert.equal(s.button.textContent,'말로 답하기');
 assert.equal(s.status.textContent,'말씀이 끝난 것 같아 듣기를 멈췄어요. 들은 내용을 확인해 주세요.');
 assert.equal(target.value,'택시비가 부담돼요');
});
test('stopping by hand prevents any restart',()=>{
 const s=setup();const target=textarea('');const rec=s.consent(target);
 s.result(rec,'택시비가 부담돼요');
 s.api.listen(s.root,target,s.button);rec.end();mock.timers.tick(s.api.FIRST_WORDS_MS);
 assert.equal(rec.starts,1);assert.equal(s.button.attrs['aria-pressed'],'false');assert.equal(s.status.textContent,'음성 입력을 멈췄어요.');
});
test('a choice question and the age field still stop after one accepted answer',()=>{
 const s=setup();let clicks=0;
 s.root.querySelectorAll=()=>[{querySelector(){return{textContent:'청양읍'};},click(){clicks++;}}];
 const rec=s.consent();s.result(rec,'청양읍');rec.end();
 assert.equal(clicks,1);assert.equal(rec.starts,1);assert.equal(s.button.attrs['aria-pressed'],'false');assert.match(s.status.textContent,/선택했어요/);
 const a=setup();const age={...textarea(''),type:'number',maxLength:-1};const ageRec=a.consent(age);
 a.result(ageRec,'65세');ageRec.end();
 assert.equal(age.value,'65');assert.equal(ageRec.starts,1);assert.equal(a.button.attrs['aria-pressed'],'false');
});
test('a choice retried after a mismatch is judged on the new words alone',()=>{
 const s=setup();let clicks=0;
 s.root.querySelectorAll=()=>[{querySelector(){return{textContent:'청양읍'};},click(){clicks++;}}];
 const rec=s.consent();s.result(rec,'서울');
 assert.equal(clicks,0);assert.equal(s.button.attrs['aria-pressed'],'true');
 rec.end();
 assert.equal(rec.starts,2);assert.match(s.status.textContent,/정확히 맞지 않아요/);
 rec.onresult({results:[phrase('청양읍')]});
 assert.equal(clicks,1);assert.equal(s.button.attrs['aria-pressed'],'false');
 const t=setup();const missed=t.consent();t.result(missed,'서울');missed.end();mock.timers.tick(t.api.SILENCE_MS);
 assert.equal(t.button.attrs['aria-pressed'],'false');assert.match(t.status.textContent,/정확히 맞지 않아요/);
});
test('no-speech inside the first-words window restarts, not-allowed does not',()=>{
 const s=setup();const rec=s.consent(textarea(''));
 mock.timers.tick(s.api.FIRST_WORDS_MS-1);rec.onerror({error:'no-speech'});rec.end();
 assert.equal(rec.starts,2);assert.equal(s.button.attrs['aria-pressed'],'true');assert.match(s.status.textContent,/듣고 있어요/);
 mock.timers.tick(1);
 assert.equal(s.button.attrs['aria-pressed'],'false');assert.equal(s.status.textContent,'인식된 말이 없어요. 다시 말하거나 직접 입력해 주세요.');
 const d=setup();const denied=d.consent(textarea(''));
 denied.onerror({error:'not-allowed'});denied.end();
 assert.equal(denied.starts,1);assert.equal(d.button.attrs['aria-pressed'],'false');assert.match(d.status.textContent,/권한/);
});
