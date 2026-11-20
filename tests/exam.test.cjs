const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const nodes=new Map();
function el(key){if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',value:'',checked:false,dataset:{},classList:{add(){},remove(){},toggle(){}},insertAdjacentHTML(where,html){this.innerHTML+=html;},setAttribute(){},remove(){}});return nodes.get(key);}
const selected=new Map(),timers=new Set();let sequence=1;
const context={window:{},document:{querySelector:el,querySelectorAll:s=>selected.get(s)||[],documentElement:{dataset:{}},addEventListener(){},createElement:()=>el('toast'),body:{append(){}}},localStorage:{getItem:()=>null,setItem(){},removeItem(){}},location:{hostname:'localhost'},matchMedia:()=>({matches:false}),fetch:()=>new Promise(()=>{}),setInterval:()=>{const n=sequence++;timers.add(n);return n;},clearInterval:n=>timers.delete(n),setTimeout:()=>sequence++,clearTimeout(){},Date,Set,Map,console};
vm.createContext(context);
for(const name of ['app.js','studio.js','exam.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',name),'utf8'),context);
const bank=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/exam_questions.json'),'utf8'));
const numbers=Array.from({length:18},(_,i)=>({number:i+4,title:'Тема '+(i+4),count:bank.filter(q=>q.number===i+4).length,solved:0,accuracy:null,max_score:i+4===8?2:1,filters:{all:1,unseen:1,mistakes:0,mastered:0},state:'new'}));
const home={numbers,total:0,solved:0,accuracy:null,mistakes:0,active:[],history:[],week:[],strongest:[],weakest:[]};
vm.runInContext('examHome='+JSON.stringify(home)+';renderExamHome()',context);
assert.match(el('#screen').innerHTML,/ЕГЭ · русский язык · 2027/);
assert.equal((el('#examTabBody').innerHTML.match(/class="exam-number-card"/g)||[]).length,18);
for(const tab of ['random','mock']){vm.runInContext('examTab='+JSON.stringify(tab)+';renderExamTab()',context);assert.ok(el('#examTabBody').innerHTML.length>200);}
assert.doesNotMatch(el('#examTabBody').innerHTML,/№27/);assert.match(el('#examTabBody').innerHTML,/18 из 18/);
for(const q of bank){const html=context.examAnswerMarkup(q);if(q.type==='matching')assert.equal((html.match(/data-exam-match=/g)||[]).length,5);if(q.type==='multi')assert.equal((html.match(/data-exam-choice=/g)||[]).length,q.options.length);assert.ok(html.length>100);}
const q=bank.find(q=>q.type==='matching');const optionsHtml=context.examAnswerMarkup(q,'12345');assert.equal((optionsHtml.match(/ selected/g)||[]).length,5);
const session={id:'exam-ui',mode:'mock',label:'Учебный пробный вариант части 1',position:0,revision:1,questions:[{...q,draft:'12345',result:null}],answered:[],total:1,finished:false,deadline:null,server_now:new Date().toISOString(),reveal:'end',max_points:2};
vm.runInContext('examSession='+JSON.stringify(session)+';view="exam";renderExamSession()',context);
assert.match(el('#screen').innerHTML,/Сохранить черновик/);assert.doesNotMatch(el('#screen').innerHTML,/Правильно:/);
const final={...session,finished:true,correct:0,points:1,xp:0,questions:[{...q,result:{chosen:'12346',answer:'12345',score:1,max_score:2,correct:false,xp:0,explanation:'Разбор соответствия',source:'Авторское задание',source_url:'https://fipi.ru'}}]};
vm.runInContext('examSession='+JSON.stringify(final)+';renderExamSummary()',context);
assert.match(el('#screen').innerHTML,/1\/2/);assert.match(el('#screen').innerHTML,/12346/);assert.match(el('#screen').innerHTML,/12345/);assert.match(el('#screen').innerHTML,/Разбор соответствия/);
const unsafe={...q,result:{...final.questions[0].result,chosen:'<script>bad()</script>'}};
assert.doesNotMatch(context.examFeedbackMarkup(unsafe),/<script>/);assert.match(context.examFeedbackMarkup(unsafe),/&lt;script&gt;/);
// Serialize two saves: each request must use the revision returned by its predecessor.
context.requests=[];context.next=0;
context.sessionFixture={...session,mode:'numbers',questions:[{...bank.find(q=>q.type==='text'),draft:'',result:null}]};
selected.set('[data-exam-choice]:checked',[]);el('#examTyped').value='первый';
vm.runInContext('examSession=sessionFixture;view="exam";api=async(path,payload)=>{requests.push(payload);return {...sessionFixture,revision:payload.revision+1}}',context);
(async()=>{
 const first=context.examAction('save');el('#examTyped').value='второй';const second=context.examAction('save');await Promise.all([first,second]);
 assert.equal(context.requests[0].revision,1);assert.equal(context.requests[1].revision,2);
 assert.equal(context.requests[0].answer,'первый');assert.equal(context.requests[1].answer,'второй');
 console.log('Exam UI checks passed: tabs, 18 numbers, text-free forms, matching, hidden answers, results, serialized autosaves');
})().catch(e=>{console.error(e);process.exitCode=1;});
