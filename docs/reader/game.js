/* ---------- 对局：押注 → 热身 → 阅读 → 对决 → 改写 ----------
   局包放在 S.doc.rounds（随同步走）。每一局的进度存在 round.st 里。
   依赖 index.html 里的全局函数：$, esc, fmt, toast, uid, dput, sheet, claude, goPage, setBack, closeSheet, locLabel, S */

const GKIND={read:'阅读局',testimony:'证词局',expedition:'远征局',boss:'Boss 战'};
let GCUR=null,GSCROLL=null;

function gRounds(){return (S.doc&&S.doc.rounds||[]).slice().sort((a,b)=>(a.no||0)-(b.no||0))}
function gSave(){return dput('docs',S.doc)}
function gNow(r){return r.st=r.st||{}}

/* 字级别的差异：把改写前后的立场并排标出来 */
function gDiff(a,b){
  a=[...(a||'')];b=[...(b||'')];const n=a.length,m=b.length;
  if(n*m>400000)return {a:esc(a.join('')),b:esc(b.join(''))};
  const L=Array.from({length:n+1},()=>new Uint16Array(m+1));
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)L[i][j]=a[i]===b[j]?L[i+1][j+1]+1:Math.max(L[i+1][j],L[i][j+1]);
  let i=0,j=0,oa='',ob='';const del=c=>`<del>${esc(c)}</del>`,ins=c=>`<ins>${esc(c)}</ins>`;
  while(i<n&&j<m){if(a[i]===b[j]){oa+=esc(a[i]);ob+=esc(b[j]);i++;j++}else if(L[i+1][j]>=L[i][j+1]){oa+=del(a[i++])}else{ob+=ins(b[j++])}}
  while(i<n)oa+=del(a[i++]);while(j<m)ob+=ins(b[j++]);
  return {a:oa.replace(/<\/del><del>/g,''),b:ob.replace(/<\/ins><ins>/g,'')}}

/* 本局页码范围内，你自己的划线和批注 = 证据 */
function gEvidence(r){
  const [f,t]=r.pages||[0,1e9];
  return S.notes.filter(n=>{const p=n.page||((n.sec!=null)?n.sec+1:0);return p>=f&&p<=t})
    .sort((x,y)=>(x.page||0)-(y.page||0))}

function gSys(r,mode){
  const st=gNow(r);const ev=gEvidence(r);
  const evTxt=ev.length?ev.map(n=>`[${locLabel(n)}]「${(n.quote||'').slice(0,300)}」${n.text?' — 批注：'+n.text:''}`).join('\n'):'（这一局还没有划线）';
  const cp=(r.checkpoints||[]).map((c,i)=>`p.${c.page} 问：${c.q}\n答：${(st.cp||{})[i]||'（没答）'}`).join('\n');
  const base=`你是牛津导师制里的导师，也是阅读游戏的对手和裁判。学生在读《${S.doc.name}》，这是第 ${r.no} 局「${r.title}」（${GKIND[r.kind]||'阅读局'}）。
本局问题：${r.question}
学生开局押注的立场：${st.bet?st.bet.text+`（把握 ${st.bet.conf}%）`:'（还没押注）'}
学生在阅读中回答的"为什么"：\n${cp||'（无）'}
学生的划线与批注（本局证据，只能用这些和他已解锁的卡）：\n${evTxt}
${r.hand?'学生已解锁的卡：'+r.hand.join('、'):''}
${r.facts?'裁判掌握的原文事实（用来核对他的说法，不要整段透露）：\n'+r.facts:''}
${r.planted?'注意：局包的地图里故意埋了一处错误：'+r.planted+'。如果学生指出，明确确认并说明原文是什么；不要主动透露。':''}
规则：只用学生已经读过、已经解锁的材料判断，不要拿他还没读的东西指责他没用。区分"原文说了什么"和"学生的判断"。用中文，德语原文保留德语。`;
  if(mode==='duel')return base+`
你现在发起攻击并和他来回辩论，不限轮数。第一条消息直接给出攻击（参考：${r.attack||'针对他的押注找最强的反方论证'}）。之后每次：先判断他刚才的回击哪里站住、哪里没站住（引用他的原话和页码），再追问一个点，以一个具体问题结尾。反馈要详细，但一次只推进一到两个点。不要替他写论点。${r.traps?'\n常见陷阱：'+r.traps:''}`;
  return base+`
现在做本局判定。学生改写后的立场：${st.revised?st.revised.text+`（把握 ${st.revised.conf}%）`:'（没改写）'}
判定的重点是"立场改得好不好"，不是输赢：
- 改得更精确、更有证据支撑 → 好；
- 坚持原立场但顶住了最强攻击 → 也好；
- 读错原文 → 生成一张锈卡（写清误读是什么、怎样修正）；
- 他抓到了局包或你的错误 → 记"核查卡"。
${r.rubric?'评分要点：\n'+r.rubric:''}
${r.cards?'可能掉落的卡（可调整）：\n'+r.cards:''}
输出格式：
**判定**：一句话
**立场变化**：前后对比，哪里变精确了、哪里还松
**做得好的**／**要改的**：各 2–3 条，带原话和页码
**掉落**：卡名 · 阵营 · 稀有度（铁矿石/生铁/钢）· 效果 · 依据的原文和页码
**下一局可以带着的问题**：一个`}

