// Duel view (/duelo): only the live video with the board, the recognized cards and the
// duel panel. The diagnostic viewer (/) keeps the analysed frame, OCR and glare tools.
const frame=document.querySelector('#frame'),ctx=frame.getContext('2d');
let currentBitmap=null,frameNumber=0,liveTracks=[],renderedFrame=-1,renderedTracks=null,renderedAR=null;
let playmat=null,calibration=null,zonesVersion=0,renderedZones=-1,virtualPreview=null;
function textNode(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}

// Card sheets (/card-info, local registry): labels under the cards and the "Carta en juego" panel.
const cardSheets=new Map();
function sheetOf(cardId){
  if(!cardId)return null;
  if(!cardSheets.has(cardId)){cardSheets.set(cardId,null);fetch('/card-info?id='+encodeURIComponent(cardId)).then(r=>r.ok?r.json():null).then(s=>{if(s){cardSheets.set(cardId,s);renderedTracks=null;}}).catch(()=>{});}
  return cardSheets.get(cardId);
}
function statsLine(s){
  if(!s)return null;
  if(s.card_type!=='monster')return s.line?.split(' · ')[0]||null;   // "Magia Normal", "Trampa Continua"
  return s.link?`ATK ${s.atk??'?'} · LINK-${s.link}`:`ATK ${s.atk??'?'} / DEF ${s.def??'?'}`;
}


// Minimal marks: only the four corners of a quadrilateral, each as an "L" along its edges.
function cornerMarks(context,quad,fraction){
  context.beginPath();
  for(let i=0;i<4;i++){
    const p=quad[i],prev=quad[(i+3)%4],next=quad[(i+1)%4];
    context.moveTo(p[0]+(prev[0]-p[0])*fraction,p[1]+(prev[1]-p[1])*fraction);context.lineTo(p[0],p[1]);
    context.lineTo(p[0]+(next[0]-p[0])*fraction,p[1]+(next[1]-p[1])*fraction);
  }
  context.stroke();
}

// Only cards inside a field zone of the board count: Monster, Spell & Trap, Field and Extra
// Monster Zones. Graveyard, Deck, Extra Deck, Banished and anything off the board are ignored.
const FIELD_ZONE=/^(monster|spell|extra_monster):|^field$/;
function insideQuad([x,y],q){
  let sign=0;
  for(let i=0;i<4;i++){const [ax,ay]=q[i],[bx,by]=q[(i+1)%4],c=(bx-ax)*(y-ay)-(by-ay)*(x-ax);if(c!==0){if(sign&&Math.sign(c)!==sign)return false;sign=Math.sign(c);}}
  return true;
}
function zoneAt(point){const board=virtualPreview||playmat;return (board?.zones||[]).find(z=>insideQuad(point,z.polygon))?.zone||null;}
function fieldTracks(tracks){
  const board=virtualPreview||playmat;
  if(!board?.zones?.length)return tracks;   // no board yet: show everything while setting up
  return tracks.filter(t=>FIELD_ZONE.test(zoneAt(t.corners.reduce(([a,b],[x,y])=>[a+x/4,b+y/4],[0,0]))||''));
}

function drawCards(context,cards){
  const size=Math.max(11,Math.round(frame.width/125)),small=Math.max(10,Math.round(size*.85));
  for(const card of cards){
    context.save();context.lineWidth=Math.max(3,frame.width/480);context.strokeStyle='#80ffbc';context.lineCap='round';
    cornerMarks(context,card.corners,.18);
    if(card.name){
      // Two short lines under the card (above it stands the AR monster): name, then ATK/DEF or card type.
      const stats=statsLine(sheetOf(card.card_id));
      const cx=card.corners.reduce((s,p)=>s+p[0]/4,0),top=Math.min(frame.height-size*2-8,Math.max(...card.corners.map(p=>p[1]))+4);
      context.textAlign='center';context.font=`600 ${size}px system-ui`;
      const w=Math.max(context.measureText(card.name).width,stats?(context.font=`600 ${small}px system-ui`,context.measureText(stats).width):0)+10;
      context.fillStyle='rgba(10,14,22,.72)';context.fillRect(cx-w/2,top,w,size+(stats?small+8:6));
      context.font=`600 ${size}px system-ui`;context.fillStyle='#e9f6ff';context.fillText(card.name,cx,top+size);
      if(stats){context.font=`600 ${small}px system-ui`;context.fillStyle='#80ffbc';context.fillText(stats,cx,top+size+small+3);}
    }
    context.restore();
  }
}

// "Carta en juego": which card is being played or looked at, and what it does.
let spotlightId=null;
async function spotlight(cardId){
  if(!cardId)return;spotlightId=cardId;
  let s=cardSheets.get(cardId);
  if(!s){try{const r=await fetch('/card-info?id='+encodeURIComponent(cardId));s=r.ok?await r.json():null;if(s)cardSheets.set(cardId,s);}catch(e){}}
  if(!s||spotlightId!==cardId)return;
  const box=document.querySelector('#spotlight');box.hidden=false;
  document.querySelector('#spotImage').src='/card-image?id='+encodeURIComponent(cardId);
  document.querySelector('#spotName').textContent=s.name;
  document.querySelector('#spotEn').textContent=s.name_en&&s.name_en!==s.name?s.name_en:'';
  document.querySelector('#spotLine').textContent=s.line||'';
  document.querySelector('#spotStats').textContent=s.card_type==='monster'?statsLine(s):'';
  document.querySelector('#spotEffect').textContent=s.effect||'';
}
// Click a card on the video to see it.
frame.addEventListener('click',event=>{
  if(calibration)return;
  const rect=frame.getBoundingClientRect(),p=[(event.clientX-rect.left)*frame.width/rect.width,(event.clientY-rect.top)*frame.height/rect.height];
  if(battleClick(p))return;   // Battle Phase: choosing attacker and target
  const hit=fieldTracks(liveTracks).find(t=>insideQuad(p,t.corners));
  if(hit)spotlight(hit.card_id);
});

