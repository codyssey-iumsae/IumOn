'use strict';
(() => {
 const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
 const synth=window.speechSynthesis;
 let active=null, generation=0, speechGeneration=0, autoRead=false, voiceConsent=false;
 const roots=()=>[document.querySelector('#main'),document.querySelector('#modal-body')].filter(Boolean);
 const sayStatus=(root,text)=>{const el=root?.querySelector('.voice-status');if(el)el.textContent=text;};
 function stopListening(){
  generation++;
  if(active){const old=active;active=null;try{old.abort();}catch{}}
  document.querySelectorAll('[data-listen]').forEach(b=>{b.textContent='말로 답하기';b.setAttribute('aria-pressed','false');});
 }
 function stopReading(){speechGeneration++;if(synth)synth.cancel();}
 function stopAll(){stopListening();stopReading();const dialog=document.querySelector('#voice-consent');if(dialog?.open)dialog.close();}
 function rootText(root){
  const clone=root.cloneNode(true);
  clone.querySelectorAll('.voice-tools,.voice-input-tools,script,style,input,textarea,svg,[hidden],details:not([open])').forEach(e=>e.remove());
  return (clone.innerText||clone.textContent||'').replace(/\s+/g,' ').trim();
 }
 function chunks(text){return text.match(/[^.!?。\n]{1,160}(?:[.!?。\n]|$)|.{1,160}/g)||[];}
 function read(root){
  stopAll();
  if(!synth||!window.SpeechSynthesisUtterance){sayStatus(root,'이 브라우저는 읽어주기를 지원하지 않아요.');return;}
  const text=rootText(root);if(!text)return;
  const current=speechGeneration;
  const parts=chunks(text).slice(0,150);
  const voices=synth.getVoices();
  const voice=voices.find(v=>v.lang?.toLowerCase().startsWith('ko'));
  if(!voice){sayStatus(root,'한국어 음성이 없으면 기기 설정에서 한국어 음성을 추가해 주세요.');}
  let index=0;
  const next=()=>{
   if(current!==speechGeneration)return;
   if(index>=parts.length){sayStatus(root,'읽기를 마쳤어요.');return;}
   const u=new SpeechSynthesisUtterance(parts[index++]);u.lang='ko-KR';u.rate=0.85;
   if(voice)u.voice=voice;
   u.onend=next;
   u.onerror=e=>{if(current===speechGeneration&&e.error!=='canceled'&&e.error!=='interrupted')sayStatus(root,'읽기를 마치지 못했어요. 다시 듣기를 눌러 주세요.');};
   synth.speak(u);
  };
  sayStatus(root,'읽고 있어요. 멈추기를 누르면 중단해요.');next();
 }
 const normalize=s=>String(s).replace(/[\s.,!?~。]/g,'').replace(/(입니다|이에요|예요|이요|이야|살|세요|세)$/,'');
 function applyTranscript(root,target,transcript,base){
  if(target){
   if(!target.isConnected)return false;
   let value=transcript.trim();
   if(target.type==='number'){
    const match=value.replace(/\s/g,'').match(/^(?:만)?(\d{1,3})(?:세|살)?(?:입니다|이에요|예요)?[.!?]?$/);
    if(!match){sayStatus(root,'나이를 숫자로 확인하지 못했어요. 숫자를 직접 입력해 주세요.');return false;}
    value=match[1];
   }else value=(base?base.trimEnd()+' ':'')+value;
   const limit=target.maxLength>0?target.maxLength:2000;
   target.value=value.slice(0,limit);target.dispatchEvent(new Event('input',{bubbles:true}));
   sayStatus(root,'들은 내용을 입력했어요. 맞는지 확인하고 다음 버튼을 눌러 주세요.');return true;
  }
  const buttons=[...root.querySelectorAll('.choice')];
  const matches=buttons.filter(b=>normalize(b.querySelector('span')?.textContent||'')===normalize(transcript));
  if(matches.length===1){matches[0].click();sayStatus(root,'선택했어요. 맞는지 확인하고 다음 버튼을 눌러 주세요.');return true;}
  sayStatus(root,'선택지와 정확히 맞지 않아요. 화면의 답을 누르거나 다시 말해 주세요.');return false;
 }
 function listen(root,target,button){
  if(active){stopListening();sayStatus(root,'음성 입력을 멈췄어요.');return;}
  if(!Recognition){sayStatus(root,'이 브라우저는 음성 입력을 지원하지 않아요. 글자나 선택 버튼으로 답해 주세요.');return;}
  if(!window.isSecureContext){sayStatus(root,'음성 입력에는 HTTPS 주소 또는 같은 기기의 localhost가 필요해요.');return;}
  if(!voiceConsent){
   const dialog=document.querySelector('#voice-consent');
   dialog.showModal();
   dialog.querySelector('[data-voice-agree]').onclick=()=>{voiceConsent=true;dialog.close();if(root.isConnected)listen(root,target,button);};
   return;
  }
  stopReading();
  const rec=new Recognition(),current=++generation;
  const base=target?.value||'';
  active=rec;rec.lang='ko-KR';rec.continuous=false;rec.interimResults=true;
  button.textContent='음성 입력 멈추기';button.setAttribute('aria-pressed','true');
  sayStatus(root,'마이크 연결 중이에요. 연결되면 말씀해 주세요.');
  rec.onstart=()=>{if(current===generation)sayStatus(root,'듣고 있어요. 편하게 말씀해 주세요.');};
  let finalText='', lastApplied='', failed=false;
  rec.onresult=e=>{
   if(current!==generation||!root.isConnected||target&&!target.isConnected)return;
   let interim='';finalText='';
   for(let i=0;i<e.results.length;i++){if(e.results[i].isFinal)finalText+=e.results[i][0].transcript;else interim+=e.results[i][0].transcript;}
   if(interim)sayStatus(root,'듣는 중: '+interim);
   if(finalText&&finalText!==lastApplied){applyTranscript(root,target,finalText,base);lastApplied=finalText;}
  };
  rec.onerror=e=>{
   if(current!==generation)return;
   failed=true;
   const errors={'not-allowed':'마이크 권한이 거부됐어요. 브라우저 권한을 확인하거나 직접 입력해 주세요.','service-not-allowed':'이 환경에서는 음성 인식을 사용할 수 없어요. 직접 입력해 주세요.','audio-capture':'사용할 마이크가 없어요. 연결을 확인해 주세요.','no-speech':'말소리를 듣지 못했어요. 다시 눌러 말씀해 주세요.','network':'음성 인식 연결에 실패했어요. 인터넷을 확인하거나 직접 입력해 주세요.','language-not-supported':'한국어 음성 인식을 지원하지 않는 환경이에요.'};
   sayStatus(root,errors[e.error]||'음성 입력을 마치지 못했어요. 다시 시도하거나 직접 입력해 주세요.');
  };
  rec.onend=()=>{
   if(current!==generation)return;
   active=null;button.textContent='말로 답하기';button.setAttribute('aria-pressed','false');
   if(!finalText&&!failed)sayStatus(root,'인식된 말이 없어요. 다시 말하거나 직접 입력해 주세요.');
  };
  try{rec.start();}catch{active=null;generation++;button.textContent='말로 답하기';button.setAttribute('aria-pressed','false');sayStatus(root,'음성 입력을 시작하지 못했어요. 다시 시도하거나 직접 입력해 주세요.');}
 }
 function mount(root){
  if(!root||root.querySelector('.voice-tools'))return;
  const tools=document.createElement('section');tools.className='voice-tools';tools.setAttribute('aria-label','음성 도움');
  tools.innerHTML='<div class="voice-buttons"><button type="button" class="secondary" data-read>화면 읽어주기</button><button type="button" class="secondary" data-voice-stop>음성 멈추기</button><label><input type="checkbox" data-auto-read> 다음 질문 자동으로 듣기</label></div><small>기기·브라우저의 음성 서비스를 사용해요.</small><p class="voice-status" role="status" aria-live="polite"></p>';
  root.prepend(tools);
  tools.querySelector('[data-read]').onclick=()=>read(root);
  tools.querySelector('[data-voice-stop]').onclick=()=>{stopAll();sayStatus(root,'음성을 멈췄어요.');};
  const toggle=tools.querySelector('[data-auto-read]');toggle.checked=autoRead;
  toggle.onchange=()=>{autoRead=toggle.checked;roots().forEach(r=>{const t=r.querySelector('[data-auto-read]');if(t)t.checked=autoRead;});if(autoRead)read(root);else stopReading();};
  if(!synth){tools.querySelector('[data-read]').disabled=true;toggle.disabled=true;sayStatus(root,'이 브라우저는 읽어주기를 지원하지 않아요.');}
  const targets=[...root.querySelectorAll('#life-story,#free-text,#age')];
  for(const target of targets) addMic(root,target,target);
  if(!targets.length&&root.querySelector('.choices'))addMic(root,null,root.querySelector('.choices'));
  if(autoRead&&root.querySelector('h1')&&!document.querySelector('#modal')?.open)read(root);
 }
 function addMic(root,target,anchor){
  const wrap=document.createElement('div');wrap.className='voice-input-tools';
  const button=document.createElement('button');button.type='button';button.className='secondary';button.dataset.listen='';button.textContent='말로 답하기';button.setAttribute('aria-pressed','false');
  button.onclick=()=>listen(root,target,button);
  wrap.append(button);
  const hint=document.createElement('small');hint.textContent=Recognition?'말한 내용을 확인한 뒤 다음으로 넘어가세요.':'음성 입력을 지원하지 않는 브라우저예요. 직접 입력해 주세요.';
  if(!Recognition)button.disabled=true;
  wrap.append(hint);anchor.after(wrap);
 }
 const consent=document.createElement('dialog');consent.id='voice-consent';
 consent.innerHTML='<h2>말로 답해 볼까요?</h2><p>음성을 글자로 바꾸려면 마이크 권한이 필요해요. 브라우저에 따라 음성이 브라우저 제공업체의 인식 서비스로 전송될 수 있어요. 이음온 서버는 이 기능의 음성 파일을 받거나 저장하지 않아요.</p><p>이름·연락처·주민등록번호는 말하지 마세요. 인식된 글을 Codyssey AI에 보내는 동의는 별도로 받아요. 읽어주기도 기기·브라우저의 음성 서비스를 사용해요.</p><div class="voice-buttons"><button type="button" class="primary" data-voice-agree>동의하고 말하기</button><button type="button" class="secondary" data-voice-cancel>직접 입력할게요</button></div>';
 document.body.append(consent);
 consent.querySelector('[data-voice-cancel]').onclick=()=>consent.close();
 window.addEventListener('iumon:screen',e=>{stopAll();mount(e.detail.root);});
 window.addEventListener('iumon:leave',stopAll);
 document.querySelector('#modal')?.addEventListener('close',stopAll);
 window.addEventListener('pagehide',stopAll);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stopAll();});
 roots().forEach(mount);
})();