async function gameSheet(id){
  const rs=gRounds();
  if(!rs.length){sideSheet('对局',`<p class="muted" style="font-size:14px">这本书还没有对局包。对局包会随同步出现在这里，也可以在“研究”里导入学习包。</p>`);return}
  const r=rs.find(x=>x.id===(id||GCUR))||rs.find(x=>!(x.st&&x.st.verdict))||rs[rs.length-1];GCUR=r.id;const st=gNow(r);
  const step=!st.bet?1:!st.recallDone&&(r.recall||[]).length?2:!st.readDone?3:!(st.chat||[]).length?4:5;
  const pill=(n,t)=>`<span class="gstep ${step===n?'on':step>n?'ok':''}" data-go="${n}" style="cursor:pointer">${step>n?'✓':n} ${t}</span>`;
  const conf=(id,v)=>`<div class="gconf"><input type="range" id="${id}" min="0" max="100" step="5" value="${v??60}"><b id="${id}V">${v??60}%</b></div>`;
  const ev=gEvidence(r);
  const recall=(r.recall||[]).map((q,i)=>{const a=(st.recall||[])[i]||{};return `<div class="gq"><div>${i+1}. ${esc(q.q)}</div>
      <textarea data-rc="${i}" style="min-height:44px" placeholder="先凭记忆写，不看笔记" ${a.shown?'disabled':''}>${esc(a.a||'')}</textarea>
      ${a.shown?`<div class="gans">参考：${esc(q.a)}　${a.ok==null?`<button class="btn sm" data-ok="${i}|1">✓ 想起来了</button><button class="btn sm" data-ok="${i}|0">✗ 没想起</button>`:(a.ok?'✓ 想起来了':'✗ 没想起')}</div>`:`<button class="btn sm" data-show="${i}">看参考</button>`}</div>`}).join('');
  const cps=(r.checkpoints||[]).map((c,i)=>`<div class="gq"><a class="pl" data-p="${c.page}" href="#">p.${c.page} ↗</a> ${esc(c.q)}
      <div class="row"><input data-cp="${i}" value="${esc((st.cp||{})[i]||'')}" placeholder="一行就够"><button class="btn sm" data-cps="${i}">保存</button></div></div>`).join('');
  const chat=st.chat||[];
  const d=st.bet&&st.revised?gDiff(st.bet.text,st.revised.text):null;
  sideSheet('对局',`
    <div class="chips" id="gR">${rs.map(x=>`<button class="chip ${x.id===r.id?'on':''}" data-r="${x.id}">局 ${x.no}${x.st&&x.st.verdict?' ✓':''}</button>`).join('')}<button class="chip" id="gLog">立场日志</button></div>
    <div class="qhead"><b>局 ${r.no} · ${esc(r.title)}</b>　<span class="muted">${GKIND[r.kind]||''}${r.pages?` · p.${r.pages[0]}–${r.pages[1]}`:''}</span><br>${esc(r.question)}</div>
    <div class="gsteps">${pill(1,'押注')}${(r.recall||[]).length?pill(2,'热身'):''}${pill(3,'阅读')}${pill(4,'对决')}${pill(5,'改写')}</div>

    <div class="lbl" id="gS1">① 押注：读之前，你现在的立场</div>
    ${st.bet?`<div class="gbet">${esc(st.bet.text)}<span class="muted">　把握 ${st.bet.conf}%</span></div>`:
      `<textarea id="gBet" style="min-height:56px" placeholder="一句话。押了就不能改，读完再改写">${esc((st.drafts||{}).bet||'')}</textarea>${conf('gBetC')}<div class="row"><button class="btn pri" id="gBetGo">押注</button></div>`}

    ${(r.recall||[]).length&&st.bet?`<div class="lbl" id="gS2">② 热身：凭记忆回答</div>${recall}${!st.recallDone?`<div class="row"><button class="btn" id="gRcDone">热身完成</button></div>`:''}`:''}

    ${st.bet&&(st.recallDone||!(r.recall||[]).length)?`
    <div class="lbl" id="gS3">③ 阅读</div>
    ${r.map?`<div class="guide">${fmt(r.map)}</div>`:''}
    ${cps?`<div class="muted" style="font-size:13px;margin:6px 0">每读完一处，回答一行“为什么”：</div>${cps}`:''}
    <div class="lbl">证据：本局范围内你的划线（${ev.length}）</div>
    ${ev.length?ev.map(n=>`<div class="gev"><a class="pl" data-p="${n.page||((n.sec??0)+1)}" href="#">${esc(locLabel(n))}</a> 「${esc((n.quote||'').slice(0,160))}」${n.text?`<div class="muted">${esc(n.text)}</div>`:''}</div>`).join(''):'<p class="muted" style="font-size:13.5px">在正文里选中文字点“划线”，就会出现在这里。不用另外抄。</p>'}
    <div class="lbl">查错：局包或 AI 说错的地方</div>
    ${(st.catches||[]).map(c=>`<div class="gev">🔍 ${esc(c.text)}</div>`).join('')}
    <div class="row"><input id="gCatch" value="${esc((st.drafts||{}).catch||'')}" placeholder="例：地图说 p.41 讲的是……，其实原文是……"><button class="btn sm" id="gCatchGo">记下</button></div>
    ${!st.readDone?`<div class="row"><button class="btn pri" id="gReadDone">读完了，进入对决</button></div>`:''}`:''}

    ${st.readDone?`
    <div class="lbl" id="gS4">④ 对决（不限时、不限句数）</div>
    <div id="gc">${chat.map(m=>`<div class="msg ${m.role==='user'?'u':'a'}">${fmt(m.content)}</div>`).join('')}</div>
    ${chat.length?`<textarea id="gIn" placeholder="回击。可以贴原文、写页码">${esc((st.drafts||{}).duel||'')}</textarea><div class="row"><button class="btn pri" id="gGo">发送</button></div>`:`<div class="row"><button class="btn pri" id="gStart">开始对决</button></div>`}`:''}

    ${chat.length>=2?`
    <div class="lbl" id="gS5">⑤ 改写：现在的立场</div>
    ${st.revised?`<div class="gdiff"><div class="muted" style="font-size:12.5px">押注 · ${st.bet.conf}%</div><div>${d.a}</div><div class="muted" style="font-size:12.5px;margin-top:6px">改写 · ${st.revised.conf}%</div><div>${d.b}</div></div>
      <div class="row"><button class="btn sm" id="gReEdit">再改一次</button>${!st.verdict?'<button class="btn pri sm" id="gJudge">请求判定</button>':''}</div>`:
      `<textarea id="gRev" style="min-height:56px">${esc((st.drafts||{}).rev??st.bet.text)}</textarea>${conf('gRevC',st.bet.conf)}<div class="row"><button class="btn pri" id="gRevGo">提交改写</button></div>`}
    ${st.verdict?`<div class="lbl">判定</div><div class="guide">${fmt(st.verdict)}</div>`:''}`:''}
  `);
  const sb=$('#shB');
  {const keep=GSCROLL&&GSCROLL.id===r.id&&GSCROLL.step===step;const tgt=$('#gS'+step);
   if(keep)sb.scrollTop=GSCROLL.top;else if(tgt&&step>1)tgt.scrollIntoView({block:'start'});
   GSCROLL={id:r.id,step,top:sb.scrollTop};sb.onscroll=()=>{GSCROLL.top=sb.scrollTop}}
  const RR=()=>gRounds().find(y=>y.id===r.id)||r,ST=()=>gNow(RR());
  const bindConf=id=>{const x=$('#'+id);if(x)x.oninput=()=>$('#'+id+'V').textContent=x.value+'%'};bindConf('gBetC');bindConf('gRevC');
  sb.onclick=async e=>{
    const pl=e.target.closest('a.pl');if(pl){e.preventDefault();closeSheet();goPage(+pl.dataset.p);setBack('← 回到对局',()=>gameSheet(r.id));return}
    const go=e.target.closest('[data-go]');if(go){const t=$('#gS'+go.dataset.go);if(t)t.scrollIntoView({block:'start',behavior:'smooth'});else toast('这一步还没解锁');return}
    const rb=e.target.closest('[data-r]');if(rb){gameSheet(rb.dataset.r);return}
    if(e.target.id==='gLog'){gLogSheet();return}
    const sh=e.target.closest('[data-show]');if(sh){const i=+sh.dataset.show;ST().recall=ST().recall||[];const ta=sb.querySelector(`[data-rc="${i}"]`);ST().recall[i]={a:ta.value.trim(),shown:true};await gSave();gameSheet(r.id);return}
    const ok=e.target.closest('[data-ok]');if(ok){const [i,v]=ok.dataset.ok.split('|');ST().recall[+i].ok=v==='1';await gSave();gameSheet(r.id);return}
  };
  // 输入即保存（停顿 0.6 秒），另有“保存”按钮；不会因为同步或翻页丢字
  const saveCp=async x=>{const t=ST();t.cp=t.cp||{};t.cp[x.dataset.cp]=x.value.trim();await gSave()};
  let cpT=null;sb.querySelectorAll('[data-cp]').forEach(x=>{x.oninput=()=>{clearTimeout(cpT);cpT=setTimeout(()=>saveCp(x),600)};x.onchange=()=>saveCp(x)});
  sb.querySelectorAll('[data-cps]').forEach(bt=>bt.onclick=async()=>{const x=sb.querySelector(`[data-cp="${bt.dataset.cps}"]`);clearTimeout(cpT);await saveCp(x);bt.textContent='已保存 ✓';setTimeout(()=>bt.textContent='保存',1500)});
  const draft=(id,k)=>{const x=$('#'+id);if(!x)return;let t=null;x.oninput=()=>{clearTimeout(t);t=setTimeout(async()=>{const o=ST();o.drafts=o.drafts||{};o.drafts[k]=x.value;await gSave()},600)}};
  draft('gBet','bet');draft('gCatch','catch');draft('gRev','rev');draft('gIn','duel');
  const on=(id,f)=>{const b=$('#'+id);if(b)b.onclick=f};
  on('gBetGo',async()=>{const t=$('#gBet').value.trim();if(!t){toast('先写一句立场');return}ST().bet={text:t,conf:+$('#gBetC').value,at:Date.now()};if(ST().drafts)delete ST().drafts.bet;await gSave();gameSheet(r.id)});
  on('gRcDone',async()=>{ST().recallDone=true;await gSave();gameSheet(r.id)});
  on('gCatchGo',async()=>{const t=$('#gCatch').value.trim();if(!t)return;ST().catches=ST().catches||[];ST().catches.push({id:uid(),text:t,at:Date.now()});if(ST().drafts)delete ST().drafts.catch;await gSave();gameSheet(r.id);toast('记下了，判定时会核对')});
  on('gReadDone',async()=>{ST().readDone=true;await gSave();gameSheet(r.id)});
  const talk=async q=>{
    ST().chat=ST().chat||[];const box=$('#gc');
    if(q){ST().chat.push({role:'user',content:q});box.insertAdjacentHTML('beforeend',`<div class="msg u">${esc(q)}</div>`)}
    box.insertAdjacentHTML('beforeend','<div class="msg a">…</div>');const out=box.lastElementChild;out.scrollIntoView({block:'nearest'});
    const msgs=ST().chat.length?ST().chat.map(m=>({role:m.role,content:m.content})):[{role:'user',content:'我读完了，请发起攻击。'}];
    if(msgs[0].role!=='user')msgs.unshift({role:'user',content:'我读完了，请发起攻击。'});
    try{const a=await claude({task:'tutor',max:1500,system:gSys(RR(),'duel'),messages:msgs,onText:t=>{out.innerHTML=fmt(t)}});ST().chat.push({role:'assistant',content:a});await gSave();gameSheet(r.id);$('#gIn')&&$('#gIn').focus()}
    catch(err){if(q)ST().chat.pop();out.className='msg e';out.textContent=err.message}};
  on('gStart',()=>talk(''));
  on('gGo',()=>{const q=$('#gIn').value.trim();if(!q)return;$('#gIn').value='';if(ST().drafts)delete ST().drafts.duel;talk(q)});
  on('gRevGo',async()=>{const t=$('#gRev').value.trim();if(!t)return;ST().revised={text:t,conf:+$('#gRevC').value,at:Date.now()};if(ST().drafts)delete ST().drafts.rev;await gSave();gameSheet(r.id)});
  on('gReEdit',async()=>{delete ST().revised;delete ST().verdict;await gSave();gameSheet(r.id)});
  on('gJudge',async()=>{const b=$('#gJudge');b.disabled=true;b.textContent='判定中…';
    const box=document.createElement('div');box.className='guide';sb.append(box);box.scrollIntoView({block:'nearest'});
    const msgs=[...(ST().chat||[]).map(m=>({role:m.role,content:m.content})),{role:'user',content:'请对这一局做判定。'+((ST().catches||[]).length?'\n我记下的查错：\n'+ST().catches.map(c=>'- '+c.text).join('\n'):'')}];
    if(msgs[0].role!=='user')msgs.unshift({role:'user',content:'（对决开始）'});
    try{const v=await claude({task:'tutor',max:1800,system:gSys(RR(),'judge'),messages:msgs,onText:t=>{box.innerHTML=fmt(t)}});ST().verdict=v;ST().done=Date.now();await gSave();gameSheet(r.id)}
    catch(err){box.className='msg e';box.textContent=err.message;b.disabled=false;b.textContent='请求判定'}});
}

function gLogSheet(){
  const rs=gRounds().filter(r=>r.st&&r.st.bet);
  sideSheet('立场日志',`<div class="row" style="margin-bottom:8px"><button class="btn sm" id="gBackG">← 回到对局</button></div>
    ${rs.length?rs.map(r=>{const st=r.st;const d=st.revised?gDiff(st.bet.text,st.revised.text):null;
      return `<div class="note"><b>局 ${r.no} · ${esc(r.title)}</b><div class="muted" style="font-size:12.5px">${new Date(st.bet.at).toLocaleDateString('zh-CN')} · ${esc(r.question)}</div>
        <div class="gdiff"><div class="muted" style="font-size:12.5px">押注 · ${st.bet.conf}%</div><div>${d?d.a:esc(st.bet.text)}</div>
        ${d?`<div class="muted" style="font-size:12.5px;margin-top:6px">改写 · ${st.revised.conf}%</div><div>${d.b}</div>`:'<div class="muted" style="font-size:12.5px;margin-top:6px">还没改写</div>'}</div></div>`}).join(''):'<p class="muted" style="font-size:14px">还没有押注记录。</p>'}`);
  $('#gBackG').onclick=()=>gameSheet()}

$('#bGame').onclick=()=>gameSheet();
