/* Studio extension: keeps the original stress and task-4 screens intact. */
let session = null, feedback = null, answeredQuestion = null, ticking = null, advancing = null;
let submitting = false, timerOffset = 0, lastPayload = {}, selectedCommas = new Set();
const modeNames = {practice:'Учебный эфир',ege:'Репетиция ЕГЭ',survival:'Без права на ошибку',
  teleprompter:'Телесуфлёр',review:'Режиссёрский повтор',emergency:'Экстренный выпуск',word:'Слово сегодняшнего эфира'};
const baseNav = nav;
function stopTimers(){clearInterval(ticking);clearTimeout(advancing);ticking=null;advancing=null;}
function channelTransition(){screen.classList.remove('channel-enter');void screen.offsetWidth;screen.classList.add('channel-enter');}
nav = function(name){
  stopTimers();
  view=name;
  tg?.BackButton?.[name==='home'?'hide':'show']();
  if(name==='channels'){renderChannels();}
  else if(name==='career'){renderCareer();}
  else baseNav(name);
  document.querySelectorAll('.bottom-nav button').forEach(b=>b.classList.toggle('active',b.dataset.nav===name));
  channelTransition();
};
tg?.BackButton?.onClick(()=>nav('home'));
tg?.onEvent?.('themeChanged',applyTheme);
function examText(exam){
  if(!exam)return 'Дата ЕГЭ пока не настроена';
  if(exam.error)return exam.error;
  const prefix=exam.official?'ЕГЭ':'Целевая дата';
  return exam.days<0?prefix+': дата прошла':exam.days===0?prefix+': сегодня':prefix+': '+exam.days+' дн.';
}
function actionCard(title,desc,attrs,icon='↗'){
  return '<button class="channel-card" '+attrs+'><span class="channel-icon" aria-hidden="true">'+icon+'</span><span><strong>'+escapeHtml(title)+'</strong><small>'+escapeHtml(desc)+'</small></span><span aria-hidden="true">→</span></button>';
}
renderHome = function(){
  const d=home.learning;if(!d)return;
  const rankProgress=d.rank.next?100*(d.xp-d.rank.start)/(d.rank.next-d.rank.start):100;
  screen.innerHTML='<div class="studio-kicker"><span class="onair">Твоя студия</span><span>'+d.streak+' дн. в эфире</span></div>'+
    '<div class="hero"><div class="eyebrow">'+escapeHtml(d.rank.name)+' · '+d.xp+' XP</div><h1>Твой голос.<br>Точный эфир.</h1><p class="lead">Русский без случайных ответов. Выбирай рубрику — и выходи в эфир.</p>'+waveform()+'</div>'+
    '<div class="daily-panel"><div class="progress-top"><span>'+escapeHtml(examText(d.exam))+'</span><b>'+Math.min(d.today.unique_count,d.goal)+' / '+d.goal+'</b></div>'+
    '<div class="progress-track"><i style="width:'+Math.min(100,100*d.today.unique_count/d.goal)+'%"></i></div><p class="footnote">'+(d.today.unique_count>=d.goal?'Дневная цель выполнена. Отличный эфир!':'Сегодня в программе: '+Math.max(0,d.goal-d.today.unique_count)+' новых вопросов до цели.')+'</p></div>'+
    '<div class="stats"><div class="stat"><b>'+home.stats.learned+'</b><span>слов освоено</span></div><div class="stat"><b>'+d.due+'</b><span>пора повторить</span></div><div class="stat"><b>'+d.total.studied+'</b><span>верных заданий</span></div></div>'+
    '<section class="program-section"><div class="eyebrow">Слово сегодняшнего эфира</div>'+
    actionCard(d.archive.some(x=>x.day===new Date().toISOString().slice(0,10))?'Слово дня уже в эфире':'Одно слово на сегодня','Верное ударение и маленький шаг к привычке','data-mode="word"','◉')+'</section>'+
    '<section class="program-section"><div class="eyebrow">Основные эфиры</div>'+
    actionCard(round?'Продолжить выпуск':'Эфир: ударения','10 слов · без спешки','id="classicStart"','●')+
    actionCard('Тренировка ЕГЭ','Ударения · задание 4','id="classicEge"','≡')+
    actionCard('Все рубрики','Паронимы, речь, орфография, пунктуация','id="allChannels"','▦')+'</section>'+
    (d.active.length?'<section class="program-section"><div class="eyebrow">Продолжить эфир</div>'+d.active.map(s=>actionCard(modeNames[s.mode]||s.mode,'Прогресс сохранён','data-resume="'+escapeHtml(s.id)+'"','↺')).join('')+'</section>':'')+
    '<div class="career-strip"><span>'+escapeHtml(d.rank.name)+'</span><span>'+d.xp+(d.rank.next?' / '+d.rank.next:'')+' XP</span></div><div class="progress-track"><i style="width:'+rankProgress+'%"></i></div>';
  $('#classicStart').onclick=()=>{view='classic';round?(result?renderResult():renderCard()):startRound();tg?.BackButton?.show();};
  $('#classicEge').onclick=()=>nav('ege');$('#allChannels').onclick=()=>nav('channels');bindPrograms();
};
function bindPrograms(){
  document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>begin({mode:b.dataset.mode}));
  document.querySelectorAll('[data-resume]').forEach(b=>b.onclick=()=>resumeSession(b.dataset.resume));
}
function renderChannels(){
  const d=home.learning;
  screen.innerHTML='<div class="eyebrow">Сетка вещания</div><h1>Выбери рубрику.</h1><p class="lead">Небольшие выпуски. Понятный разбор. Ошибки вернутся вовремя.</p>'+
    d.categories.map(c=>actionCard(c.title,c.topics.length+' тем · '+c.count+' упражнений','data-category="'+c.id+'"',({paronyms:'🎙',speech:'📺',spelling:'А',punctuation:','})[c.id])).join('')+
    '<section class="program-section"><div class="eyebrow">Специальные программы</div>'+
    actionCard('Экстренный выпуск','Один выпуск в день · 10 секунд','data-mode="emergency"','!')+
    actionCard('Без права на ошибку','5 вопросов · 3 жизни · рекорд '+d.records.survival,'data-mode="survival"','●')+
    actionCard('Режиссёрский повтор',d.due+' заданий по расписанию','data-mode="review"','↺')+
    actionCard('Телесуфлёр','Быстрые ответы · рекорд '+d.records.teleprompter,'id="teleIntro"','≋')+'</section>';
  document.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>renderCategory(b.dataset.category));
  $('#teleIntro').onclick=renderTeleIntro;bindPrograms();
}
function renderCategory(id){
  const c=home.learning.categories.find(c=>c.id===id);
  screen.innerHTML='<div class="eyebrow">Учебная рубрика</div><h1>'+escapeHtml(c.title)+'</h1><p class="lead">Авторские упражнения по нормативным правилам. Репетиция ЕГЭ использует структуру задания, но не является вариантом ФИПИ.</p>'+
    '<label class="field-label" for="topicSelect">Тема</label><select id="topicSelect" class="wide-input"><option value="">Все темы вперемешку</option>'+c.topics.map(t=>'<option>'+escapeHtml(t)+'</option>').join('')+'</select>'+
    '<button class="primary" id="learnStart">Учебный эфир →</button><button class="secondary" id="examStart">Репетиция ЕГЭ →</button><p class="footnote">В узкой теме выпуск может быть короче пяти вопросов. Новые упражнения добавляются через проверяемый импорт.</p>';
  $('#learnStart').onclick=()=>begin({mode:'practice',category:id,topic:$('#topicSelect').value});
  $('#examStart').onclick=()=>begin({mode:'ege',category:id});
}
function renderTeleIntro(){
  screen.innerHTML='<div class="eyebrow">Быстрый эфир</div><h1>Телесуфлёр.</h1><p class="lead">Десять вопросов. Ответил — сразу дальше. Время продолжает идти, если свернуть приложение.</p><label class="field-label" for="speedSelect">Темп</label><select id="speedSelect" class="wide-input"><option value="beginner">Новичок · 12 секунд</option><option value="host">Ведущий · 8 секунд</option><option value="pro">Профессионал · 5 секунд</option></select><button class="primary" id="teleStart">В эфир →</button>';
  $('#teleStart').onclick=()=>begin({mode:'teleprompter',level:$('#speedSelect').value});
}
async function begin(payload){
  stopTimers();lastPayload=payload;submitting=false;feedback=null;
  try{
    session=await api('/api/learning/start',payload);
    localStorage.setItem('udarnik-session',session.id);
    view='learning';tg?.BackButton?.show();renderLearning();
  }catch(e){showLearningError(e);}
}
async function resumeSession(id){
  stopTimers();submitting=false;feedback=null;
  try{session=await api('/api/learning/session',{session_id:id});lastPayload={mode:session.mode,category:session.category,level:session.level};view='learning';tg?.BackButton?.show();renderLearning();}catch(e){showLearningError(e);}
}
function showLearningError(e){
  stopTimers();
  screen.innerHTML='<div class="error">'+escapeHtml(e.message)+'</div><button class="secondary" id="returnStudio">В студию</button>';
  $('#returnStudio').onclick=load;
}
function questionMarkup(q,readonly=false,answer=null){
  if(q.type==='stress'){
    if(readonly){
      const index=[...String(answer)].findIndex(c=>c===c.toUpperCase()&&VOWELS.includes(c.toLowerCase()));
      return letterBoard(q.prompt,{stressIndex:index});
    }
    return letterBoard(q.prompt,{interactive:true});
  }
  if(q.type==='commas'){
    const correct=new Set(Array.isArray(answer)?answer:[]);
    return '<div class="comma-sentence">'+q.tokens.map((word,i)=>'<span class="sentence-token">'+escapeHtml(word)+'</span>'+
      (i<q.tokens.length-1?'<button class="comma-slot '+(readonly?(correct.has(i+1)?'comma-correct':'')+(selectedCommas.has(i+1)&&!correct.has(i+1)?' comma-wrong':''):selectedCommas.has(i+1)?'selected':'')+'" data-comma="'+(i+1)+'" aria-label="Запятая после слова '+escapeHtml(word)+'" aria-pressed="'+selectedCommas.has(i+1)+'" '+(readonly?'disabled':'')+'>'+(readonly?(correct.has(i+1)?',':selectedCommas.has(i+1)?'×':'·'):selectedCommas.has(i+1)?',':'·')+'</button>':'')).join('')+'</div>';
  }
  if(readonly)return '<div class="answer-reveal">'+escapeHtml(Array.isArray(answer)?answer.join(', '):answer)+'</div>';
  if(q.type==='choice')return '<div class="answer-options">'+q.options.map((o,i)=>'<button class="answer-option" data-choice="'+i+'">'+escapeHtml(o)+'</button>').join('')+'</div>';
  if(q.type==='numbers')return '<div class="answer-options">'+q.options.map((o,i)=>'<label class="number-option"><input type="checkbox" value="'+(i+1)+'"><span><b>'+(i+1)+')</b> '+escapeHtml(o)+'</span></label>').join('')+'</div><button class="primary" id="checkLearning">Проверить ответ</button>';
  return '<form id="answerForm"><label class="field-label" for="typedAnswer">Исправленное слово</label><input class="wide-input" id="typedAnswer" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="250" required><button class="primary">Проверить ответ</button></form>';
}
function renderLearning(){
  stopTimers();
  if(session.finished){renderLearningSummary();return;}
  const q=session.question;
  selectedCommas=new Set();submitting=false;
  timerOffset=Date.parse(session.server_now)-Date.now();
  screen.innerHTML='<div class="progress-top"><span class="live-label">LIVE <time id="airClock"></time></span><span>'+session.position+' / '+session.total+'</span></div>'+
    '<div class="progress-track"><i style="width:'+100*(session.position-1)/session.total+'%"></i></div>'+
    '<div class="studio-kicker"><span class="eyebrow">'+escapeHtml(modeNames[session.mode])+'</span><span>'+(session.mode==='survival'?'♥ '.repeat(session.lives):'')+'</span></div>'+
    (session.deadline?'<div class="countdown" role="timer" id="countdown"></div>':'')+
    '<div class="learning-card"><p class="footnote">'+escapeHtml(q.topic)+(q.exam_number?' · ЕГЭ '+q.exam_number:' · учебное упражнение')+'</p>'+
    (q.type==='stress'?'':q.type==='commas'?'<h2>Поставь запятые.</h2>':'<div class="question-title multiline">'+escapeHtml(q.prompt)+'</div>')+
    questionMarkup(q)+(q.note?'<p class="word-note">'+escapeHtml(q.note)+'</p>':'')+
    (q.type==='commas'?'<p class="footnote">Нажми между словами. Каждая точка — место для запятой.</p><button class="primary" id="checkLearning">Проверить запятые</button>':'')+'</div><div id="requestError" role="alert"></div>'+
    '<button class="small-link" id="leaveSession">Сохранить и выйти в студию</button>';
  document.querySelectorAll('[data-choice]').forEach(b=>b.onclick=()=>submitLearning(q.options[Number(b.dataset.choice)]));
  document.querySelectorAll('.letter-board button').forEach(b=>b.onclick=()=>submitLearning(Number(b.dataset.index)));
  document.querySelectorAll('[data-comma]').forEach(b=>b.onclick=()=>{const n=Number(b.dataset.comma);selectedCommas.has(n)?selectedCommas.delete(n):selectedCommas.add(n);b.setAttribute('aria-pressed',selectedCommas.has(n));b.classList.toggle('selected',selectedCommas.has(n));b.textContent=selectedCommas.has(n)?',':'·';});
  if($('#checkLearning'))$('#checkLearning').onclick=()=>submitLearning(q.type==='commas'?[...selectedCommas]:[...document.querySelectorAll('.number-option input:checked')].map(n=>Number(n.value)));
  if($('#answerForm'))$('#answerForm').onsubmit=e=>{e.preventDefault();submitLearning($('#typedAnswer').value);};
  $('#leaveSession').onclick=load;
  const update=()=>{
    if(view!=='learning'||submitting)return;
    const clock=$('#airClock');
    if(clock){const elapsed=Math.max(0,Math.floor((Date.now()+timerOffset-Date.parse(session.started_at))/1000));clock.textContent=Math.floor(elapsed/60)+':'+String(elapsed%60).padStart(2,'0');}
    if(session.deadline){
      const remain=Math.max(0,Date.parse(session.deadline)-Date.now()-timerOffset);
      const label=$('#countdown');if(label)label.textContent=Math.ceil(remain/1000)+' сек.';
      if(!remain)submitLearning(null,true);
    }
  };
  ticking=setInterval(update,200);update();channelTransition();
}
async function submitLearning(value,timeout=false){
  if(submitting||view!=='learning')return;
  submitting=true;stopTimers();
  document.querySelectorAll('.learning-card button,.learning-card input').forEach(b=>b.disabled=true);
  const previousRank=home.learning.rank.level;
  answeredQuestion=session.question;
  try{
    const r=await api('/api/learning/answer',{session_id:session.id,position:session.position,answer:value,timeout});
    session=r.session;feedback=r.feedback;
    const fresh=await api('/api/home');home=fresh;
    feedback.rankUp=home.learning.rank.level>previousRank;
    buzz(feedback.correct?'light':'medium');
    if(view!=='learning')return;
    if(session.mode==='teleprompter'){
      if(session.finished)renderLearningSummary();
      else{renderLearning();showToast(feedback.correct?'✓ '+feedback.answer+' · +'+feedback.xp+' XP':'Верно: '+feedback.answer);}
    }else renderLearningFeedback();
  }catch(e){
    submitting=false;
    if(view!=='learning')return;
    const box=$('#requestError');if(box)box.innerHTML='<p class="incorrect">'+escapeHtml(e.message)+'</p><button class="secondary" id="restoreSession">Восстановить эфир</button>';
    if($('#restoreSession'))$('#restoreSession').onclick=()=>resumeSession(session.id);
  }
}
function showToast(message){
  document.querySelector('.studio-toast')?.remove();
  const toast=document.createElement('div');toast.className='studio-toast';toast.textContent=message;toast.setAttribute('role','status');document.body.append(toast);
  setTimeout(()=>toast.remove(),3500);
}
function completedSpelling(q,answer){
  const word=q.prompt.includes(': ')?q.prompt.split(': ').slice(1).join(': '):q.prompt;
  return String(answer).length<=2&&word.includes('…')?word.replace('…',answer):String(answer);
}
function renderLearningFeedback(){
  stopTimers();const r=feedback,q=answeredQuestion;
  screen.innerHTML='<div class="eyebrow">'+(r.expired?'Время вышло':r.correct?'Слово в эфире':'Редакторская правка')+'</div>'+
    '<div class="learning-card '+(r.correct?'answer-good':'answer-bad')+'"><div class="feedback-symbol">'+(r.correct?'✓':'↺')+'</div>'+
    '<div class="xp-float">+'+r.xp+' XP</div>'+questionMarkup(q,true,r.answer)+
    '<p class="lead">'+escapeHtml(r.explanation)+'</p>'+
    (q.category==='spelling'&&r.correct?'<span class="letter-appears">'+escapeHtml(completedSpelling(q,r.answer))+'</span>':'')+
    (r.missing?.length?'<p>Пропущены позиции: '+r.missing.join(', ')+'</p>':'')+
    (r.extra?.length?'<p class="incorrect">Лишние позиции: '+r.extra.join(', ')+'</p>':'')+
    '<a class="footnote" href="'+escapeHtml(r.source)+'" target="_blank" rel="noopener">Источник правила / формата ↗</a></div>'+
    r.achievements.map(a=>'<div class="badge-card">★ '+escapeHtml(a.title)+' · +'+a.xp+' XP</div>').join('')+
    (r.rankUp?'<div class="rank-reveal"><div class="eyebrow">Повышение в эфире</div><h2>'+escapeHtml(home.learning.rank.name)+'</h2><p>Новый ранг открыт. Каждый точный ответ продолжает твою карьеру.</p></div>':'')+
    '<button class="primary" id="learningNext">'+(session.finished?'Итоги эфира':'Следующий вопрос →')+'</button>';
  $('#learningNext').onclick=()=>session.finished?renderLearningSummary():renderLearning();
}
function reviewAnswerText(q,value){
  if(value===null)return 'Нет ответа';
  if(value===undefined)return 'Ответ не сохранён';
  if(q.type==='stress'&&Number.isInteger(value)){
    return [...q.prompt].map((letter,i)=>i===value?letter.toUpperCase():letter).join('');
  }
  if(Array.isArray(value)){
    if(q.type==='commas')return q.tokens.map((word,i)=>word+(value.includes(i+1)?',':'')).join(' ');
    return value.length?value.join(', '):'Ни один вариант';
  }
  return String(value);
}
function teleprompterMistakesMarkup(){
  if(session.mode!=='teleprompter')return '';
  const mistakes=session.mistakes||[];
  if(!mistakes.length)return '<section class="program-section"><h2>Без ошибок!</h2><p class="lead">Все ответы верные, время не упущено.</p></section>';
  return '<section class="program-section" aria-label="Разбор ошибок"><h2>Разбор ошибок · '+mistakes.length+'</h2><p class="lead">Не торопись: теперь можно спокойно разобрать каждый ответ.</p>'+mistakes.map(m=>{
    const q=m.question;
    const correct=q.type==='commas'?reviewAnswerText(q,m.answer):Array.isArray(m.answer)?m.answer.join(', '):q.category==='spelling'?completedSpelling(q,m.answer):m.answer;
    return '<article class="mistake-review"><div class="eyebrow">Вопрос '+m.position+' · '+escapeHtml(q.topic)+'</div>'+
      '<p class="question-title multiline">'+escapeHtml(q.prompt)+'</p>'+(q.note?'<p class="word-note">'+escapeHtml(q.note)+'</p>':'')+
      (m.expired?'<p class="incorrect">Время вышло</p>':'')+
      '<p class="review-choice">Твой ответ: <strong>'+escapeHtml(reviewAnswerText(q,m.chosen))+'</strong></p>'+
      '<p class="correct">Правильно: <strong>'+escapeHtml(correct)+'</strong></p>'+
      '<p class="lead">'+escapeHtml(m.explanation)+'</p><a class="footnote" href="'+escapeHtml(m.source)+'" target="_blank" rel="noopener">Источник правила ↗</a></article>';
  }).join('')+'</section>';
}
function renderLearningSummary(){
  stopTimers();localStorage.removeItem('udarnik-session');
  const perfect=session.outcomes.length>=5&&session.correct===session.outcomes.length;
  screen.innerHTML='<div class="eyebrow">OFF AIR · Эфир завершён</div><h1>'+(session.lives===0?'Сигнал прервался.':'Хороший выпуск.')+'</h1>'+
    '<p class="lead">'+(session.lives===0?'Три жизни закончились. Ошибки сохранены для повторения.':'Ответы сохранены. Следующий эфир станет ещё увереннее.')+'</p>'+
    '<div class="stats"><div class="stat"><b>'+session.correct+'/'+session.outcomes.length+'</b><span>верных</span></div><div class="stat"><b>'+session.accuracy+'%</b><span>точность</span></div><div class="stat"><b>+'+session.xp+'</b><span>XP за эфир</span></div></div>'+
    (feedback?.new_record?'<div class="badge-card">★ Новый личный рекорд: '+session.best_chain+' подряд</div>':'')+
    (perfect?'<div class="confetti" aria-hidden="true">'+Array.from({length:12},(_,i)=>'<i style="--n:'+i+'"></i>').join('')+'</div>':'')+
    teleprompterMistakesMarkup()+
    '<button class="primary" id="repeatLearning">Ещё выпуск →</button><button class="secondary" id="backStudio">В студию</button>';
  $('#repeatLearning').onclick=()=>['word','emergency'].includes(session.mode)?load():begin(lastPayload.mode===session.mode?lastPayload:{mode:session.mode,...(['practice','ege'].includes(session.mode)?{category:answeredQuestion?.category||'paronyms'}:{})});
  if(['word','emergency'].includes(session.mode))$('#repeatLearning').textContent='Другие рубрики →';
  if(['word','emergency'].includes(session.mode))$('#repeatLearning').onclick=()=>nav('channels');
  $('#backStudio').onclick=load;
}
function renderCareer(){
  const d=home.learning;const pct=d.rank.next?Math.min(100,100*(d.xp-d.rank.start)/(d.rank.next-d.rank.start)):100;
  screen.innerHTML='<div class="eyebrow">Карьера ведущего · уровень '+d.rank.level+'</div><h1>'+escapeHtml(d.rank.name)+'</h1><div class="career-strip"><b>'+d.xp+' XP</b><span>'+(d.rank.next?'До следующего ранга '+(d.rank.next-d.xp)+' XP':'Вершина карьеры')+'</span></div><div class="progress-track"><i style="width:'+pct+'%"></i></div>'+
    '<div class="stats"><div class="stat"><b>'+d.total.correct+'</b><span>верных ответов</span></div><div class="stat"><b>'+d.streak+'</b><span>дней подряд</span></div><div class="stat"><b>'+d.total.studied+'</b><span>заданий изучено</span></div></div>'+
    '<section class="program-section"><div class="eyebrow">Последние семь дней</div><div class="week-chart">'+d.week.map(w=>'<div><span>'+w.total+'</span><i style="height:'+Math.max(3,Math.min(100,w.total*5))+'px"></i><small>'+escapeHtml(w.day.slice(5))+'</small></div>').join('')+'</div><p class="footnote">Сегодня: '+d.today.correct+' верных из '+d.today.total+'. Цель: '+Math.min(d.today.unique_count,10)+'/10 разных вопросов. Лучший эфир сегодня: '+d.best_today+' подряд.</p></section>'+
    '<section class="program-section"><div class="eyebrow">Рекорды</div><p>Выживание: '+d.records.survival+' · Телесуфлёр: '+d.records.teleprompter+'</p></section>'+
    '<section class="program-section"><div class="eyebrow">Достижения</div>'+d.achievements.map(a=>'<div class="achievement '+(a.earned?'earned':'')+'"><span>'+(a.earned?'★':'☆')+'</span><strong>'+escapeHtml(a.title)+'</strong><small>'+a.xp+' XP</small></div>').join('')+'</section>'+
    '<section class="program-section"><div class="eyebrow">Архив слов дня</div>'+(d.archive.length?d.archive.map(a=>'<div class="summary-item"><strong>'+escapeHtml(a.word)+'</strong><span>'+a.day+' · '+(a.correct?'✓':'повторим')+'</span></div>').join(''):'<p class="lead">Первое слово появится здесь после ответа.</p>')+'</section>';
}
const originalSettings=renderSettings;
renderSettings=function(){originalSettings();screen.insertAdjacentHTML('beforeend','<p class="footnote">Дневная цель — 10 разных вопросов. Правильный ответ приносит 10 XP один раз за задание в день. Сутки и серия занятий считаются по UTC.</p><p class="footnote">Дата ЕГЭ задаётся владельцем приложения через EGE_DATE. Неофициальная дата помечается как целевая.</p>');};
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&view==='learning'&&!submitting&&session&&!session.finished)resumeSession(session.id);});
// Give the original stress screens the same feedback and final statistics.
const classicCard=renderCard,classicResult=renderResult,classicSummary=renderSummary;
let classicAirStart=0;
renderCard=function(){
  stopTimers();view='classic';classicCard();
  if(!classicAirStart)classicAirStart=Date.now();
  const indicator=document.querySelector('.progress-top span');
  if(indicator){indicator.classList.add('live-label');indicator.innerHTML='LIVE <time id="classicClock"></time>';}
  ticking=setInterval(()=>{const clock=$('#classicClock');if(clock){const secs=Math.floor((Date.now()-classicAirStart)/1000);clock.textContent=Math.floor(secs/60)+':'+String(secs%60).padStart(2,'0');}},1000);
};
renderResult=function(){
  stopTimers();classicResult();
  const stage=document.querySelector('.word-stage');
  if(stage){stage.classList.add(result.correct?'answer-good':'answer-bad');stage.insertAdjacentHTML('beforeend','<span class="xp-float">+'+(result.xp||0)+' XP</span>');}
};
renderSummary=function(items){
  stopTimers();classicAirStart=0;classicSummary(items);
  const correct=items.filter(i=>i.correct).length,xp=items.reduce((sum,i)=>sum+(i.xp||0),0);
  screen.insertAdjacentHTML('afterbegin','<div class="eyebrow">OFF AIR · ЭФИР ЗАВЕРШЁН</div><div class="stats"><div class="stat"><b>'+correct+'/'+items.length+'</b><span>верных ответов</span></div><div class="stat"><b>'+Math.round(100*correct/items.length)+'%</b><span>точность</span></div><div class="stat"><b>+'+xp+'</b><span>XP</span></div></div>');
};
const originalAnswerWord=answerWord,originalSendQuiz=sendQuiz,originalQuizResult=renderQuizResult;
answerWord=async function(index){await originalAnswerWord(index);try{home=await api('/api/home');}catch(_){/* The answer remains saved; refresh on next visit. */}};
sendQuiz=async function(){await originalSendQuiz();try{home=await api('/api/home');}catch(_){}};
renderQuizResult=function(){originalQuizResult();screen.insertAdjacentHTML('afterbegin','<div class="xp-float">+'+(quizResult.xp||0)+' XP</div>');};