function draw(now){
  const ar=document.querySelector('#ar').checked;
  // With AR on, monsters breathe and effects play: repaint every display frame.
  if(currentBitmap&&(ar||renderedFrame!==frameNumber||renderedTracks!==liveTracks||renderedZones!==zonesVersion||renderedAR!==ar)){
    if(frame.width!==currentBitmap.width||frame.height!==currentBitmap.height){frame.width=currentBitmap.width;frame.height=currentBitmap.height;zonesVersion++;}
    ctx.drawImage(currentBitmap,0,0);
    drawTableOverlay(ctx);
    const field=fieldTracks(liveTracks);
    if(ar)drawStage(ctx,field.filter(t=>t.stable),now||performance.now());
    drawCards(ctx,field);
    drawBattle(ctx);
    if(ar)drawHud(ctx,now||performance.now());   // effects are queued only with Efectos on (stageEvents)
    renderedFrame=frameNumber;renderedTracks=liveTracks;renderedZones=zonesVersion;renderedAR=ar;
  }
  requestAnimationFrame(draw);
}

// Video: the server's newest frame with the tracks of that exact frame (X-Tracks).
async function refreshCamera(){
  let delay=66;const started=performance.now();
  try{
    const r=await fetch('/snapshot?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(!r.ok)throw Error();
    const bitmap=await createImageBitmap(await r.blob());
    let tracks=[];try{tracks=JSON.parse(r.headers.get('X-Tracks')||'[]');}catch(e){}
    if(currentBitmap)currentBitmap.close();currentBitmap=bitmap;frameNumber++;
    liveTracks=Array.isArray(tracks)?tracks.filter(t=>t.card_id&&t.corners?.length===4):[];
    const onField=fieldTracks(liveTracks).length;
    document.querySelector('#videoStatus').textContent=`${onField} carta${onField===1?'':'s'} en el campo`;
  }catch(e){document.querySelector('#videoStatus').textContent='Sin señal de cámara; reintentando…';delay=1500;}
  finally{setTimeout(refreshCamera,Math.max(30,delay-(performance.now()-started)));}
}

// The server analyses only while some page asks for results: keep asking.
let analysisSequence=-1;
async function followAnalysis(){
  let delay=0;
  try{
    const r=await fetch('/analysis?after='+analysisSequence,{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(r.status===404){delay=5000;return;}   // no server loop (saved capture): nothing to keep alive
    if(r.status===200){const data=await r.json();if(Number.isFinite(data.sequence))analysisSequence=data.sequence;}
  }catch(e){delay=1000;}
  finally{setTimeout(followAnalysis,delay);}
}
document.querySelector('#ar').onchange=()=>{renderedAR=null;};

// ---- Duelo en la mesa: calibración del tapete y panel ------------------------------------
const $d=s=>document.querySelector(s);
const CORNERS=['arriba a la izquierda (lado del rival)','arriba a la derecha (lado del rival)','abajo a la derecha (su lado)','abajo a la izquierda (su lado)'];
const PHASES={draw:'Fase de Robo',standby:'Fase de Espera',main1:'Fase Principal 1',battle:'Fase de Batalla',main2:'Fase Principal 2',end:'Fase Final'};
const POSITIONS={attack:'ataque',defense:'defensa',facedown_defense:'defensa boca abajo',faceup:'boca arriba',facedown:'boca abajo'};
let duelView=null;

const SHORT={field:'Campo',graveyard:'Cementerio',extra_deck:'Mazo Extra',deck:'Mazo',banished:'Desterradas'};
function shortLabel(zone){const [k,i]=zone.split(':');return k==='monster'?`M${+i+1}`:k==='spell'?(i==='0'||i==='4'?`MT${+i+1}·P`:`MT${+i+1}`):k==='extra_monster'?`Monstruo Extra ${+i+1}`:SHORT[zone]||zone;}
function drawTableOverlay(context){
  const board=virtualPreview||playmat;
  if(board&&$d('#showZones')?.checked&&!calibration){
    // Line and text sizes follow the video resolution: the canvas is shown scaled down.
    context.save();context.lineWidth=Math.max(2,frame.width/520);context.lineCap='round';context.font=`600 ${Math.round(frame.width/95)}px system-ui`;context.textAlign='center';
    for(const z of board.zones||[]){
      // Only corner marks, like the printed mat; piles (Graveyard, Deck...) fainter than field zones.
      const field=FIELD_ZONE.test(z.zone),a=field?.7:.35;
      context.strokeStyle=z.player===0?`rgba(255,255,255,${a})`:`rgba(255,224,150,${a})`;
      cornerMarks(context,z.polygon,.22);
      const bottom=z.polygon.reduce((m,p)=>m[1]>p[1]?m:p);const [cx]=z.polygon.reduce(([s],[x])=>[s+x/4],[0]);
      context.fillStyle=`rgba(255,255,255,${a*.7})`;context.fillText(shortLabel(z.zone),cx,bottom[1]-6);
    }
    context.restore();
  }
  if(calibration){
    context.save();context.font='bold 22px system-ui';
    calibration.mats.flat().concat(calibration.points).forEach(([x,y],i)=>{
      context.fillStyle='#ffd166';context.beginPath();context.arc(x,y,9,0,Math.PI*2);context.fill();
      context.fillStyle='#10141d';context.fillText(String(i%4+1),x-6,y+7);
    });
    context.restore();
  }
}

function calibrationStep(){
  if(!calibration){
    const seen=(playmat?.mats||[]).map(m=>`jugador ${m.player+1} (${m.markers} marcadores)`).join(', ');
    $d('#calibrationHelp').textContent=playmat?.mode==='printed'?(seen?`Plantilla impresa: veo ${seen}. Puedes mover la cámara o el tapete.`:'Plantilla impresa: no veo ningún tapete. Deja a la vista al menos 2 de sus 4 marcadores.'):
      playmat?.virtual?`Tablero virtual fijado (${playmat.mode==='two'?'2 jugadores':'1 jugador'}). Si mueves la cámara, vuelve a elegirlo y ajústalo.`:
      playmat?.mode?`Tapetes calibrados (${playmat.modes[playmat.mode]}). Si mueves la cámara, vuelve a calibrar.`:'Sin tablero: elige "Tablero virtual" y ajústalo sobre la mesa.';
    return;}
  const player=calibration.mats.length,who=calibration.mode==='one'?'tu tapete':`el tapete del jugador ${player+1} (${$d('#name'+player).value})`;
  $d('#calibrationHelp').textContent=`Haz clic en ${who}, esquina ${calibration.points.length+1} de 4: ${CORNERS[calibration.points.length]}, como lo ve ese jugador sentado.`;
}

// Virtual board: sliders place it, the server returns the zones (same geometry as the saved board).
const VKEYS=['cx','cy','width','tilt','depth','rotation','gap'];
const VDEFAULT={cx:.5,cy:.55,width:.7,tilt:.75,depth:1,rotation:0,gap:.08};
// Two boards stacked must fit a 16:9 frame: start narrower and centred.
const VSTART={'virtual-two':{...VDEFAULT,width:.42,cy:.5},'virtual-one':VDEFAULT};
function virtualParams(){return Object.fromEntries(VKEYS.map(k=>[k,Number($d('#v-'+k).value)]));}
function setVirtualParams(v){for(const k of VKEYS)$d('#v-'+k).value=String((v||VDEFAULT)[k]??VDEFAULT[k]);}
let previewTimer=0,previewSeq=0;
async function previewVirtual(){
  const mode=$d('#matMode').value;if(!mode.startsWith('virtual-'))return;
  // The canvas takes the video's size with the first frame; before that the board would be off-scale.
  if(!currentBitmap){clearTimeout(previewTimer);previewTimer=setTimeout(previewVirtual,300);return;}
  const seq=++previewSeq;
  try{const r=await fetch('/playmat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview:true,mode:mode.slice(8),virtual:virtualParams(),image_size:[frame.width,frame.height]})});
    const data=await r.json();if(!r.ok)throw Error(data.error||'No se pudo dibujar el tablero');
    if(seq===previewSeq){virtualPreview=data;zonesVersion++;}}
  catch(e){duelMessage(e.message,true);}
}
function showMode(adjust=false){
  const mode=$d('#matMode').value,virtual=mode.startsWith('virtual-');
  const fixed=virtual&&playmat?.virtual&&'virtual-'+playmat.mode===mode;
  const editing=virtual&&(adjust||!fixed);
  $d('#virtualControls').hidden=!editing;$d('#calibrate').hidden=editing;$d('#v-gap-label').hidden=mode!=='virtual-two';
  $d('#calibrate').textContent=virtual?'Ajustar tablero':'Usar este modo';
  if(editing){$d('#boardSettings').open=true;$d('#calibrationHelp').textContent='Ajusta los controles y pulsa "Fijar tablero".';previewVirtual();}
  else{virtualPreview=null;zonesVersion++;calibrationStep();if(playmat?.mode)$d('#boardSettings').open=false;}   // board set: fold its settings away
}
$d('#matMode').onchange=()=>{
  // Switching boards starts from the saved sliders of that board, else from its default size.
  const mode=$d('#matMode').value;
  if(mode.startsWith('virtual-'))setVirtualParams(playmat?.virtual&&'virtual-'+playmat.mode===mode?playmat.virtual:VSTART[mode]);
  showMode(false);
};
setVirtualParams(VSTART['virtual-two']);
for(const k of VKEYS)$d('#v-'+k).oninput=()=>{clearTimeout(previewTimer);previewTimer=setTimeout(previewVirtual,40);};
$d('#fixBoard').onclick=async()=>{
  try{const r=await fetch('/playmat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:$d('#matMode').value.slice(8),virtual:virtualParams(),image_size:[frame.width,frame.height]})});
    const data=await r.json();if(!r.ok)throw Error(data.error||'No se pudo fijar el tablero');
    playmat=data;duelMessage('Tablero fijado. Para moverlo, pulsa "Ajustar tablero".');showMode(false);}
  catch(e){duelMessage(e.message,true);}
};

$d('#calibrate').onclick=async()=>{
  if($d('#matMode').value.startsWith('virtual-')){showMode(true);return;}
  if($d('#matMode').value==='printed'){
    // Printed templates need no clicks: the markers are found on every analysis.
    try{const r=await fetch('/playmat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'printed',mats:[],image_size:[frame.width,frame.height]})});
      const data=await r.json();if(!r.ok)throw Error(data.error||'No se pudo activar');playmat=data;zonesVersion++;duelMessage('Plantilla impresa activada: coloca los tapetes con sus marcadores a la vista.');}
    catch(e){duelMessage(e.message,true);}
    calibrationStep();return;
  }
  calibration={mode:$d('#matMode').value,mats:[],points:[]};$d('#cancelCalibration').hidden=false;zonesVersion++;calibrationStep();frame.style.cursor='crosshair';};
$d('#cancelCalibration').onclick=()=>{calibration=null;$d('#cancelCalibration').hidden=true;frame.style.cursor='';zonesVersion++;calibrationStep();};
frame.addEventListener('click',async event=>{
  if(!calibration)return;
  const rect=frame.getBoundingClientRect();
  calibration.points.push([(event.clientX-rect.left)*frame.width/rect.width,(event.clientY-rect.top)*frame.height/rect.height]);zonesVersion++;
  if(calibration.points.length===4){calibration.mats.push(calibration.points);calibration.points=[];}
  if(calibration.mats.length<(calibration.mode==='one'?1:2)){calibrationStep();return;}
  try{
    const body={mode:calibration.mode,image_size:[frame.width,frame.height],mats:calibration.mats.map((corners,player)=>({player,corners}))};
    const r=await fetch('/playmat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await r.json();if(!r.ok)throw Error(data.error||'No se pudo guardar la calibración');
    playmat=data;duelMessage('Calibración guardada.');
  }catch(e){duelMessage(e.message,true);}
  calibration=null;$d('#cancelCalibration').hidden=true;frame.style.cursor='';zonesVersion++;calibrationStep();
});
$d('#showZones').onchange=()=>{zonesVersion++;};

function duelMessage(text,error=false){const m=$d('#duelMessage');m.textContent=text;m.className=error?'error':'';if(text)$d('#duelSection').hidden=false;}
async function duelAct(event){
  try{
    const r=await fetch('/duel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(event)});
    const data=await r.json();if(!r.ok)throw Error(data.error||'No se pudo registrar');
    duelMessage('');renderDuel(data.duel);
  }catch(e){duelMessage(e.message,true);}
}

function questionNode(q){
  const box=document.createElement('div');box.className='question';
  const who=duelView?.players?.[q.player]?.name||`Jugador ${q.player+1}`,card=q.card_name||'una carta sin identificar';
  const text={unexplained:`Apareció ${card} en la ${q.zone_label} de ${who}. ¿Qué pasó?`,
    missing:`La carta de la ${q.zone_label} de ${who} ya no está. ¿A dónde fue?`,
    moved:`${card} aparece en la ${q.zone_label} de ${who}, pero estaba en otra zona.`,
    different_copy:`En la ${q.zone_label} de ${who} hay otra carta distinta de la registrada.`,
    conflict:`${card} en la ${q.zone_label} de ${who}: la cámara ve ${POSITIONS[q.position]||q.position}, el duelo tiene ${POSITIONS[q.expected_position]||q.expected_position}.`}[q.kind]||`${q.zone_label}: ${q.kind}`;
  box.append(textNode('p',text));
  if(q.hint)box.append(textNode('p',q.hint));
  // Level 5+ Normal Summons need tributes: the player's own monsters on the field.
  const own=(duelView?.board||[]).filter(c=>c.player===q.player&&c.zone.includes('monster')&&c.copy_id!==q.copy_id);
  const tributes=[];
  if(q.kind==='unexplained'&&(q.level||0)>=5&&own.length){
    box.append(textNode('p',`Nivel ${q.level}: marca los monstruos sacrificados si fue Invocación Normal o colocación.`));
    for(const c of own){const l=document.createElement('label'),i=document.createElement('input');i.type='checkbox';i.onchange=()=>i.checked?tributes.push(c.copy_id):tributes.splice(tributes.indexOf(c.copy_id),1);l.append(i,document.createTextNode(` ${c.name||'carta'} (${c.zone_label})`));box.append(l);}
  }
  for(const o of q.options){
    const b=document.createElement('button');b.textContent=o.label;
    b.onclick=()=>{
      const e={type:o.type,player:q.player};
      if(q.kind==='missing')e.copy_id=q.expected_copy;
      else if(o.type==='change_position'){e.copy_id=q.copy_id;e.position=q.position;}
      else if(o.type==='flip')e.copy_id=q.copy_id;
      else{e.zone=q.zone;e.copy_id=q.copy_id;if(q.card_id)e.card_id=q.card_id;}
      if(['normal_summon','set_monster'].includes(o.type))e.tributes=[...tributes];
      if(o.type==='special_summon'&&['attack','defense'].includes(q.position))e.position=q.position;
      duelAct(e);
    };
    box.append(b);
  }
  return box;
}

// Phase bar over the video (as in Master Duel): current phase lit, later phases clickable.
const PHASE_KEYS=['draw','standby','main1','battle','main2','end'];
function renderPhaseBar(view){
  const bar=$d('#phaseBar');bar.hidden=!view.started||!!view.result;if(bar.hidden)return;
  $d('#turnLabel').textContent=`Turno ${view.turn} · ${view.players[view.current]?.name}`;
  const at=PHASE_KEYS.indexOf(view.phase);
  bar.querySelectorAll('button[data-phase]').forEach(b=>{
    const i=PHASE_KEYS.indexOf(b.dataset.phase);b.className=i===at?'now':'';
    b.disabled=i<at||(view.turn===1&&['battle','main2'].includes(b.dataset.phase));
  });
}
function nextPhase(){
  const v=duelView;if(!v?.started||v.result)return;
  if(v.phase==='end')return duelAct({type:'end_turn'});
  let i=PHASE_KEYS.indexOf(v.phase)+1;
  if(v.turn===1&&PHASE_KEYS[i]==='battle')i=PHASE_KEYS.indexOf('end');
  duelAct({type:'goto_phase',phase:PHASE_KEYS[i]});
}
document.querySelectorAll('#phaseBar button[data-phase]').forEach(b=>b.onclick=()=>duelAct({type:'goto_phase',phase:b.dataset.phase}));
$d('#barEndTurn').onclick=()=>duelAct({type:'end_turn'});
document.addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','SELECT','TEXTAREA','BUTTON'].includes(document.activeElement?.tagName)){e.preventDefault();nextPhase();}});
$d('#autoPlays').onchange=()=>duelAct({type:'auto',enabled:$d('#autoPlays').checked});

// Automatic plays, newest first: change to another play or undo.
function renderRecent(view){
  const recent=(view.recent||[]).slice(0,3);
  $d('#recentSection').hidden=!recent.length;
  // A new play puts its card in "Carta en juego".
  if(recent[0]&&recent[0].id!==renderRecent.lastId){renderRecent.lastId=recent[0].id;spotlight(recent[0].card_id);}
  const key=JSON.stringify(recent);if(key===renderRecent.key)return;renderRecent.key=key;
  const nodes=recent.map((r,i)=>{
    const row=document.createElement('div');row.className='play';row.append(textNode('span',r.text));
    if(i===0){   // only the latest can be changed without touching later plays
      for(const a of r.alternatives){const b=document.createElement('button');b.className='secondary';b.textContent=`Era: ${a.label}`;b.onclick=()=>duelAct({type:'revise',id:r.id,replacement:a.type});row.append(b);}
      const u=document.createElement('button');u.className='secondary';u.textContent='Deshacer';u.onclick=()=>duelAct({type:'revise',id:r.id});row.append(u);
    }
    return row;});
  $d('#recentPlays').replaceChildren(...(nodes.length?nodes:[textNode('p','Todavía no hay jugadas.')]));
}

// Graveyard and Banished of each player, newest last; a click shows the card.
function renderPiles(view){
  const key=JSON.stringify((view.players||[]).map(p=>[p.graveyard_cards,p.banished_cards]));
  if(key===renderPiles.key)return;renderPiles.key=key;
  const nodes=[];
  (view.players||[]).forEach(p=>{
    for(const [title,cards] of [['Cementerio',p.graveyard_cards||[]],['Desterradas',p.banished_cards||[]]]){
      const box=document.createElement('div');box.className='pile';box.append(textNode('h4',`${p.name} · ${title} (${cards.length})`));
      for(const c of cards){const b=document.createElement('button');b.textContent=c.name||'Carta sin identificar';b.disabled=!c.card_id;b.onclick=()=>spotlight(c.card_id);box.append(b);}
      nodes.push(box);
    }
  });
  $d('#pilesBody').replaceChildren(...(nodes.length?nodes:[textNode('p','Empieza un duelo para ver sus pilas.')]));
  const total=(view.players||[]).reduce((s,p)=>s+(p.graveyard||0)+(p.banished||0),0);
  $d('#piles').querySelector('summary').textContent=`Cementerio y Desterradas${total?` (${total})`:''}`;
}

// Past duels, newest first (archived when a duel is ended with "Terminar y reiniciar").
async function loadHistory(){
  try{
    const items=await (await fetch('/duel/history',{cache:'no-store'})).json();
    $d('#historyBody').replaceChildren(...(items.length?items.map(h=>{
      const who=h.winner!=null?`gana ${h.players[h.winner]}`:'sin terminar';
      const box=document.createElement('div');box.className='history';
      box.append(textNode('p',`${h.saved_at.replace('T',' ').slice(0,16)} · ${h.players.join(' vs ')} · ${who} · ${h.turns} turnos · LP ${h.lp.join(' / ')}`));return box;
    }):[textNode('p','Todavía no hay duelos guardados.')]));
  }catch(e){}
}
$d('#historyBox').addEventListener('toggle',()=>{if($d('#historyBox').open)loadHistory();});

function renderDuel(view){
  stageEvents(duelView,view);   // summon, attack, destruction and LP effects from what changed
  renderPhaseBar(view);renderRecent(view);renderPiles(view);
  if($d('#autoPlays').checked!==!!view.auto)$d('#autoPlays').checked=!!view.auto;
  duelView=view;
  $d('#duelSetup').hidden=view.started&&!view.result;$d('#duelControls').hidden=!view.started||!!view.result;
  // The phase bar over the video shows turn and phase; the panel only announces the result.
  $d('#duelPhase').textContent=view.result?`Duelo terminado: gana ${view.players[view.result.winner]?.name??'—'} (${view.result.reason}).`:
    view.started&&view.battle_step?`Battle Phase · ${view.battle_step}`:'';
  $d('#duelSection').hidden=view.started&&!view.result&&!(view.phase==='battle')&&!$d('#duelMessage').textContent;
  $d('#duelPlayers').replaceChildren(...(view.players||[]).map((p,i)=>{
    const box=document.createElement('div');box.className='player'+(i===view.current?' current':'');
    box.append(textNode('h3',p.name),textNode('div',`${p.lp} LP`),textNode('p',`Mano ${p.hand} · Mazo ${p.deck} · Mazo Extra ${p.extra_deck} · Cementerio ${p.graveyard} · Desterradas ${p.banished}`));
    box.children[1].className='lp';return box;}));
  // Rebuilt only when the questions change: the panel refreshes every 800 ms and would
  // otherwise clear tribute checkboxes while the player is ticking them.
  const questionsKey=JSON.stringify([view.questions,(view.board||[]).map(c=>c.copy_id)]);
  $d('#questionsSection').hidden=!(view.questions||[]).length;
  if(questionsKey!==renderDuel.questionsKey){renderDuel.questionsKey=questionsKey;$d('#duelQuestions').replaceChildren(...(view.questions||[]).map(questionNode));}
  const board=view.board||[];
  $d('#duelBoard').replaceChildren(...(board.length?[textNode('h3','En el campo')]:[textNode('p','Nada en el campo todavía.')]),...board.map(c=>textNode('p',`${view.players[c.player]?.name} · ${c.zone_label}: ${c.name||'carta boca abajo'} · ${POSITIONS[c.position]||c.position}${c.atk!=null?` · ATK ${c.atk}${c.def!=null?` / DEF ${c.def}`:''}`:''}`)));
  ['#lpPlayer'].forEach(s=>[...$d(s).options].forEach((o,i)=>o.textContent=view.players?.[i]?.name||o.textContent));
  renderBattle(view);
}

// ---- Battle: click (or carry-and-return gesture) declares; the result is proposed, then applied
let selectedAttacker=null;
function renderBattle(view){
  const inBattle=view.started&&!view.result&&view.phase==='battle';$d('#battle').hidden=!inBattle;$d('#duelSection').hidden&&=!inBattle;
  if(!inBattle){selectedAttacker=null;return;}
  const preview=view.battle_preview,attacker=selectedAttacker!=null?(view.board||[]).find(c=>c.copy_id===selectedAttacker):null;
  $d('#battleHelp').textContent=preview?'':attacker?`${attacker.name} va a atacar: haz clic en el monstruo rival o usa "Ataque directo".`:
    'Haz clic en tu monstruo y luego en el rival, o lleva tu carta junto al monstruo rival y regrésala a su zona.';
  $d('#battlePreview').hidden=!preview;
  if(preview){$d('#battleText').textContent=preview.text;$d('#battleOutcome').textContent=preview.problem?`No se puede calcular: ${preview.problem}`:`Resultado: ${preview.outcome}.`;}
  $d('#applyBattle').disabled=!preview||!!preview.problem;
  $d('#directAttack').hidden=!attacker||!!preview;
}
function battleClick(point){
  const v=duelView;if(!v?.started||v.phase!=='battle'||v.battle_preview)return false;
  const hit=fieldTracks(liveTracks).find(t=>insideQuad(point,t.corners));if(!hit)return false;
  const card=(v.board||[]).find(c=>c.copy_id===hit.track_id);if(!card||!card.zone.includes('monster'))return false;
  if(card.player===v.current&&card.position==='attack'){selectedAttacker=card.copy_id;renderedTracks=null;renderBattle(v);return true;}
  if(card.player!==v.current&&selectedAttacker!=null){duelAct({type:'attack',attacker:selectedAttacker,target:card.copy_id});selectedAttacker=null;return true;}
  return false;
}
$d('#directAttack').onclick=()=>{if(selectedAttacker!=null){duelAct({type:'attack',attacker:selectedAttacker,target:null});selectedAttacker=null;}};
$d('#applyBattle').onclick=()=>duelAct({type:'resolve_battle'});
$d('#cancelBattle').onclick=()=>duelAct({type:'cancel_attack'});

// On the video: the chosen attacker glows, and a declared attack shows an arrow to its target.
function drawBattle(context){
  const v=duelView;if(!v?.started||v.phase!=='battle')return;
  const where=id=>{const t=liveTracks.find(x=>x.track_id===id);return t?{c:t.corners.reduce(([a,b],[x,y])=>[a+x/4,b+y/4],[0,0]),q:t.corners}:null;};
  context.save();context.lineCap='round';
  const sel=selectedAttacker!=null?where(selectedAttacker):null;
  if(sel){context.strokeStyle='#5ff2ff';context.lineWidth=Math.max(5,frame.width/260);cornerMarks(context,sel.q,.28);}
  const pa=v.pending_attack;
  if(pa){
    const a=where(pa.attacker),t=pa.target!=null?where(pa.target):null;
    if(a){
      const to=t?t.c:[a.c[0],Math.max(20,a.c[1]-frame.height*.35)],ang=Math.atan2(to[1]-a.c[1],to[0]-a.c[0]),head=frame.width/60;
      context.strokeStyle='#ff6b4a';context.fillStyle='#ff6b4a';context.lineWidth=Math.max(5,frame.width/240);
      context.beginPath();context.moveTo(a.c[0],a.c[1]);context.lineTo(to[0]-Math.cos(ang)*head,to[1]-Math.sin(ang)*head);context.stroke();
      context.beginPath();context.moveTo(to[0],to[1]);context.lineTo(to[0]-head*Math.cos(ang-.45),to[1]-head*Math.sin(ang-.45));context.lineTo(to[0]-head*Math.cos(ang+.45),to[1]-head*Math.sin(ang+.45));context.closePath();context.fill();
    }
  }
  context.restore();
}

// Extra Deck of 15 each, so Synchro/Xyz/Fusion/Link placed on the field come out of it.
$d('#startDuel').onclick=()=>duelAct({type:'start_duel',names:[$d('#name0').value||'Jugador 1',$d('#name1').value||'Jugador 2'],starting:Number($d('#starting').value),extra_deck_sizes:[15,15]});
$d('#nextPhase').onclick=nextPhase;
$d('#endTurn').onclick=()=>duelAct({type:'end_turn'});
$d('#drawCard').onclick=()=>duelAct({type:'draw',player:duelView?.current??0});
$d('#applyLp').onclick=()=>duelAct({type:'change_lp',player:Number($d('#lpPlayer').value),delta:Number($d('#lpDelta').value),reason:'manual'});
$d('#undo').onclick=()=>duelAct({type:'undo'});
$d('#resetDuel').onclick=async()=>{if(confirm('¿Terminar este duelo y empezar otro? Queda guardado en el historial.')){await duelAct({type:'reset'});loadHistory();}};

async function refreshDuel(){
  try{
    const r=await fetch('/duel',{cache:'no-store'});
    if(r.status===404){$d('#duel').hidden=true;return;}   // demo with a saved capture: no duel
    $d('#duel').hidden=false;renderDuel(await r.json());
    // Printed mats move with the camera: refresh their outline every poll (about once a second).
    if((!playmat||playmat.mode==='printed')&&!calibration&&!virtualPreview){const m=await fetch('/playmat');if(m.ok){const first=!playmat,next=await m.json();if(JSON.stringify(next)!==JSON.stringify(playmat)){playmat=next;zonesVersion++;}
      // First load: show the saved board's mode and slider positions.
      if(first&&next.mode){const option=next.virtual?'virtual-'+next.mode:next.mode;if([...$d('#matMode').options].some(o=>o.value===option))$d('#matMode').value=option;if(next.virtual)setVirtualParams(next.virtual);}
      if(first)showMode(false);  // no saved board: the virtual board's preview appears right away
      else calibrationStep();}}
  }catch(e){}
  finally{setTimeout(refreshDuel,800);}
}
refreshDuel();
// ---- Escena AR: monstruos de pie sobre su carta y efectos del duelo ---------------------
// Sprites are YGOPro close-up cut-outs with transparency (/cutout/<ref>, trimmed so the
// bottom row is the feet). Each card's homography gives its centre, size and the
// perspective of its shadow; "up" is the image's up, as the camera looks down at the table.
const cutouts={cache:new Map(),get(ref){
  if(!ref)return null;let e=this.cache.get(ref);
  if(!e){e={image:null};this.cache.set(ref,e);const img=new Image();img.onload=()=>{e.image=img;};img.src='/cutout/'+encodeURIComponent(ref);}
  return e.image;}};

function cardMap(corners){
  // Unit square (card TL, TR, BR, BL) -> image quad, perspective-correct (Heckbert).
  const [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]=corners;
  const sx=x0-x1+x2-x3,sy=y0-y1+y2-y3,dx1=x1-x2,dx2=x3-x2,dy1=y1-y2,dy2=y3-y2;
  let g=0,h=0;
  if(Math.abs(sx)>1e-9||Math.abs(sy)>1e-9){const den=dx1*dy2-dx2*dy1;if(Math.abs(den)>1e-9){g=(sx*dy2-dx2*sy)/den;h=(dx1*sy-sx*dy1)/den;}}
  const a=x1-x0+g*x1,b=x3-x0+h*x3,d=y1-y0+g*y1,e=y3-y0+h*y3;
  return (u,v)=>{const w=g*u+h*v+1;return [(a*u+b*v+x0)/w,(d*u+e*v+y0)/w];};
}
function geometry(track){
  const H=cardMap(track.corners),center=H(.5,.5),l=H(0,.5),r=H(1,.5);
  return {H,center,width:Math.hypot(r[0]-l[0],r[1]-l[1])};
}
// A circle on the card's plane (radius in card widths), as the camera sees it.
function planeEllipse(context,H,scale){
  context.beginPath();
  for(let i=0;i<=36;i++){const t=i/36*Math.PI*2;const [x,y]=H(.5+.44*scale*Math.cos(t),.5+.3*scale*Math.sin(t));i?context.lineTo(x,y):context.moveTo(x,y);}
  context.closePath();
}

const effects=[];const lastSeen=new Map();
const hud={lp:[null,null]};
function boardCard(copyId){return (duelView?.board||[]).find(c=>c.copy_id===copyId);}
function effectOf(kind,copyId,now){return effects.find(e=>e.kind===kind&&e.copy===copyId&&now-e.start<e.duration);}

function drawMonster(context,item,now){
  const {track,g}=item,img=cutouts.get(track.sprite_ref);if(!img)return;
  const card=boardCard(track.track_id),position=card?.position;
  if(position==='facedown_defense'||position==='facedown')return;
  const defense=position==='defense',seed=(Number(track.track_id)||0)*1.7;
  let height=g.width*(defense?1.45:2.1);const width=height*img.width/img.height;
  let [x,y]=g.center,alpha=defense?.82:1;
  // Summon: rise out of the light pillar.
  const summon=effectOf('summon',track.track_id,now);
  if(summon){const t=Math.min(1,(now-summon.start)/700);height*=.4+.6*t;alpha*=t;}
  // Attack: lunge toward the target and back.
  const attack=effects.find(e=>e.kind==='attack'&&e.attacker===track.track_id&&now-e.start<e.duration);
  if(attack){const t=(now-attack.start)/attack.duration,k=t<.45?t/.45:t<.6?1:Math.max(0,1-(t-.6)/.4);x+=(attack.to[0]-x)*.75*k;y+=(attack.to[1]-y)*.75*k;}
  const bob=Math.sin(now/650+seed)*.035*height,sway=Math.sin(now/950+seed)*.035,breathe=1+Math.sin(now/520+seed)*.015;
  context.save();context.globalAlpha=alpha;context.translate(x,y-bob);context.rotate(sway);context.scale(breathe,1/breathe);
  context.drawImage(img,-width/2,-height,width,height);
  context.restore();
  if(defense){
    // Blue shield at the base: this monster is in Defense Position.
    context.save();context.globalAlpha=.85;context.fillStyle='rgba(80,160,255,.35)';context.strokeStyle='#8ec5ff';context.lineWidth=Math.max(2,g.width/30);
    const s=g.width*.28,[cx,cy]=g.center;context.beginPath();
    for(let i=0;i<6;i++){const a=Math.PI/3*i-Math.PI/2;context[i?'lineTo':'moveTo'](cx+s*Math.cos(a),cy-g.width*.35+s*Math.sin(a));}
    context.closePath();context.fill();context.stroke();context.restore();
  }
}

function drawStage(context,tracks,now){
  const items=tracks.filter(t=>t.sprite_ref&&t.corners?.length===4).map(track=>({track,g:geometry(track)}));
  for(const {track,g} of items)lastSeen.set(track.track_id,{g,sprite_ref:track.sprite_ref,name:track.name});
  // Base: shadow on the card and a glowing ring, then monsters from far to near so near ones cover far ones.
  for(const {track,g} of items){
    const card=boardCard(track.track_id);if(card?.position==='facedown_defense')continue;
    context.save();context.fillStyle='rgba(0,0,0,.38)';planeEllipse(context,g.H,1);context.fill();
    context.shadowColor=card&&card.controller===1?'#ffc861':'#5ff2ff';context.shadowBlur=g.width/5;context.strokeStyle=context.shadowColor;context.lineWidth=Math.max(2,g.width/28);
    context.globalAlpha=.55+.25*Math.sin(now/400+(Number(track.track_id)||0));planeEllipse(context,g.H,1.08);context.stroke();context.restore();
  }
  for(const item of items.sort((a,b)=>a.g.center[1]-b.g.center[1]))drawMonster(context,item,now);
  drawEffects(context,now);
}

function drawEffects(context,now){
  for(let i=effects.length-1;i>=0;i--){
    const e=effects[i],t=(now-e.start)/e.duration;
    if(t>=1){effects.splice(i,1);continue;}
    const seen=lastSeen.get(e.copy);
    if(e.kind==='summon'&&seen){
      // Pillar of light and a ring spreading on the table.
      const {g}=seen,[x,y]=g.center,h=g.width*2.2*(t<.3?t/.3:1),fade=t<.7?1:1-(t-.7)/.3;
      context.save();const grad=context.createLinearGradient(x,y,x,y-h);grad.addColorStop(0,`rgba(180,245,255,${.75*fade})`);grad.addColorStop(1,'rgba(180,245,255,0)');
      context.fillStyle=grad;context.fillRect(x-g.width*.45,y-h,g.width*.9,h);
      context.strokeStyle=`rgba(140,240,255,${fade})`;context.lineWidth=Math.max(2,g.width/20);planeEllipse(context,g.H,.6+1.6*t);context.stroke();
      context.fillStyle=`rgba(230,255,255,${fade})`;
      for(let k=0;k<22;k++){const a=k*2.4,r=g.width*(.2+.5*((k*37)%10)/10),px=x+Math.cos(a)*r,py=y-g.width*3*((t*1.4+k/22)%1);context.fillRect(px,py,g.width/40+1,g.width/40+1);}
      context.restore();
    }
    if(e.kind==='impact'){
      // Flash where the attack lands.
      const [x,y]=e.at,r=e.size*(.3+1.2*t);context.save();const grad=context.createRadialGradient(x,y,0,x,y,r);
      grad.addColorStop(0,`rgba(255,255,255,${1-t})`);grad.addColorStop(.4,`rgba(255,200,120,${.7*(1-t)})`);grad.addColorStop(1,'rgba(255,120,60,0)');
      context.fillStyle=grad;context.beginPath();context.arc(x,y,r,0,Math.PI*2);context.fill();context.restore();
    }
    if(e.kind==='destroy'&&e.image){
      // The monster breaks into pieces that fall and fade.
      const {g}=e,[x,y]=g.center,height=g.width*2.1,width=height*e.image.width/e.image.height,n=5;
      context.save();context.globalAlpha=1-t;
      for(let r=0;r<n;r++)for(let c=0;c<n;c++){
        const sx=e.image.width*c/n,sy=e.image.height*r/n,sw=e.image.width/n,sh=e.image.height/n;
        const dx=(c-(n-1)/2)*g.width*.9*t,dy=-height+(r+.5)*height/n+(r-n)*g.width*.3*t+g.width*3*t*t;
        context.save();context.translate(x+dx,y+dy);context.rotate((c-r)*1.3*t);
        context.drawImage(e.image,sx,sy,sw,sh,-width/n/2,-height/n/2,width/n,height/n);context.restore();
      }
      context.restore();
    }
    if(e.kind==='lp'){
      // Damage or gain floating up from that player's LP counter.
      const [x,y]=hudAnchor(e.player);context.save();context.globalAlpha=1-t;context.font=`bold ${Math.round(frame.width/28)}px system-ui`;context.textAlign='center';
      context.fillStyle=e.delta<0?'#ff6b6b':'#6bff9e';context.strokeStyle='rgba(0,0,0,.7)';context.lineWidth=6;
      // Starts just below the LP box and rises toward it.
      const dir=e.player===0?-1:1,ty=y+dir*(frame.height*.1+frame.height*.05*t),text=(e.delta>0?'+':'')+e.delta;context.strokeText(text,x,ty);context.fillText(text,x,ty);context.restore();
    }
  }
}

// LP boxes in opposite corners: the near player bottom-left, the opponent top-right (the phase bar is top centre).
function hudAnchor(player){return player===0?[frame.width*.13,frame.height*.93]:[frame.width*.87,frame.height*.08];}
function drawHud(context,now){
  const view=duelView;if(!view?.started)return;
  // LP boxes at the top, counting toward the real value.
  view.players.forEach((p,i)=>{
    const shown=hud.lp[i]??p.lp;hud.lp[i]=Math.abs(shown-p.lp)<1?p.lp:shown+(p.lp-shown)*.08;
    const [x,y]=hudAnchor(i),w=frame.width*.2,h=frame.height*.085;
    context.save();context.fillStyle='rgba(8,14,26,.72)';context.strokeStyle=i===view.current?'#5ff2ff':'rgba(160,190,230,.6)';context.lineWidth=3;
    context.beginPath();context.roundRect?context.roundRect(x-w/2,y-h/2,w,h,12):context.rect(x-w/2,y-h/2,w,h);context.fill();context.stroke();
    context.textAlign='center';context.fillStyle='#aebbd0';context.font=`600 ${Math.round(h*.26)}px system-ui`;context.fillText(p.name,x,y-h*.12);
    context.fillStyle='#e9f6ff';context.font=`bold ${Math.round(h*.44)}px system-ui`;context.fillText(`${Math.round(hud.lp[i])} LP`,x,y+h*.32);
    context.restore();
  });
}

// Effects come from what changed in the duel, never from the camera alone.
function stageEvents(prev,next){
  if(!prev||!next||!document.querySelector('#fx').checked)return;const now=performance.now();
  const before=new Map((prev.board||[]).map(c=>[c.copy_id,c])),after=new Map((next.board||[]).map(c=>[c.copy_id,c]));
  for(const [id,c] of after)if(!before.has(id)&&c.zone.includes('monster')&&c.position!=='facedown_defense')effects.push({kind:'summon',copy:id,start:now,duration:900});
  for(const [id,c] of before)if(!after.has(id)){
    const seen=lastSeen.get(id),image=seen&&cutouts.get(seen.sprite_ref);
    if(seen&&image&&c.zone.includes('monster'))effects.push({kind:'destroy',copy:id,g:seen.g,image,start:now,duration:800});
  }
  if(prev.pending_attack&&!next.pending_attack){
    const {attacker,target}=prev.pending_attack,from=lastSeen.get(attacker),to=target!=null?lastSeen.get(target):null;
    if(from){
      const aim=to?to.g.center:[from.g.center[0],from.g.center[1]-from.g.width*4];
      effects.push({kind:'attack',attacker,to:aim,start:now,duration:700});
      setTimeout(()=>effects.push({kind:'impact',at:aim,size:from.g.width*1.6,start:performance.now(),duration:600}),380);
    }
  }
  (next.players||[]).forEach((p,i)=>{const old=prev.players?.[i]?.lp;if(old!=null&&old!==p.lp)effects.push({kind:'lp',player:i,delta:p.lp-old,start:now,duration:1400});});
}

draw();refreshCamera();followAnalysis();
