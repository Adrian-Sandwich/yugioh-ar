// Duel view (/duelo): only the live video with the board, the recognized cards and the
// duel panel. The diagnostic viewer (/) keeps the analysed frame, OCR and glare tools.
const frame=document.querySelector('#frame'),ctx=frame.getContext('2d');
let currentBitmap=null,frameNumber=0,liveTracks=[],renderedFrame=-1,renderedTracks=null,renderedAR=null;
let playmat=null,calibration=null,zonesVersion=0,renderedZones=-1,virtualPreview=null;
function textNode(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}

// English names next to the Spanish ones (most TCG copies are printed in English).
const englishNames=new Map();
function englishName(cardId){
  if(!cardId)return null;
  if(!englishNames.has(cardId)){englishNames.set(cardId,null);fetch('/card-info?id='+encodeURIComponent(cardId)).then(r=>r.ok?r.json():null).then(s=>{if(s?.name_en){englishNames.set(cardId,s.name_en);renderedTracks=null;}}).catch(()=>{});}
  return englishNames.get(cardId);
}

function drawSprites(context,cards,width,height){
  if(!spriteGL||!document.querySelector('#ar').checked)return;
  const items=cards.filter(c=>c.corners?.length===4&&c.sprite_ref).map(c=>({corners:c.corners,image:sprites.get('/sprite/'+c.sprite_ref)}));
  const layer=spriteGL.draw(width,height,items);
  if(layer)context.drawImage(layer,0,0,width,height);
}

function drawCards(context,cards){
  const size=Math.round(frame.width/70);
  for(const card of cards){
    context.save();context.lineWidth=Math.max(3,frame.width/500);context.strokeStyle='#80ffbc';
    context.beginPath();card.corners.forEach(([x,y],i)=>i?context.lineTo(x,y):context.moveTo(x,y));context.closePath();context.stroke();
    const en=englishName(card.card_id);const label=card.name?(en&&en!==card.name?`${card.name} · ${en}`:card.name):null;
    if(label){
      const x=Math.max(0,Math.min(...card.corners.map(p=>p[0]))),y=Math.max(size+6,Math.min(...card.corners.map(p=>p[1]))-8);
      context.font=`bold ${size}px system-ui`;context.fillStyle='rgba(16,20,29,.85)';context.fillRect(x,y-size-2,context.measureText(label).width+14,size+10);
      context.fillStyle='#80ffbc';context.fillText(label,x+7,y);
    }
    context.restore();
  }
}

