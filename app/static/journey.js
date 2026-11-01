'use strict';
function start(){
 afterQuestions=null;
 if(!statusInfo){toast('자료 연결을 기다려 주세요.');return;}
 route='results';const storyVersion=++requestVersion;
 setMain(`<div class="question-layout"><div class="eyebrow">생활 이야기로 시작해요</div><h1>요즘 어떤 점이 힘드세요?</h1><p class="hint">정책 이름이나 검색어를 몰라도 괜찮아요.<br>말로 답하거나 편하게 적어 주세요.</p><label class="sr-only" for="life-story">생활 속 어려움</label><textarea id="life-story" class="text-input story-input" maxlength="2000" placeholder="예: 무릎이 아파 병원에 자주 가는데, 차가 없고 택시비도 부담돼요."></textarea><label class="consent"><input id="story-consent" type="checkbox">이 이야기를 Codyssey AI에 보내 필요한 도움을 정리하는 데 동의해요. 이름·연락처·주민등록번호는 적지 마세요.</label><p class="error" id="story-error" role="alert"></p><button class="primary full" id="understand-story">필요한 도움 함께 찾기 ${icon('arrow')}</button><button class="plain" id="skip-story">이야기 대신 선택 질문으로 시작할게요</button><p class="notice">말로 입력한 내용은 확인하고 수정할 수 있어요. 이야기만으로 질환이나 소득, 지원 자격을 단정하지 않아요.</p></div>`);
 $('#skip-story').onclick=()=>{requestVersion++;startBasic();};
 $('#understand-story').onclick=async()=>{
  const story=$('#life-story').value.trim();
  if(story.length<5){$('#story-error').textContent='어려운 상황을 조금만 더 알려주세요.';return;}
  if(!$('#story-consent').checked){$('#story-error').textContent='AI 전송에 동의하거나 선택 질문으로 시작해 주세요.';return;}
  const b=$('#understand-story');b.disabled=true;b.textContent='이야기를 정리하고 있어요…';
  try{const data=await api('/api/story',{story,consent:true});if(storyVersion!==requestVersion)return;if(!data.issues.length){$('#story-error').textContent='필요한 도움을 아직 파악하지 못했어요. 조금 더 적거나 선택 질문으로 시작해 주세요.';return;}confirmStory(data.issues);}
  catch(e){if($('#story-error'))$('#story-error').textContent=e.message;}
  finally{if(b.isConnected){b.disabled=false;b.innerHTML='필요한 도움 함께 찾기 '+icon('arrow');}}
 };
}
function confirmStory(issues){
 const selected=new Set(issues.map((_,i)=>i));
 setMain(`<div class="question-layout"><div class="eyebrow">제가 잘 이해했나요?</div><h1>이런 도움이 필요하신가요?</h1><p class="hint">맞지 않는 내용은 눌러서 빼 주세요. 아직 자격을 판단한 것은 아니에요.</p><div class="choices">${issues.map((x,i)=>`<button class="choice selected" data-issue="${i}" aria-pressed="true"><span>${esc(x.label)}<small class="issue-quote">“${esc(x.evidence)}” · ${esc(x.topic)}</small></span><span class="mark">✓</span></button>`).join('')}</div><p class="error" id="confirm-story-error"></p><button class="primary full" id="accept-story">맞아요, 필요한 지원을 찾아주세요 ${icon('arrow')}</button><button class="plain" id="rewrite-story">다시 이야기할게요</button></div>`);
 document.querySelectorAll('[data-issue]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.issue);selected.has(i)?selected.delete(i):selected.add(i);b.classList.toggle('selected',selected.has(i));b.setAttribute('aria-pressed',String(selected.has(i)));b.querySelector('.mark').textContent=selected.has(i)?'✓':'';});
 $('#rewrite-story').onclick=start;
 $('#accept-story').onclick=()=>{const checked=issues.filter((_,i)=>selected.has(i));if(!checked.length){$('#confirm-story-error').textContent='맞는 도움을 한 가지 이상 선택해 주세요.';return;}chooseMainDifficulty(checked);};
}
async function preparation(id){
 if(!profile||!jobToken){toast('문답을 마친 현재 추천 결과에서 신청 준비를 시작해 주세요.');return;}
 const selectedPolicy=results.find(p=>p.id===id);
 const accessRoutes=selectedPolicy?['available','blocked','unknown'].flatMap(k=>selectedPolicy.access?.[k]||[]):[];
 const ask=[];
 for(const [field,kind] of [['mobility','visit'],['digital','online']]){
  if(!(profile.answered||[]).includes(field)&&accessRoutes.some(r=>r.kind===kind))ask.push(bank[field]);
 }
 if(ask.length){draft=structuredClone(profile);questions=ask;questionMode='preparation';editMode=false;step=0;afterQuestions=()=>{profile=structuredClone(draft);preparation(id);};question();return;}

 try{
  const data=await api('/api/prepare',{job_id:jobToken,policy_id:id,profile});
  showModal(`<div class="eyebrow">복지센터 상담 전, 이음온과 준비해요</div><h2>${esc(data.title)}</h2><section class="detail-section"><h3>상담할 때 이렇게 말씀해 보세요</h3><p class="preline consultation-note">${esc(data.consultation_note)}</p></section><section class="detail-section"><h3>먼저 물어볼 질문</h3><ul class="prep-list">${data.questions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></section><section class="detail-section"><h3>준비할 서류</h3>${data.documents.length?data.documents.map(x=>`<p class="preline">${esc(x.text)}</p><small>공식 원문 · ${esc(x.field)}</small>`).join(''):'<div class="privacy-card">공식 자료에서 필요한 서류 목록을 확인하지 못했어요. 서류를 임의로 안내하지 않으니 방문 전에 담당 기관에 물어봐 주세요.</div>'}</section><section class="detail-section"><h3>다음에 할 일</h3><p>${esc(data.next_action)}</p><p class="hint">${data.office?esc(data.office)+'<br>':''}${esc(data.agency)}<br>${esc(data.phone||'문의처는 공식 안내에서 확인해 주세요.')}</p></section><label class="consent"><input id="prep-download-consent" type="checkbox">내 상황이 포함된 상담 메모를 이 기기에 파일로 저장할게요.</label><button class="primary full" id="download-prep">상담 준비 메모 내려받기</button><p class="notice">${esc(data.notice)}</p>`);
  $('#download-prep').onclick=()=>{if(!$('#prep-download-consent').checked){toast('메모 저장 여부를 먼저 선택해 주세요.');return;}const content=`이음온 상담·신청 준비 메모\n\n사업: ${data.title}\n\n${data.consultation_note}\n\n확인할 질문\n${data.questions.map((x,i)=>`${i+1}. ${x}`).join('\n')}\n\n준비서류\n${data.documents.length?data.documents.map(x=>x.text).join('\n'):'공식 자료에서 확인되지 않았습니다. 방문 전 담당 기관에 문의하세요.'}\n\n${data.office?`신청 창구: ${data.office}\n`:''}문의: ${data.agency} ${data.phone}\n공식 안내: ${data.url}\n\n${data.notice}`;const url=URL.createObjectURL(new Blob(['\ufeff'+content],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='이음온_상담준비.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 }catch(e){toast(e.message);}
}

function chooseMainDifficulty(issues){
 let selected=null;
 setMain(`<div class="question-layout"><div class="eyebrow">지금 가장 필요한 도움</div><h1>어떤 어려움부터 도와드릴까요?</h1><p class="hint">여러 어려움이 있으면 모두 필요해요를 선택하셔도 괜찮아요.</p><div class="choices">${issues.map((x,i)=>choice(String(i),x.label,false)).join('')}${choice('all','모두 필요해요',false)}${choice('unknown','잘 모르겠어요',false)}</div><p class="error" id="focus-error"></p><button class="primary full" id="focus-next">이 어려움부터 살펴보기 ${icon('arrow')}</button><button class="plain" id="focus-back">이해한 어려움 다시 확인</button></div>`);
 document.querySelectorAll('.choice').forEach(b=>b.onclick=()=>{selected=b.dataset.value;document.querySelectorAll('.choice').forEach(x=>{const on=x.dataset.value===selected;x.classList.toggle('selected',on);x.setAttribute('aria-pressed',String(on));x.querySelector('.mark').textContent=on?'✓':'';});});
 $('#focus-back').onclick=()=>confirmStory(issues);
 $('#focus-next').onclick=async()=>{
  if(selected===null){$('#focus-error').textContent='먼저 살펴볼 도움을 선택해 주세요.';return;}
  const b=$('#focus-next');b.disabled=true;
  try{const plan=await api('/api/intake-plan',{issues,selected});draft=profile?structuredClone(profile):{region:'청양군',answered:[]};Object.assign(draft,{story_summary:plan.story_summary,focus_summary:plan.focus_summary,search_terms:plan.search_terms||[],needs:plan.needs,priority:plan.priority,priority_mode:plan.priority_mode});delete draft.knee_care;delete draft.transport_mode;draft.answered=(draft.answered||[]).filter(f=>!['knee_care','transport_mode'].includes(f));questions=plan.questions;questionMode='intake';editMode=false;step=0;question();}
  catch(e){if($('#focus-error'))$('#focus-error').textContent=e.message;}finally{if(b.isConnected)b.disabled=false;}
 };
}
