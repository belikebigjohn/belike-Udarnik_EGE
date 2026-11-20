const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const nodes=new Map();
function node(key){if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',value:'',dataset:{},classList:{add(){},remove(){},toggle(){}},insertAdjacentHTML(where,html){this.innerHTML+=html;},setAttribute(){},remove(){}});return nodes.get(key);}
const timers=new Set();let nextTimer=1;
const context={window:{},document:{querySelector:node,querySelectorAll:()=>[],documentElement:{dataset:{}},addEventListener(){},createElement:()=>node('toast'),body:{append(){}}},
 localStorage:{getItem:()=>null,setItem(){},removeItem(){}},location:{hostname:'localhost'},matchMedia:()=>({matches:false}),
 fetch:()=>new Promise(()=>{}),setInterval:()=>{const n=nextTimer++;timers.add(n);return n;},clearInterval:n=>timers.delete(n),setTimeout:()=>nextTimer++,clearTimeout(){},Date,Set,Map,console};
vm.createContext(context);
for(const f of ['app.js','studio.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',f),'utf8'),context);
const d={xp:160,rank:{name:'Корреспондент',level:2,start:100,next:300},today:{unique_count:3,correct:3,total:4},total:{studied:3,correct:3,total:4},streak:1,due:2,goal:10,best_today:3,records:{survival:2,teleprompter:3},daily:{},archive:[],active:[],exam:null,week:[{day:'2026-11-20',total:4,correct:3}],achievements:[{id:'first',title:'Первый эфир',xp:20,earned:true}],categories:['paronyms','speech','spelling','punctuation'].map(id=>({id,title:id,count:5,topics:['Тест']}))};
vm.runInContext('home='+JSON.stringify({learning:d,stats:{learned:2},word_count:220,reminders:false,source:{year:2026,url:'https://fipi.ru'}})+'; round=null;renderHome()',context);
assert.match(node('#screen').innerHTML,/Твой голос/);
assert.match(node('#screen').innerHTML,/Слово сегодняшнего эфира/);
const studioHtml=node('#screen').innerHTML;
assert.match(studioHtml,/ты ведущий в прямом эфире/);
assert.ok(studioHtml.indexOf('верных заданий')<studioHtml.indexOf('Основные эфиры'));
assert.ok(studioHtml.indexOf('Основные эфиры')<studioHtml.indexOf('Слово сегодняшнего эфира'));
context.beginExam=payload=>JSON.parse(JSON.stringify(payload));
for(const [id,numbers] of [['mainParonyms',[5]],['mainGrammar',[6,7,8]],['mainSpelling',[9,10,11,12,13,14,15]],['mainPunctuation',[16,17,18,19,20,21]]]){
 assert.match(studioHtml,new RegExp('id="'+id+'"'));
 assert.deepEqual(node('#'+id).onclick(),{mode:'numbers',numbers,count:5});
}
for(const name of ['channels','career','ege','settings','home']){context.nav(name);assert.ok(node('#screen').innerHTML.length>100);}
for(const c of d.categories){context.renderCategory(c.id);assert.match(node('#screen').innerHTML,/Учебный эфир/);assert.match(node('#screen').innerHTML,/Репетиция ЕГЭ/);}
context.renderTeleIntro();assert.match(node('#screen').innerHTML,/12 секунд/);
const questions=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/questions.json'),'utf8').replace(/^\uFEFF/,''));
for(const q of questions){
 const markup=context.questionMarkup(q,false);
 if(q.type==='commas')assert.equal((markup.match(/data-comma=/g)||[]).length,q.tokens.length-1);
 if(q.type==='choice')assert.equal((markup.match(/data-choice=/g)||[]).length,q.options.length);
 assert.ok(context.questionMarkup(q,true,q.answer).length>0);
}
const s={id:'test',mode:'practice',position:1,total:5,lives:3,finished:false,question:questions[0],started_at:new Date().toISOString(),server_now:new Date().toISOString(),deadline:null};
vm.runInContext('session='+JSON.stringify(s)+';view="learning";renderLearning()',context);
assert.equal(timers.size,1);
context.nav('home');assert.equal(timers.size,0);
vm.runInContext('session='+JSON.stringify({...s,finished:true,outcomes:[{correct:true}],correct:1,accuracy:100,xp:10})+';renderLearningSummary()',context);
assert.match(node('#screen').innerHTML,/OFF AIR/);
assert.match(node('#screen').innerHTML,/100%/);
assert.match(node('#screen').innerHTML,/\+10/);
console.log('Studio UI checks passed: navigation, categories, 52 question renderers, timers, summary');
const reviewQuestion=questions.find(q=>q.id==='p1');
const mistakes=[{position:1,question:reviewQuestion,answer:'надеть',chosen:'одеть',expired:false,explanation:'Надеть что, одеть кого.',source:'https://gramota.ru/'},
 {position:3,question:reviewQuestion,answer:'надеть',chosen:null,expired:true,explanation:'Проверь ударение и форму.',source:'https://gramota.ru/'}];
const finalSession={...s,mode:'teleprompter',finished:true,outcomes:[{correct:false},{correct:true},{correct:false}],correct:1,accuracy:33,xp:10,mistakes};
vm.runInContext('session='+JSON.stringify(finalSession)+';renderLearningSummary()',context);
assert.match(node('#screen').innerHTML,/Разбор ошибок · 2/);
assert.equal((node('#screen').innerHTML.match(/class="mistake-review"/g)||[]).length,2);
assert.match(node('#screen').innerHTML,/Твой ответ: <strong>одеть/);
assert.match(node('#screen').innerHTML,/Правильно: <strong>надеть/);
assert.match(node('#screen').innerHTML,/Время вышло/);
assert.match(node('#screen').innerHTML,/Нет ответа/);
assert.equal(context.reviewAnswerText({type:'stress',prompt:'бананы'},3),'банАны');
assert.equal(context.reviewAnswerText(reviewQuestion,undefined),'Ответ не сохранён');
assert.equal(context.reviewAnswerText({type:'commas',tokens:['Эфир','закончен']},[1]),'Эфир, закончен');
vm.runInContext('session='+JSON.stringify({...finalSession,mistakes:[]})+';renderLearningSummary()',context);
assert.match(node('#screen').innerHTML,/Без ошибок!/);
assert.doesNotMatch(node('#screen').innerHTML,/class="mistake-review"/);
const unsafe={...mistakes[0],chosen:'<img src=x onerror=alert(1)>'};
vm.runInContext('session='+JSON.stringify({...finalSession,mistakes:[unsafe]})+';renderLearningSummary()',context);
assert.match(node('#screen').innerHTML,/&lt;img/);
assert.doesNotMatch(node('#screen').innerHTML,/<img/);
(async()=>{
  context.testFinal=finalSession;context.testHome={learning:d};
  vm.runInContext('session='+JSON.stringify({...s,mode:'teleprompter'})+';view="learning";submitting=false;api=async(path)=>path==="/api/home"?testHome:{session:testFinal,feedback:{correct:false,answer:"надеть",xp:0,achievements:[]}}',context);
  await context.submitLearning('одеть');
  assert.match(node('#screen').innerHTML,/OFF AIR/);
  assert.match(node('#screen').innerHTML,/Разбор ошибок · 2/);
  assert.doesNotMatch(node('#screen').innerHTML,/id="learningNext"/);
  assert.equal(timers.size,0);
  console.log('Teleprompter review checks passed: full list, timeout, empty state, escaping, automatic final screen');
})().catch(e=>{console.error(e);process.exitCode=1;});