function draw(){
  const ar=document.querySelector('#ar').checked;
  if(currentBitmap&&(renderedFrame!==frameNumber||renderedTracks!==liveTracks||renderedZones!==zonesVersion||renderedAR!==ar)){
    if(frame.width!==currentBitmap.width||frame.height!==currentBitmap.height){frame.width=currentBitmap.width;frame.height=currentBitmap.height;zonesVersion++;}
    ctx.drawImage(currentBitmap,0,0);
    drawTableOverlay(ctx);
    drawSprites(ctx,liveTracks.filter(t=>t.stable),frame.width,frame.height);
    drawCards(ctx,liveTracks);
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
    document.querySelector('#videoStatus').textContent=`${liveTracks.length} carta${liveTracks.length===1?'':'s'} reconocida${liveTracks.length===1?'':'s'}`;
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
    context.save();context.lineWidth=Math.max(2,frame.width/420);context.font=`600 ${Math.round(frame.width/75)}px system-ui`;context.textAlign='center';
    for(const z of board.zones||[]){
      // White outlines like the printed mat; the opponent's board slightly yellow.
      context.strokeStyle=z.player===0?'rgba(255,255,255,.8)':'rgba(255,224,150,.8)';
      context.beginPath();z.polygon.forEach(([x,y],i)=>i?context.lineTo(x,y):context.moveTo(x,y));context.closePath();context.stroke();
      const bottom=z.polygon.reduce((a,p)=>a[1]>p[1]?a:p);const [cx]=z.polygon.reduce(([a],[x])=>[a+x/4],[0]);
      context.fillStyle='rgba(255,255,255,.85)';context.fillText(shortLabel(z.zone),cx,bottom[1]-8);
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
  if(editing){$d('#calibrationHelp').textContent='Vista previa: ajusta los controles y pulsa "Fijar tablero".';previewVirtual();}
  else{virtualPreview=null;zonesVersion++;calibrationStep();}
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

function duelMessage(text,error=false){const m=$d('#duelMessage');m.textContent=text;m.className=error?'error':'';}
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

function renderDuel(view){
  duelView=view;
  $d('#duelSetup').hidden=view.started&&!view.result;$d('#duelControls').hidden=!view.started||!!view.result;
  $d('#duelPhase').textContent=!view.started?'Duelo sin empezar.':view.result?`Duelo terminado: gana ${view.players[view.result.winner]?.name??'—'} (${view.result.reason}).`:
    `Turno ${view.turn} · ${view.players[view.current]?.name} · ${PHASES[view.phase]||view.phase}${view.battle_step?` (${view.battle_step})`:''} · ${view.events} eventos registrados`;
  $d('#duelPlayers').replaceChildren(...(view.players||[]).map((p,i)=>{
    const box=document.createElement('div');box.className='player'+(i===view.current?' current':'');
    box.append(textNode('h3',p.name),textNode('div',`${p.lp} LP`),textNode('p',`Mano ${p.hand} · Mazo ${p.deck} · Mazo Extra ${p.extra_deck} · Cementerio ${p.graveyard} · Desterradas ${p.banished}`));
    box.children[1].className='lp';return box;}));
  // Rebuilt only when the questions change: the panel refreshes every 800 ms and would
  // otherwise clear tribute checkboxes while the player is ticking them.
  const questionsKey=JSON.stringify([view.questions,(view.board||[]).map(c=>c.copy_id)]);
  if(questionsKey!==renderDuel.questionsKey){renderDuel.questionsKey=questionsKey;const nodes=(view.questions||[]).map(questionNode);$d('#duelQuestions').replaceChildren(...(nodes.length?nodes:[textNode('p',view.started?'Sin preguntas pendientes.':'Empieza el duelo para que las cartas del tablero generen preguntas.')]));}
  const board=view.board||[];
  $d('#duelBoard').replaceChildren(...(board.length?[textNode('h3','En el campo')]:[textNode('p','Nada en el campo todavía.')]),...board.map(c=>textNode('p',`${view.players[c.player]?.name} · ${c.zone_label}: ${c.name||'carta boca abajo'} · ${POSITIONS[c.position]||c.position}${c.atk!=null?` · ATK ${c.atk}${c.def!=null?` / DEF ${c.def}`:''}`:''}`)));
  ['#lpPlayer'].forEach(s=>[...$d(s).options].forEach((o,i)=>o.textContent=view.players?.[i]?.name||o.textContent));
  // Battle Phase: the current player's face-up Attack Position monsters against the opponent's monsters or directly.
  const inBattle=view.started&&!view.result&&view.phase==='battle';$d('#battle').hidden=!inBattle;
  if(inBattle){
    const keep=(sel,items)=>{const old=$d(sel).value;$d(sel).replaceChildren(...items.map(([v,t])=>{const o=document.createElement('option');o.value=v;o.textContent=t;return o;}));if([...$d(sel).options].some(o=>o.value===old))$d(sel).value=old;};
    keep('#attacker',board.filter(c=>c.player===view.current&&c.zone.includes('monster')&&c.position==='attack').map(c=>[String(c.copy_id),`${c.name||'monstruo'} (ATK ${c.atk??'?'})`]));
    keep('#target',[['','Ataque directo'],...board.filter(c=>c.player!==view.current&&c.zone.includes('monster')).map(c=>[String(c.copy_id),`${c.name||'boca abajo'} · ${POSITIONS[c.position]||c.position}`])]);
    $d('#resolveBattle').disabled=!view.pending_attack;
  }
}
// copy_id comes from the recognizer's track ids (integers); option values are text.
const copyValue=v=>v===''?null:(Number.isNaN(Number(v))?v:Number(v));
$d('#declareAttack').onclick=()=>duelAct({type:'declare_attack',player:duelView?.current??0,attacker:copyValue($d('#attacker').value),target:copyValue($d('#target').value)});
$d('#resolveBattle').onclick=()=>duelAct({type:'resolve_battle'});

$d('#startDuel').onclick=()=>duelAct({type:'start_duel',names:[$d('#name0').value||'Jugador 1',$d('#name1').value||'Jugador 2'],starting:Number($d('#starting').value)});
$d('#nextPhase').onclick=()=>duelAct({type:'next_phase'});
$d('#endTurn').onclick=()=>duelAct({type:'end_turn'});
$d('#drawCard').onclick=()=>duelAct({type:'draw',player:duelView?.current??0});
$d('#applyLp').onclick=()=>duelAct({type:'change_lp',player:Number($d('#lpPlayer').value),delta:Number($d('#lpDelta').value),reason:'manual'});
$d('#undo').onclick=()=>duelAct({type:'undo'});
$d('#resetDuel').onclick=()=>{if(confirm('¿Terminar este duelo y empezar otro? Se borra el registro del duelo actual.'))duelAct({type:'reset'});};

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
draw();refreshCamera();followAnalysis();
