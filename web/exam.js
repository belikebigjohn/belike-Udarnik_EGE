/* Exam practice lives in the existing EGE tab; no external navigation required. */
let examHome=null,examSession=null,examBusy=false,examTick=null,examSaveTimer=null;
let examChain=Promise.resolve(),examTab='numbers',examFilter='all';
renderEgeIntro=async function(){
  view='ege';screen.innerHTML='<p class="lead">Готовим экзаменационный эфир…</p>';
  try{examHome=await api('/api/exam/home');if(view==='ege')renderExamHome();}
  catch(e){if(view==='ege')showLearningError(e);}
};
function examTabs(){
  return '<div class="exam-tabs" role="tablist">'+[['numbers','По номерам'],['random','Случайная'],['mock','Пробный вариант']].map(([id,title])=>'<button role="tab" aria-selected="'+(examTab===id)+'" data-exam-tab="'+id+'">'+title+'</button>').join('')+'</div>';
}
function renderExamHome(){
  const h=examHome;
  screen.innerHTML='<div class="eyebrow">ЕГЭ · русский язык · 2027</div><h1>Проверка перед эфиром.</h1><p class="lead">Экзаменационные форматы, спокойный темп и разбор каждого решения.</p>'+
    '<div class="stats"><div class="stat"><b>'+h.solved+'</b><span>разных заданий решено</span></div><div class="stat"><b>'+(h.accuracy===null?'—':h.accuracy+'%')+'</b><span>точность</span></div><div class="stat"><b>'+h.mistakes+'</b><span>ошибок</span></div></div>'+examTabs()+'<div id="examTabBody"></div>'+
    '<section class="program-section"><div class="eyebrow">Вернуться в эфир</div>'+
    h.active.map(s=>actionCard(s.label,'Продолжить с сохранённого места','data-exam-resume="'+s.id+'"','↺')).join('')+
    actionCard('Повторение ЕГЭ','Ошибки по расписанию. Все ошибки можно открыть фильтром «С ошибками».','id="examReviewStart"','↺')+'</section>'+
    '<details class="source-drawer"><summary>Статистика за неделю</summary>'+h.week.map(d=>'<div class="summary-item"><span>'+d.day+'</span><span>'+d.total+' ответов · '+(d.accuracy===null?'—':d.accuracy+'%')+'</span></div>').join('')+
    '<p class="footnote">Сильные темы (от 3 попыток): '+h.strongest.map(t=>'№'+t.number+' '+t.accuracy+'%').join(', ')+'</p><p class="footnote">Стоит повторить: '+h.weakest.map(t=>'№'+t.number+' '+t.accuracy+'%').join(', ')+'</p></details>'+
    '<details class="source-drawer"><summary>История попыток</summary>'+h.history.map(s=>actionCard(s.label,s.created_at.slice(0,10),'data-exam-resume="'+s.id+'"','≡')).join('')+'</details>'+
    '<p class="footnote">Авторские задания по формату ФИПИ. Сторонние банки не копировались. Тема считается освоенной после верных ответов в разные дни.</p>';
  document.querySelectorAll('[data-exam-tab]').forEach(b=>b.onclick=()=>{examTab=b.dataset.examTab;renderExamHome();});
  document.querySelectorAll('[data-exam-resume]').forEach(b=>b.onclick=()=>resumeExam(b.dataset.examResume));
  $('#examReviewStart').onclick=()=>beginExam({mode:'review',count:10});
  renderExamTab();
}
function renderExamTab(){
  const body=$('#examTabBody');
  if(examTab==='numbers'){
    body.innerHTML='<label class="field-label" for="examFilter">Показывать</label><select id="examFilter" class="wide-input">'+[['all','Все задания'],['unseen','Не решённые'],['mistakes','С ошибками'],['mastered','Освоенные']].map(([k,t])=>'<option value="'+k+'">'+t+'</option>').join('')+'</select>'+
      '<div class="exam-map" aria-label="Карта подготовки">'+examHome.numbers.map(n=>'<button data-exam-number="'+n.number+'" class="exam-map-cell '+n.state+'" aria-label="Задание '+n.number+', '+escapeHtml(n.title)+'">'+n.number+'</button>').join('')+'</div>'+
      examHome.numbers.map(n=>( {4:'Ударения',5:'Паронимы',6:'Грамматические нормы',9:'Орфография',16:'Пунктуация'}[n.number] ? '<h2 class="exam-topic">'+{4:'Ударения',5:'Паронимы',6:'Грамматические нормы',9:'Орфография',16:'Пунктуация'}[n.number]+'</h2>' : '')+'<div class="exam-number-card"><div><h3>№'+n.number+'. '+escapeHtml(n.title)+'</h3><p class="footnote">'+n.max_score+' '+(n.max_score===1?'балл':'балла')+' · '+n.count+' вопросов · решено '+n.solved+' · точность '+(n.accuracy===null?'—':n.accuracy+'%')+'</p><p class="footnote">'+n.filters[examFilter]+' подходят под фильтр</p></div><button class="secondary" data-exam-number="'+n.number+'" '+(!n.filters[examFilter]?'disabled':'')+'>'+(n.count?'Тренироваться':'База готовится')+'</button></div>').join('');
    $('#examFilter').value=examFilter;$('#examFilter').onchange=e=>{examFilter=e.target.value;renderExamTab();};
    document.querySelectorAll('[data-exam-number]').forEach(b=>b.onclick=()=>beginExam({mode:'numbers',numbers:[Number(b.dataset.examNumber)],count:5,filter:examFilter}));
  }else if(examTab==='random'){
    body.innerHTML='<p class="lead">Выбери номера. Внутри выпуска нет повторяющихся вопросов.</p><div class="exam-number-picker">'+examHome.numbers.filter(n=>n.count).map(n=>'<label><input type="checkbox" name="examNumbers" value="'+n.number+'" checked>№'+n.number+'</label>').join('')+'</div><button class="small-link" id="examToggleNumbers">Снять / выбрать все</button>'+
      '<label class="field-label" for="examCount">Вопросов в выпуске</label><select id="examCount" class="wide-input">'+[5,10,20,30].map(n=>'<option>'+n+'</option>').join('')+'</select>'+
      '<label class="number-option"><input id="examTimer" type="checkbox"><span>С таймером · 2 минуты на вопрос в общем запасе времени</span></label>'+
      '<label class="field-label" for="examReveal">Показывать объяснения</label><select id="examReveal" class="wide-input"><option value="immediate">Сразу после проверки</option><option value="end">После завершения</option></select>'+
      '<button class="primary" id="randomExamStart">Начать тренировку →</button>';
    $('#examToggleNumbers').onclick=()=>{const inputs=[...document.querySelectorAll('[name="examNumbers"]')];const checked=inputs.some(i=>!i.checked);inputs.forEach(i=>i.checked=checked);};
    $('#randomExamStart').onclick=()=>beginExam({mode:'random',numbers:[...document.querySelectorAll('[name="examNumbers"]:checked')].map(i=>Number(i.value)),count:Number($('#examCount').value),timer:$('#examTimer').checked,reveal:$('#examReveal').value});
  }else{
    const available=examHome.numbers.filter(n=>n.count).length;
    body.innerHTML='<h2>Тематический вариант №4–21</h2><p class="lead">'+available+' из 18 номеров. По одному заданию на номер, в порядке экзамена. Можно пропускать и возвращаться до сдачи.</p><p class="lead">Таймер — 36 минут. Ответы и баллы появятся после сдачи.</p><button class="primary" id="mockExamStart">Открыть вариант →</button>';
    $('#mockExamStart').onclick=()=>beginExam({mode:'mock'});
  }
}
async function beginExam(payload){
  stopTimers();if(examBusy)return;examBusy=true;
  try{examSession=await api('/api/exam/start',payload);view='exam';tg?.BackButton?.show();renderExamSession();}
  catch(e){showLearningError(e);}finally{examBusy=false;}
}
async function resumeExam(id){
  stopTimers();clearInterval(examTick);clearTimeout(examSaveTimer);
  try{examSession=await api('/api/exam/session',{session_id:id});view='exam';tg?.BackButton?.show();renderExamSession();}
  catch(e){showLearningError(e);}
}
function examAnswerMarkup(q,value=''){
  if(q.type==='matching')return '<div class="exam-matching-options">'+q.options.map((o,i)=>'<p><b>'+(i+1)+')</b> '+escapeHtml(o)+'</p>').join('')+'</div><div class="exam-matching">'+q.left.map((left,i)=>'<label><span>'+String.fromCharCode(1040+i)+') '+escapeHtml(left)+'</span><select class="wide-input" data-exam-match="'+i+'" aria-label="Ответ для '+String.fromCharCode(1040+i)+'"><option value="">—</option>'+q.options.map((_,j)=>'<option value="'+(j+1)+'" '+(value[i]===String(j+1)?'selected':'')+'>'+(j+1)+'</option>').join('')+'</select></label>').join('')+'</div>';
  if(q.type==='multi')return '<div class="answer-options">'+q.options.map((o,i)=>'<label class="number-option"><input type="checkbox" data-exam-choice="'+(i+1)+'" '+(value.includes(String(i+1))?'checked':'')+'><span><b>'+(i+1)+')</b> '+escapeHtml(o)+'</span></label>').join('')+'</div>';
  return (q.options.length?'<div class="exam-matching-options">'+q.options.map((o,i)=>'<p>'+(i+1)+') '+escapeHtml(o)+'</p>').join('')+'</div>':'')+
    '<label class="field-label" for="examTyped">Ответ '+(q.type==='digits'?'цифрами без пробелов и запятых':'словом без кавычек')+'</label><input id="examTyped" class="wide-input" value="'+escapeHtml(value)+'" maxlength="250" autocomplete="off" spellcheck="false" '+(q.type==='digits'?'inputmode="numeric"':'')+'>';
}
function currentExamAnswer(){
  const q=examSession.questions[examSession.position];
  if(q.type==='multi')return [...document.querySelectorAll('[data-exam-choice]:checked')].map(i=>i.dataset.examChoice).join('');
  if(q.type==='matching')return [...document.querySelectorAll('[data-exam-match]')].map(i=>i.value||'0').join('');
  return $('#examTyped')?.value||'';
}
function displayExamAnswer(q,value){
  if(!value)return 'Нет ответа';
  return q.type==='matching'?String(value).replace(/0/g,'—'):String(value);
}
function examFeedbackMarkup(q){
  const r=q.result;if(!r)return '';
  return '<div class="exam-feedback '+(r.correct?'answer-good':'answer-bad')+'"><h3 class="'+(r.correct?'correct':'incorrect')+'">'+(r.correct?'Верно':r.score?'Частично верно':'Нужна правка')+' · '+r.score+'/'+r.max_score+'</h3><p>Твой ответ: <strong>'+escapeHtml(displayExamAnswer(q,r.chosen))+'</strong></p><p class="correct">Правильно: <strong>'+escapeHtml(r.answer)+'</strong></p><p class="lead">'+escapeHtml(r.explanation)+'</p><p class="footnote">+'+r.xp+' XP · '+escapeHtml(r.source)+'</p><a class="footnote" href="'+escapeHtml(r.source_url)+'" target="_blank" rel="noopener">Источник формата ↗</a></div>';
}
function renderExamSession(){
  clearInterval(examTick);clearTimeout(examSaveTimer);
  if(examSession.finished){renderExamSummary();return;}
  const s=examSession,q=s.questions[s.position];
  screen.innerHTML='<div class="progress-top"><span>ЕГЭ №'+q.number+'</span><span>'+(s.position+1)+' / '+s.total+'</span></div><div class="progress-track"><i style="width:'+100*s.answered.length/s.total+'%"></i></div><div class="studio-kicker"><span>'+escapeHtml(s.label)+'</span><time id="examClock"></time></div>'+
    '<div class="exam-navigation" aria-label="Навигация по заданиям">'+s.questions.map((t,i)=>'<button data-exam-jump="'+i+'" class="'+(s.answered.includes(t.id)?'answered':'')+' '+(i===s.position?'current':'')+'" aria-label="Вопрос '+(i+1)+', задание '+t.number+'">'+(i+1)+'<small>№'+t.number+'</small></button>').join('')+'</div>'+
    '<div class="learning-card"><p class="question-title multiline">'+escapeHtml(q.prompt)+'</p>'+
    '<div id="examAnswerFields">'+examAnswerMarkup(q,q.draft)+'</div>'+examFeedbackMarkup(q)+'</div><p id="examSaveState" class="footnote" role="status">Черновик сохранён на сервере</p><div id="examError" role="alert"></div>'+
    (s.mode==='mock'?'<button class="secondary" id="examSave">Сохранить черновик</button>':'<button class="primary" id="examCheck" '+(s.answered.includes(q.id)?'disabled':'')+'>Проверить</button>')+
    '<div class="exam-actions"><button class="secondary" id="examPrevious" '+(s.position===0?'disabled':'')+'>← Назад</button><button class="secondary" id="examNext">'+(s.answered.includes(q.id)?'Следующее':'Пропустить / дальше')+' →</button></div>'+
    '<button class="secondary" id="examFinish">Завершить и посмотреть результат</button><button class="small-link" id="examLeave">Сохранить и выйти</button>';
  if(s.answered.includes(q.id))document.querySelectorAll('#examAnswerFields input,#examAnswerFields select').forEach(i=>i.disabled=true);
  document.querySelectorAll('[data-exam-jump]').forEach(b=>b.onclick=()=>examNavigate(Number(b.dataset.examJump)));
  const edited=()=>{if($('#examSaveState'))$('#examSaveState').textContent='Сохраняем черновик…';clearTimeout(examSaveTimer);examSaveTimer=setTimeout(()=>saveExamDraft().catch(()=>{}),600);};
  document.querySelectorAll('#examAnswerFields input,#examAnswerFields select').forEach(i=>{i.oninput=edited;i.onchange=edited;});
  if($('#examCheck'))$('#examCheck').onclick=()=>examAction('answer',s.position,true).catch(()=>{});
  if($('#examSave'))$('#examSave').onclick=()=>saveExamDraft().catch(()=>{});
  $('#examPrevious').onclick=()=>examNavigate(Math.max(0,s.position-1));
  $('#examNext').onclick=()=>examNavigate(Math.min(s.total-1,s.position+1));
  $('#examFinish').onclick=()=>finishExam();
  $('#examLeave').onclick=()=>nav('ege');
  const offset=Date.parse(s.server_now)-Date.now();
  const update=()=>{if(view!=='exam'||!s.deadline)return;const seconds=Math.max(0,Math.ceil((Date.parse(s.deadline)-Date.now()-offset)/1000));const clock=$('#examClock');if(clock)clock.textContent=Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');if(!seconds){clearInterval(examTick);finishExam();}};
  examTick=setInterval(update,500);update();channelTransition();
}
function examAction(action,position=examSession.position,render=false){
  clearTimeout(examSaveTimer);
  const q=examSession.questions[examSession.position],value=currentExamAnswer(),sid=examSession.id;
  const task=async()=>{
    const r=await api('/api/exam/action',{session_id:sid,revision:examSession.revision,action,question_id:q.id,answer:value,position});
    if(examSession?.id!==sid)return;
    examSession=r;
    if(view==='exam'){
      if(render||r.finished)renderExamSession();
      else if($('#examSaveState'))$('#examSaveState').textContent='Черновик сохранён на сервере';
    }
  };
  const pending=examChain.then(task);examChain=pending.catch(()=>{});
  return pending.catch(e=>{if(view==='exam'){const box=$('#examError');if(box)box.innerHTML='<p class="incorrect">'+escapeHtml(e.message)+'</p><button class="secondary" id="examRecover">Восстановить тренировку</button>';if($('#examRecover'))$('#examRecover').onclick=()=>resumeExam(sid);}throw e;});
}
function saveExamDraft(){
  if(view!=='exam'||examSession.finished)return Promise.resolve();
  const q=examSession.questions[examSession.position];
  if(examSession.answered.includes(q.id))return examChain;
  return examAction('save');
}
async function examNavigate(position){
  if(examBusy)return;examBusy=true;
  try{await examAction('navigate',position,true);}catch(_){}finally{examBusy=false;}
}
async function finishExam(){
  if(examBusy)return;examBusy=true;
  try{await saveExamDraft();await examAction('finish',examSession.position,true);}catch(_){}finally{examBusy=false;}
}
function renderExamSummary(){
  clearInterval(examTick);
  const s=examSession,wrong=s.questions.filter(q=>!q.result?.correct),correct=s.correct||0;
  screen.innerHTML='<div class="eyebrow">OFF AIR · ЕГЭ</div><h1>Практика завершена.</h1><p class="lead">'+escapeHtml(s.label)+'</p>'+
    '<div class="stats"><div class="stat"><b>'+correct+'/'+s.total+'</b><span>верных</span></div><div class="stat"><b>'+Math.round(100*correct/s.total)+'%</b><span>точность</span></div><div class="stat"><b>'+s.points+'/'+s.max_points+'</b><span>первичных баллов</span></div></div><p class="lead">+'+s.xp+' XP · '+(wrong.length?'Стоит повторить номера: '+[...new Set(wrong.map(q=>q.number))].join(', '):'Все задания решены верно!')+'</p>'+
    '<p class="footnote">Это результат тематической практики. Ошибки включены в интервальное повторение.</p>'+
    s.questions.map(q=>'<details class="exam-review '+(q.result?.correct?'':'needs-review')+'" '+(!q.result?.correct?'open':'')+'><summary>№'+q.number+' · '+(q.result?.correct?'Верно':'Разобрать')+' · '+q.result?.score+'/'+q.result?.max_score+'</summary><p class="multiline">'+escapeHtml(q.prompt)+'</p>'+(q.options.length?'<div>'+q.options.map((o,i)=>'<p>'+(i+1)+') '+escapeHtml(o)+'</p>').join('')+'</div>':'')+(q.left?'<div>'+q.left.map((o,i)=>'<p>'+String.fromCharCode(1040+i)+') '+escapeHtml(o)+'</p>').join('')+'</div>':'')+examFeedbackMarkup(q)+'</details>').join('')+
    '<button class="primary" id="examBackHome">К заданиям ЕГЭ</button>';
  $('#examBackHome').onclick=()=>nav('ege');
}
const navBeforeExam=nav;
nav=async function(name){
  clearInterval(examTick);clearTimeout(examSaveTimer);
  if(view==='exam'&&examSession&&!examSession.finished){
    try{await saveExamDraft();}catch(_){return;}
  }
  return navBeforeExam(name);
};
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&view==='exam'&&examSession&&!examSession.finished){examChain.then(()=>resumeExam(examSession.id));}else if(document.visibilityState==='hidden'&&view==='exam')saveExamDraft().catch(()=>{});});
// Reuse exam input forms in the existing spaced-repetition screen.
const baseQuestionMarkup=questionMarkup;
questionMarkup=function(q,readonly=false,answer=null){
  if(q.type!=='exam')return baseQuestionMarkup(q,readonly,answer);
  if(readonly)return '<div class="answer-reveal">'+escapeHtml(answer)+'</div>';
  const actual={...q,type:q.exam_type};
  return examAnswerMarkup(actual)+
    '<button class="primary" id="examSrsCheck">Проверить ответ</button>';
};
const beforeExamLearning=renderLearning;
renderLearning=function(){
  beforeExamLearning();
  if(session?.question?.type==='exam'&&!session.finished){
    const q=session.question;
    $('#examSrsCheck').onclick=()=>{
      const answer=q.exam_type==='multi'?[...document.querySelectorAll('[data-exam-choice]:checked')].map(i=>i.dataset.examChoice).join(''):
        q.exam_type==='matching'?[...document.querySelectorAll('[data-exam-match]')].map(i=>i.value||'0').join(''):$('#examTyped').value;
      submitLearning(answer);
    };
  }
};
