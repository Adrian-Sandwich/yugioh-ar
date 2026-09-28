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
function zoneHit(point){const board=virtualPreview||playmat;return (board?.zones||[]).find(z=>insideQuad(point,z.polygon))||null;}
function zoneAt(point){return zoneHit(point)?.zone||null;}
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

// Face-down cards have no track (the detector does not see card backs): their zone gets the marks.
let teachingBack=false,renderedDuel=null;
// A face-down Defense Position monster gets a generic figure (never its identity). Three styles
// to compare with the "Boca abajo" button: holographic shield, hooded silhouette, standing card back.
const FD_STYLES=[['shield','Escudo'],['silhouette','Silueta'],['card','Carta de pie']];
let fdStyle=(()=>{try{return localStorage.getItem('fdStyle')||'shield';}catch(e){return 'shield';}})();
function fdButtonLabel(){const b=$d('#fdStyle');if(b)b.textContent='Boca abajo: '+FD_STYLES.find(s=>s[0]===fdStyle)[1];}
function hexPath(context,cx,cy,r){context.beginPath();for(let i=0;i<6;i++){const a=Math.PI/3*i-Math.PI/2;context[i?'lineTo':'moveTo'](cx+r*Math.cos(a),cy+r*.9*Math.sin(a));}context.closePath();}
function drawFacedownFigure(context,polygon,now,seed){
  const H=cardMap(polygon),[cx,cy]=H(.5,.5),l=H(0,.5),r=H(1,.5),w=Math.hypot(r[0]-l[0],r[1]-l[1]);
  const pulse=.5+.5*Math.sin(now/700+seed),bob=Math.sin(now/900+seed)*w*.02;
  context.save();
  context.fillStyle='rgba(0,0,0,.3)';planeEllipse(context,H,.9);context.fill();
  if(fdStyle==='shield'){
    // Translucent shield with the back's orange swirl, breathing softly.
    const y=Math.max(w*.4,cy-w*.18)+bob,s=w*.36;
    const grad=context.createRadialGradient(cx,y,s*.1,cx,y,s);grad.addColorStop(0,'rgba(20,8,2,.85)');grad.addColorStop(.7,'rgba(120,55,12,.7)');grad.addColorStop(1,'rgba(230,140,50,.55)');
    hexPath(context,cx,y,s);context.fillStyle=grad;context.fill();
    context.shadowColor='#ffb35c';context.shadowBlur=w/5*(.6+.4*pulse);context.strokeStyle='#ffb35c';context.lineWidth=Math.max(2,w/28);context.stroke();
    context.shadowBlur=0;context.strokeStyle=`rgba(255,170,80,${.5+.3*pulse})`;context.lineWidth=Math.max(1.5,w/45);
    for(let k=0;k<3;k++){context.beginPath();context.ellipse(cx,y,s*(.25+.2*k),s*(.18+.15*k),now/1500+k,0,Math.PI*1.4);context.stroke();}
  }else if(fdStyle==='silhouette'){
    // A dark hooded figure crouching behind a round shield; only its eyes glow.
    const base=cy+w*.05,hgt=w*.95,top=Math.max(w*.1,base-hgt)+bob;
    context.fillStyle='rgba(22,12,38,.9)';context.shadowColor='#b58cff';context.shadowBlur=w/6;
    context.beginPath();context.moveTo(cx-w*.3,base);context.quadraticCurveTo(cx-w*.26,top+hgt*.35,cx,top+hgt*.08);context.quadraticCurveTo(cx+w*.26,top+hgt*.35,cx+w*.3,base);context.closePath();context.fill();
    context.beginPath();context.ellipse(cx,top+hgt*.2,w*.12,w*.14,0,0,Math.PI*2);context.fill();
    context.shadowBlur=w/10;context.fillStyle=`rgba(255,80,120,${.6+.4*pulse})`;
    context.beginPath();context.arc(cx-w*.04,top+hgt*.21,w*.018,0,Math.PI*2);context.arc(cx+w*.04,top+hgt*.21,w*.018,0,Math.PI*2);context.fill();
    context.shadowColor='#b58cff';context.shadowBlur=w/8;context.fillStyle='rgba(60,40,90,.92)';context.strokeStyle='#b58cff';context.lineWidth=Math.max(2,w/30);
    context.beginPath();context.ellipse(cx+w*.05,top+hgt*.62,w*.2,w*.24,0,0,Math.PI*2);context.fill();context.stroke();
  }else{
    // The card back standing up, turned sideways (Defense Position), as Master Duel shows it.
    const cw=w*.62,ch=cw*.69,y=Math.max(ch/2,cy-w*.22)+bob;
    context.shadowColor='#ffb35c';context.shadowBlur=w/6*(.6+.4*pulse);
    context.fillStyle='#b8651e';context.fillRect(cx-cw/2,y-ch/2,cw,ch);context.shadowBlur=0;
    const grad=context.createRadialGradient(cx,y,0,cx,y,cw*.5);grad.addColorStop(0,'#050201');grad.addColorStop(.6,'#2a1206');grad.addColorStop(1,'#5a2a0c');
    context.fillStyle=grad;context.fillRect(cx-cw/2+cw*.05,y-ch/2+cw*.05,cw*.9,ch-cw*.1);
    context.strokeStyle='rgba(255,150,60,.75)';context.lineWidth=Math.max(1.5,w/50);
    for(let k=0;k<4;k++){context.beginPath();context.ellipse(cx,y,cw*(.1+.09*k),ch*(.1+.08*k),.6+now/4000,0,Math.PI*1.5);context.stroke();}
  }
  context.restore();
}
function drawFacedown(context){
  const board=virtualPreview||playmat;if(!board?.zones||calibration)return;
  const now=performance.now();
  if($d('#ar')?.checked)for(const card of duelView?.board||[]){
    if(card.position!=='facedown_defense')continue;
    const z=board.zones.find(z=>z.player===card.player&&z.zone===card.zone);if(z)drawFacedownFigure(context,z.polygon,now,card.zone.length+card.player*3);
  }
  const size=Math.max(10,Math.round(frame.width/140));
  context.save();context.lineWidth=Math.max(3,frame.width/480);context.strokeStyle='#c9a0ff';context.lineCap='round';
  context.textAlign='center';context.font=`600 ${size}px system-ui`;
  for(const card of duelView?.board||[]){
    if(card.position!=='facedown'&&card.position!=='facedown_defense')continue;
    const z=board.zones.find(z=>z.player===card.player&&z.zone===card.zone);if(!z)continue;
    cornerMarks(context,z.polygon,.3);
    const [cx,cy]=z.polygon.reduce(([a,b],[x,y])=>[a+x/4,b+y/4],[0,0]),label='Boca abajo',w=context.measureText(label).width+10;
    context.fillStyle='rgba(10,14,22,.72)';context.fillRect(cx-w/2,cy-size*.8,w,size*1.5);
    context.fillStyle='#e6d6ff';context.fillText(label,cx,cy+size*.35);
  }
  context.restore();
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
  renderTags(s);renderEffect(s);
}
// What the card does (from the engine scripts, or rules on its text) and, apart, what it costs.
function renderTags(s){
  const tags=[],does=s.does||[],cost=s.cost||[],shown=does.slice(0,4);
  for(const t of shown)tags.push(Object.assign(textNode('span',t),{title:s.categories_source==='text'?'Deducido del texto de la carta':'Declarado en el script del motor'}));
  if(does.length>shown.length){const m=textNode('span',`+${does.length-shown.length}`);m.className='more';m.title=does.slice(4).join(', ');tags.push(m);}
  for(const t of cost.slice(0,2)){const c=textNode('span','Costo: '+t);c.className='cost';tags.push(c);}
  document.querySelector('#spotTags').replaceChildren(...tags);
}
// The effect text by blocks: when (condition) / cost / target / does; restrictions apart.
function renderEffect(s){
  const box=document.querySelector('#spotEffect'),blocks=s.effect_blocks||[];
  const structured=blocks.some(b=>b.cost||b.condition||(b.targets||[]).length);
  if(!structured){box.textContent=s.effect||'';return;}
  const part=(cls,label,text)=>{const p=document.createElement('span');p.className=cls;const b=textNode('b',label);p.append(b,document.createTextNode(text+' '));return p;};
  box.replaceChildren(...blocks.map(b=>{
    if(b.restriction)return Object.assign(textNode('p',b.restriction),{className:'restriction'});
    const p=document.createElement('p');p.className='eff';
    if(b.plain){p.textContent=b.plain;return p;}
    if(b.condition)p.append(part('when','Condición',b.condition));
    if(b.cost)p.append(part('cost','Costo',b.cost));
    for(const t of b.targets||[])p.append(part('target','Objetivo',t));
    p.append(part('does','Hace',b.does));
    return p;
  }));
}
// Click a card on the video to see it.
frame.addEventListener('click',event=>{
  if(calibration)return;
  const rect=frame.getBoundingClientRect(),p=[(event.clientX-rect.left)*frame.width/rect.width,(event.clientY-rect.top)*frame.height/rect.height];
  if(teachingBack){   // "Enseñar reverso": the clicked zone holds a face-down card
    const z=zoneHit(p);
    if(!z||!/^(monster|spell):|^field$/.test(z.zone)){duelMessage('Haz clic en una Zona de Monstruo, de Magia/Trampa o de Campo con la carta boca abajo.',true);return;}
    teachingBack=false;duelAct({type:'teach_back',player:z.player,zone:z.zone});return;
  }
  if(battleClick(p))return;   // Battle Phase: choosing attacker and target
  const hit=fieldTracks(liveTracks).find(t=>insideQuad(p,t.corners));
  if(hit)spotlight(hit.card_id);
});

function draw(now){
  const ar=document.querySelector('#ar').checked;
  // With AR on, monsters breathe and effects play: repaint every display frame.
  if(currentBitmap&&(ar||renderedFrame!==frameNumber||renderedTracks!==liveTracks||renderedZones!==zonesVersion||renderedAR!==ar||renderedDuel!==duelView)){
    if(frame.width!==currentBitmap.width||frame.height!==currentBitmap.height){frame.width=currentBitmap.width;frame.height=currentBitmap.height;zonesVersion++;}
    ctx.drawImage(currentBitmap,0,0);
    drawTableOverlay(ctx);
    drawFacedown(ctx);renderedDuel=duelView;
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
    const r=await fetch('/analysis?view=duel&after='+analysisSequence,{cache:'no-store',signal:AbortSignal.timeout(10000)});
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
    // Notary mode: a rule this play skipped, as a quiet note (the players decide).
    if(r.warnings?.length){const w=textNode('small','Aviso: '+r.warnings.join(' · '));w.className='warning';row.append(w);}
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
  const backs=view.card_backs;
  if(backs)$d('#backsStatus').textContent=`${backs.official?'Se reconoce el reverso oficial':'Sin reverso oficial (no se pudo descargar)'}${backs.taught?` y ${backs.taught} reverso${backs.taught===1?'':'s'} enseñado${backs.taught===1?'':'s'}`:''}. Si juegan con fundas, pon una carta boca abajo en una zona y enséñala.`;
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
$d('#fdStyle').onclick=()=>{
  const i=FD_STYLES.findIndex(s=>s[0]===fdStyle);fdStyle=FD_STYLES[(i+1)%FD_STYLES.length][0];
  try{localStorage.setItem('fdStyle',fdStyle);}catch(e){}
  fdButtonLabel();renderedAR=null;
};
fdButtonLabel();
$d('#teachBack').onclick=()=>{teachingBack=true;duelMessage('Pon una carta boca abajo en una zona y haz clic en esa zona en el vídeo.');};
$d('#forgetBacks').onclick=()=>{if(confirm('¿Olvidar los reversos enseñados? El reverso oficial se sigue reconociendo.'))duelAct({type:'forget_backs'});};
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

// ---- Motor de efectos: luz aditiva, partículas con física, curvas con rebote y sacudida ----
// Everything is drawn over the live video with the canvas 2D API. Lights add up
// ('lighter'), glows come from blurred silhouettes cached once per sprite and colour,
// and each duel event plays a short timed sequence (see drawEffects).
const effects=[];const lastSeen=new Map();
const hud={lp:[null,null],flash:[0,0],flashColor:['#ff5a5a','#ff5a5a']};
function boardCard(copyId){return (duelView?.board||[]).find(c=>c.copy_id===copyId);}
function effectOf(kind,copyId,now){return effects.find(e=>e.kind===kind&&e.copy===copyId&&now-e.start<e.duration);}

const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
const ease={out:t=>1-Math.pow(1-clamp(t),3),in:t=>Math.pow(clamp(t),3),inOut:t=>{t=clamp(t);return t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;},
  back:t=>{t=clamp(t);const c=1.9;return 1+(c+1)*Math.pow(t-1,3)+c*Math.pow(t-1,2);}};
const span=(t,a,b)=>clamp((t-a)/(b-a));   // progress of t inside [a, b]
const RGB={monster:[95,242,255],rival:[255,196,92],spell:[63,230,164],trap:[255,86,160],white:[255,255,255],fire:[255,150,60],back:[255,160,70],heal:[110,255,160],hurt:[255,80,80]};
const rgba=(c,a)=>`rgba(${c[0]},${c[1]},${c[2]},${clamp(a)})`;
const KIND_COLOR={monster:'#5ff2ff',spell:'#3fe6a4',trap:'#ff56a0'};
function kindOf(track){
  const s=sheetOf(track.card_id);if(s?.card_type==='spell'||s?.card_type==='trap')return s.card_type;
  const card=boardCard(track.track_id);
  if(card&&/^Trampa/.test(card.type||''))return 'trap';
  if(card&&(/^Magia/.test(card.type||'')||/^spell:|^field$/.test(card.zone)))return 'spell';
  return 'monster';
}
function ownerColor(kind,rival){return kind==='monster'?(rival?RGB.rival:RGB.monster):RGB[kind];}

// Blurred, tinted silhouette of a sprite (glow and flashes), cached per image, colour and blur.
const silhouettes=new Map();
function silhouette(img,color,blur){
  const key=img.src+'|'+color+'|'+blur;let s=silhouettes.get(key);
  if(!s){
    const pad=Math.ceil(blur*2.2),c=document.createElement('canvas');c.width=img.width+pad*2;c.height=img.height+pad*2;
    const x=c.getContext('2d');if(blur)x.filter=`blur(${blur}px)`;x.drawImage(img,pad,pad);x.filter='none';
    x.globalCompositeOperation='source-in';x.fillStyle=color;x.fillRect(0,0,c.width,c.height);
    s={canvas:c,pad};silhouettes.set(key,s);if(silhouettes.size>160)silhouettes.delete(silhouettes.keys().next().value);
  }
  return s;
}
// A figure centred at (x, y): glow behind, the sprite, then an optional white flash on top.
function drawFigure(context,img,x,y,width,height,o={}){
  const k=width/img.width;
  context.save();context.translate(x,y);if(o.rot)context.rotate(o.rot);if(o.scale&&o.scale!==1)context.scale(o.scale,o.scale*(o.squash||1));
  if(o.glow){
    const g=silhouette(img,o.glow,Math.max(4,Math.round(img.width*.045))),a=clamp(o.glowAlpha??.55)*clamp(o.alpha??1);
    // Normal-blend halo first (shows on bright tables), then the additive one (shines on dark ones).
    context.globalAlpha=a*.55;context.drawImage(g.canvas,-width/2-g.pad*k,-height/2-g.pad*k,g.canvas.width*k,g.canvas.height*k);
    context.globalCompositeOperation='lighter';context.globalAlpha=a;
    context.drawImage(g.canvas,-width/2-g.pad*k,-height/2-g.pad*k,g.canvas.width*k,g.canvas.height*k);
  }
  context.globalCompositeOperation='source-over';context.globalAlpha=clamp(o.alpha??1);
  context.drawImage(img,-width/2,-height/2,width,height);
  if(o.flash>0){
    const w=silhouette(img,'#ffffff',0);context.globalCompositeOperation='lighter';context.globalAlpha=clamp(o.flash);
    context.drawImage(w.canvas,-width/2,-height/2,width,height);
  }
  context.restore();
}

// ---- partículas ----
const particles=[];let lastFrame=0;
function emit(p){if(particles.length<1200)particles.push({age:0,drag:.0015,gravity:0,spin:0,rot:0,shape:'dot',...p});}
function burst(n,make){for(let i=0;i<n;i++)emit(make(i,n));}
function stepParticles(dt){
  for(let i=particles.length-1;i>=0;i--){
    const p=particles[i];p.age+=dt;if(p.age>=p.life){particles.splice(i,1);continue;}
    const d=Math.exp(-p.drag*dt);p.vx*=d;p.vy=p.vy*d+p.gravity*dt;p.x+=p.vx*dt;p.y+=p.vy*dt;p.rot+=p.spin*dt;
  }
}
function drawParticles(context){
  context.save();
  for(const p of particles){
    const t=p.age/p.life,a=(p.fadeIn?Math.min(1,t/p.fadeIn):1)*(1-ease.in(t));
    if(p.shape==='smoke'){   // dark, normal blending, grows
      const r=p.size*(1+t*1.8),g=context.createRadialGradient(p.x,p.y,0,p.x,p.y,r);
      context.globalCompositeOperation='source-over';g.addColorStop(0,`rgba(20,16,24,${.35*a})`);g.addColorStop(1,'rgba(20,16,24,0)');
      context.fillStyle=g;context.beginPath();context.arc(p.x,p.y,r,0,Math.PI*2);context.fill();continue;
    }
    if(p.shape==='spark'){   // a streak along its velocity (darker core line keeps it visible on bright mats)
      context.beginPath();context.moveTo(p.x,p.y);context.lineTo(p.x-p.vx*p.trail,p.y-p.vy*p.trail);context.lineCap='round';
      litStroke(context,p.color,a,p.size*(1-t*.6));
    }else if(p.shape==='glyph'){   // small spinning diamond (magic)
      context.save();context.translate(p.x,p.y);context.rotate(p.rot);
      const s=p.size;context.beginPath();context.moveTo(0,-s);context.lineTo(s*.6,0);context.lineTo(0,s);context.lineTo(-s*.6,0);context.closePath();
      context.fillStyle=rgba(dark(p.color),a*.8);context.fill();context.globalCompositeOperation='lighter';context.fillStyle=rgba(p.color,a);context.scale(.7,.7);context.fill();context.restore();
    }else{   // soft dot
      context.globalCompositeOperation='lighter';
      const r=p.size*(p.grow?1+t*p.grow:1),g=context.createRadialGradient(p.x,p.y,0,p.x,p.y,r);
      g.addColorStop(0,rgba([255,255,255],a));g.addColorStop(.35,rgba(p.color,a*.9));g.addColorStop(1,rgba(p.color,0));
      context.fillStyle=g;context.fillRect(p.x-r,p.y-r,r*2,r*2);
    }
  }
  context.restore();
}

// ---- utilidades de luz y geometría sobre el plano de la carta ----
let shake={until:0,mag:0,start:0};
function addShake(mag,ms){const now=performance.now();if(mag>=shake.mag||now>shake.until)shake={until:now+ms,mag,start:now};}
function shakeOffset(now){
  if(now>shake.until)return [0,0];const k=1-(now-shake.start)/(shake.until-shake.start);
  return [Math.sin(now*.11)*shake.mag*k,Math.cos(now*.13)*shake.mag*k*.7];
}
let screenFlash={until:0,start:0,color:RGB.white,alpha:0};
function addFlash(color,alpha,ms){const now=performance.now();screenFlash={until:now+ms,start:now,color,alpha};}
// Two layers for every light: a normal-blend tint (a light added to a white mat stays white,
// so on bright tables this is what shows) and the additive glow (what shines on dark tables).
const dark=c=>c.map(v=>Math.round(v*.55));
function glow(context,x,y,r,color,a){
  if(r<=0||a<=0)return;context.save();
  const t=context.createRadialGradient(x,y,0,x,y,r);t.addColorStop(0,rgba(color,a*.32));t.addColorStop(1,rgba(color,0));
  context.fillStyle=t;context.fillRect(x-r,y-r,r*2,r*2);
  const g=context.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,rgba([255,255,255],a));g.addColorStop(.25,rgba(color,a*.8));g.addColorStop(1,rgba(color,0));
  context.globalCompositeOperation='lighter';context.fillStyle=g;context.fillRect(x-r,y-r,r*2,r*2);context.restore();
}
// Strokes the current path twice: a darker, wider normal-blend line, then the additive one.
function litStroke(context,color,a,lw){
  if(a<=0)return;context.save();context.globalCompositeOperation='source-over';context.strokeStyle=rgba(dark(color),a*.75);context.lineWidth=lw*1.9;context.stroke();
  context.globalCompositeOperation='lighter';context.strokeStyle=rgba(color,a);context.lineWidth=lw;context.stroke();context.restore();
}
// Point on the card plane at angle a and radius r (in card half-widths), as the camera sees it.
function onPlane(g,a,r){return g.H(.5+.44*r*Math.cos(a),.5+.3*r*Math.sin(a));}
function planePath(context,g,pts){context.beginPath();pts.forEach(([a,r],i)=>{const [x,y]=onPlane(g,a,r);i?context.lineTo(x,y):context.moveTo(x,y);});context.closePath();}
// Light pillar: three layered vertical gradients (outer colour, mid, white core).
function beam(context,x,bottom,height,width,color,a){
  if(a<=0||height<=0)return;context.save();
  const tint=context.createLinearGradient(0,bottom,0,bottom-height);tint.addColorStop(0,rgba(color,a*.3));tint.addColorStop(1,rgba(color,0));
  context.fillStyle=tint;context.fillRect(x-width*.35,bottom-height,width*.7,height);
  context.globalCompositeOperation='lighter';
  for(const [w,c,k] of [[width,color,.55],[width*.45,color,.8],[width*.14,[255,255,255],.9]]){
    const g=context.createLinearGradient(0,bottom,0,bottom-height);g.addColorStop(0,rgba(c,a*k));g.addColorStop(.6,rgba(c,a*k*.45));g.addColorStop(1,rgba(c,0));
    context.fillStyle=g;context.fillRect(x-w/2,bottom-height,w,height);
  }
  context.restore();
}
// Magic circle on the card plane: two counter-rotating rings, rune ticks and a hexagram.
function magicCircle(context,g,now,color,size,a,opts={}){
  if(a<=0)return;const spin=now/(opts.slow?5200:2600);
  context.save();context.lineCap='round';
  const lw=Math.max(1.5,g.width/40);
  planeEllipse(context,g.H,size);litStroke(context,color,a,lw*1.3);
  planeEllipse(context,g.H,size*.82);litStroke(context,color,a*.7,lw*.8);
  context.beginPath();for(let k=0;k<24;k++){const ang=spin+k*Math.PI/12,[x0,y0]=onPlane(g,ang,size*.84),[x1,y1]=onPlane(g,ang,size*(k%3?.92:.98));context.moveTo(x0,y0);context.lineTo(x1,y1);}
  litStroke(context,color,a*.85,lw);
  if(opts.hexagram!==false)for(const off of [0,Math.PI/3]){planePath(context,g,[0,1,2].map(i=>[-spin*.7+off+i*2*Math.PI/3,size*.8]));litStroke(context,color,a*.55,lw*.8);}
  context.restore();
}
function shockwave(context,g,t,color,from=.3,to=2.3){
  if(t<=0||t>=1)return;planeEllipse(context,g.H,from+(to-from)*ease.out(t));litStroke(context,color,(1-t)*.9,Math.max(1,g.width/14*(1-t)));
}

// ---- figuras en reposo ----
function drawBase(context,g,kind,rival,now,seed){
  const c=ownerColor(kind,rival);
  // Contact shadow, then a soft pool of light on the card and the kind's emblem.
  context.save();const [cx,cy]=g.center,sh=context.createRadialGradient(cx,cy,0,cx,cy,g.width*.62);
  sh.addColorStop(0,'rgba(0,0,0,.45)');sh.addColorStop(1,'rgba(0,0,0,0)');context.fillStyle=sh;planeEllipse(context,g.H,1.05);context.fill();context.restore();
  glow(context,cx,cy,g.width*.55,c,.16+.05*Math.sin(now/600+seed));
  if(kind==='monster'){
    context.save();context.lineCap='round';
    planeEllipse(context,g.H,1.02);litStroke(context,c,.55,Math.max(1.5,g.width/32));
    // Two energy arcs chasing each other around the ring.
    for(let k=0;k<2;k++){const a0=now/900+seed+k*Math.PI;
      context.beginPath();for(let i=0;i<=10;i++){const [x,y]=onPlane(g,a0+i*.09,1.02);i?context.lineTo(x,y):context.moveTo(x,y);}litStroke(context,c,.9,Math.max(2,g.width/22));}
    context.restore();
  }else if(kind==='spell')magicCircle(context,g,now+seed*500,c,1.05,.5,{slow:true});
  else{
    const pulse=.45+.4*Math.abs(Math.sin(now/300+seed)),lw=Math.max(1.5,g.width/28);
    planePath(context,g,[0,1,2,3,4,5].map(i=>[Math.PI/6+i*Math.PI/3,1.05]));litStroke(context,c,pulse,lw);
    planePath(context,g,[0,1,2,3,4,5].map(i=>[Math.PI/6+i*Math.PI/3,.78]));litStroke(context,c,pulse*.5,lw);
  }
  // Ambient motes rising from the card.
  if(Math.random()<.05){const [x,y]=onPlane(g,Math.random()*6.28,Math.random()*.9);
    emit({x,y,vx:(Math.random()-.5)*.004*g.width/100,vy:-(.02+.03*Math.random())*g.width/100,life:1400+Math.random()*900,size:g.width*(.018+.02*Math.random()),color:c,fadeIn:.25});}
}
function figureSize(img,g,kind,defense){const height=g.width*(kind==='monster'?(defense?.95:1.25):1.05);return [height*img.width/img.height,height];}
function drawSpellTrap(context,item,kind,now){
  const {track,g}=item,img=cutouts.get(track.sprite_ref);if(!img)return;
  const seed=(Number(track.track_id)||0)%1000,c=RGB[kind];let [width,height]=figureSize(img,g,kind,false);
  const act=effectOf('activate',track.track_id,now);let [x,y]=g.center,alpha=.95,rot=0,scale=1,flash=0,lift=0;
  if(kind==='spell'){lift=Math.sin(now/900+seed)*.05*height;}          // calm hover
  else{rot=Math.sin(now/170+seed)*.018;x+=Math.sin(now/90+seed)*.004*height;}   // restless: a trap is waiting
  if(act){const t=(now-act.start)/act.duration;
    if(kind==='spell'){const u=span(t,.15,.55);scale=.4+.6*ease.back(u);alpha*=u;lift+=height*.25*(1-ease.out(span(t,.15,.9)));flash=1-span(t,.3,.8);}
    else{const u=span(t,0,.35);scale=.3+.7*ease.back(u);alpha*=u;rot+=Math.sin(t*60)*.08*(1-t);flash=1-span(t,.15,.6);}}
  const top=Math.max(0,y-height*.12-lift-height*scale/2);
  drawFigure(context,img,x,top+height*scale/2,width,height,{alpha,rot,scale,glow:KIND_COLOR[kind],glowAlpha:.6,flash});
}
function drawMonster(context,item,now){
  const {track,g}=item,img=cutouts.get(track.sprite_ref);if(!img)return;
  const card=boardCard(track.track_id),position=card?.position;
  if(position==='facedown_defense'||position==='facedown')return;
  const kind=kindOf(track);if(kind!=='monster')return drawSpellTrap(context,item,kind,now);
  const defense=position==='defense',rival=card?.controller===1,seed=(Number(track.track_id)||0)*1.7,c=ownerColor('monster',rival);
  let [width,height]=figureSize(img,g,'monster',defense);
  let [x,y]=g.center,alpha=defense?.85:1,scale=1,squash=1,flash=0,rot=Math.sin(now/950+seed)*.03;
  // Summon: appears at 30 % of the sequence with an overshoot and a white flash.
  const summon=effectOf('summon',track.track_id,now);
  if(summon){const t=(now-summon.start)/summon.duration,u=span(t,.3,.62);scale=.5+.5*ease.back(u);alpha*=clamp(u*2);flash=1-span(t,.35,.85);if(u<=0)return;}
  // Attack: wind-up, dash (with after-images), hold, return.
  const attack=effects.find(e=>e.kind==='attack'&&e.attacker===track.track_id&&now-e.start<e.duration);
  if(attack){
    const t=(now-attack.start)/attack.duration,[tx,ty]=attack.to,dx=tx-x,dy=ty-y;
    const k=t<.2?-.12*ease.out(t/.2):t<.42?-.12+.92*ease.in(span(t,.2,.42)):t<.58?.8:.8*(1-ease.out(span(t,.58,1)));
    if(t>.2&&t<.46){for(let i=3;i>=1;i--){const kk=Math.max(-.12,k-i*.12);
      drawFigure(context,img,x+dx*kk,y+dy*kk-height*.12,width,height,{alpha:.18*i/3,glow:rgba(c,1),glowAlpha:.5});}}
    x+=dx*k;y+=dy*k;rot+=(t<.2?-.12:t<.46?.1:0)*Math.sign(dx||1);squash=t<.2?.94:t<.46?1.06:1;
  }
  const bob=Math.sin(now/650+seed)*.035*height,breathe=1+Math.sin(now/520+seed)*.015;
  const top=Math.max(0,y-height*.12-bob-height/2);
  drawFigure(context,img,x,top+height/2,width,height,{alpha,rot,scale:scale*breathe,squash:squash/breathe,glow:rgba(c,1),glowAlpha:rival?.45:.5,flash});
  if(defense){
    // Translucent hex shield in front, with a highlight sweeping across it.
    const s=g.width*.3,[cx,cy]=[x,g.center[1]+g.width*.28];context.save();
    const grad=context.createLinearGradient(cx-s,cy-s,cx+s,cy+s);grad.addColorStop(0,'rgba(90,170,255,.18)');grad.addColorStop(1,'rgba(40,90,200,.32)');
    hexPath(context,cx,cy,s);context.fillStyle=grad;context.fill();
    context.globalCompositeOperation='lighter';context.strokeStyle='rgba(150,205,255,.85)';context.lineWidth=Math.max(1.5,g.width/34);context.stroke();
    context.clip();const sweep=((now/1600+seed)%1)*s*4-s*2;const h=context.createLinearGradient(cx+sweep-s*.3,0,cx+sweep+s*.3,0);
    h.addColorStop(0,'rgba(255,255,255,0)');h.addColorStop(.5,'rgba(220,240,255,.35)');h.addColorStop(1,'rgba(255,255,255,0)');context.fillStyle=h;context.fillRect(cx-s,cy-s,s*2,s*2);context.restore();
  }
}

function drawStage(context,tracks,now){
  const dt=lastFrame?Math.min(64,now-lastFrame):16;lastFrame=now;stepParticles(dt);
  // Every card on the field is remembered (activation effects need its place, sprite or not).
  for(const t of tracks)if(t.corners?.length===4)lastSeen.set(t.track_id,{g:geometry(t),sprite_ref:t.sprite_ref,name:t.name,kind:kindOf(t),rival:boardCard(t.track_id)?.controller===1});
  const items=tracks.filter(t=>t.sprite_ref&&t.corners?.length===4).map(track=>({track,g:geometry(track)}));
  const [sx,sy]=shakeOffset(now);context.save();context.translate(sx,sy);
  for(const {track,g} of items){
    const card=boardCard(track.track_id);if(card?.position==='facedown_defense'||card?.position==='facedown')continue;
    drawBase(context,g,kindOf(track),card?.controller===1,now,(Number(track.track_id)||0)%1000);
  }
  drawEffects(context,now,'under');
  for(const item of items.sort((a,b)=>a.g.center[1]-b.g.center[1]))drawMonster(context,item,now);
  drawEffects(context,now,'over');drawParticles(context);
  context.restore();
  if(now<screenFlash.until){const a=screenFlash.alpha*(1-(now-screenFlash.start)/(screenFlash.until-screenFlash.start));
    context.save();context.globalCompositeOperation='lighter';context.fillStyle=rgba(screenFlash.color,a);context.fillRect(0,0,frame.width,frame.height);context.restore();}
}

// ---- secuencias de cada evento ----
// Each effect is drawn in two layers: 'under' (on the table, below the figures) and 'over'.
// The first frame of an effect spawns its particles and camera shake (e.fired).
function zoneGeometry(player,zone){
  const board=virtualPreview||playmat,z=board?.zones?.find(z=>z.player===player&&z.zone===zone);
  if(!z)return null;const H=cardMap(z.polygon),l=H(0,.5),r=H(1,.5);return {H,center:H(.5,.5),width:Math.hypot(r[0]-l[0],r[1]-l[1])*.72};
}
function drawEffects(context,now,layer){
  for(let i=effects.length-1;i>=0;i--){
    const e=effects[i],t=(now-e.start)/e.duration;
    if(t>=1){if(layer==='over')effects.splice(i,1);continue;}
    if(t<0)continue;
    const seen=e.g?{g:e.g}:lastSeen.get(e.copy),g=seen?.g;
    if(e.kind==='summon'&&g){
      const c=e.rival?RGB.rival:RGB.monster,[x,y]=g.center;
      if(!e.fired&&t>.3){e.fired=true;addShake(g.width*.035,260);
        burst(40,()=>{const a=Math.random()*6.28,v=(.08+.18*Math.random())*g.width/100;return {x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v*.55,life:500+Math.random()*400,size:g.width*.02,color:c,shape:'spark',trail:40,drag:.004};});
        burst(34,()=>{const a=Math.random()*6.28,[px,py]=onPlane(g,a,.3+.7*Math.random());return {x:px,y:py,vx:Math.cos(a)*.01*g.width/100,vy:-(.06+.12*Math.random())*g.width/100,life:900+Math.random()*700,size:g.width*(.02+.025*Math.random()),color:c,fadeIn:.1};});}
      if(layer==='under'){
        magicCircle(context,g,now,c,.3+.9*ease.out(span(t,0,.35)),(1-span(t,.7,1))*.95);
        glow(context,x,y,g.width*(.4+.9*ease.out(span(t,0,.4))),c,.5*(1-span(t,.6,1)));
        shockwave(context,g,span(t,.3,.75),c);
      }else{
        const up=ease.out(span(t,.12,.4)),down=1-span(t,.55,1);
        beam(context,x,y,Math.min(y,g.width*2.4)*up,g.width*1.05,c,down*.9);
        glow(context,x,y-g.width*.5,g.width*.9,[255,255,255],.35*(1-span(t,.3,.7))*span(t,.25,.32));
      }
    }
    else if(e.kind==='activate'&&g){
      const trap=e.type==='trap',c=trap?RGB.trap:RGB.spell,[x,y]=g.center;
      if(!e.fired){e.fired=true;
        if(trap){addShake(g.width*.05,300);addFlash(RGB.trap,.12,220);
          burst(36,()=>{const a=Math.random()*6.28,v=(.12+.2*Math.random())*g.width/100;return {x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v*.6,life:420+Math.random()*300,size:g.width*.018,color:c,shape:'spark',trail:30,drag:.005};});}
        else burst(30,()=>{const [px,py]=onPlane(g,Math.random()*6.28,Math.random()*1.1);return {x:px,y:py,vx:(Math.random()-.5)*.02*g.width/100,vy:-(.05+.1*Math.random())*g.width/100,life:1100+Math.random()*600,size:g.width*.03,color:c,shape:'glyph',spin:(Math.random()-.5)*.01,fadeIn:.15};});}
      if(layer==='under'){
        if(trap){
          // The hexagon snaps shut, chains whip out from it.
          const s=1.5-.45*ease.back(span(t,0,.3)),a=1-span(t,.6,1);context.save();
          planePath(context,g,[0,1,2,3,4,5].map(k=>[Math.PI/6+k*Math.PI/3,s]));litStroke(context,c,a,Math.max(2,g.width/18));
          context.setLineDash([g.width/9,g.width/14]);
          for(let k=0;k<6;k++){const ang=k*Math.PI/3+.3,len=1.2+1.3*ease.out(span(t,.1,.5));context.beginPath();
            for(let j=0;j<=8;j++){const r=len*j/8,[px,py]=onPlane(g,ang+Math.sin(j*.9+t*8)*.08,r);j?context.lineTo(px,py):context.moveTo(px,py);}litStroke(context,c,a*.9,Math.max(2,g.width/26));}
          context.restore();glow(context,x,y,g.width*(.5+1.2*ease.out(span(t,0,.3))),c,.55*(1-span(t,.2,.8)));
        }else{magicCircle(context,g,now,c,.4+1.1*ease.back(span(t,0,.45)),1-span(t,.7,1));glow(context,x,y,g.width*1.2,c,.35*(1-span(t,.5,1)));}
      }else if(!trap)beam(context,x,y,Math.min(y,g.width*1.8)*ease.out(span(t,.1,.45)),g.width*.8,c,.6*(1-span(t,.5,1)));
    }
    else if(e.kind==='set'&&g&&layer==='under'){
      // Face-down: the card back's swirl gathers into the zone.
      const [x,y]=g.center;
      if(!e.fired){e.fired=true;burst(26,()=>{const a=Math.random()*6.28,[px,py]=onPlane(g,a,1.6);return {x:px,y:py,vx:(x-px)/650,vy:(y-py)/650,life:650,size:g.width*.025,color:RGB.back,drag:0};});}
      context.save();context.lineCap='round';
      for(let k=0;k<3;k++){context.beginPath();
        for(let j=0;j<=24;j++){const a=now/300+k*2.1+j*.18,r=(1.4-1.2*ease.out(t))*(1-j/30),[px,py]=onPlane(g,a,r);j?context.lineTo(px,py):context.moveTo(px,py);}
        litStroke(context,RGB.back,(1-t)*.8,Math.max(1.5,g.width/30));}
      context.restore();glow(context,x,y,g.width*.8,RGB.back,.4*span(t,.5,.8)*(1-span(t,.8,1)));
    }
    else if(e.kind==='impact'&&layer==='over'){
      const [x,y]=e.at,c=e.color||RGB.fire;
      if(!e.fired){e.fired=true;addShake(e.size*.06,320);addFlash(RGB.white,.18,160);
        burst(46,()=>{const a=Math.random()*6.28,v=(.2+.45*Math.random())*e.size/100;return {x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,life:350+Math.random()*350,size:e.size*.022,color:Math.random()<.5?c:RGB.white,shape:'spark',trail:35,drag:.006,gravity:.0006*e.size/100};});
        burst(16,()=>{const a=Math.random()*6.28;return {x,y,vx:Math.cos(a)*.05*e.size/100,vy:Math.sin(a)*.05*e.size/100-.02,life:800,size:e.size*.05,color:c,grow:1.2};});}
      glow(context,x,y,e.size*(.4+1.1*ease.out(t)),c,.9*(1-t));
      context.beginPath();context.ellipse(x,y,e.size*1.4*ease.out(t),e.size*.8*ease.out(t),0,0,Math.PI*2);litStroke(context,c,1-t,Math.max(1,e.size/20*(1-t)));
    }
    else if(e.kind==='destroy'&&e.image&&layer==='over'){
      // Shatters: fragments fly with gravity and burn out, embers rise, smoke spreads.
      const img=e.image,[width,height]=figureSize(img,e.g,'monster',false),x=e.g.center[0],y=Math.max(height/2,e.g.center[1]-height*.12),n=6;
      if(!e.fired){e.fired=true;addShake(e.g.width*.03,220);
        burst(10,()=>({x:x+(Math.random()-.5)*width*.6,y:y+(Math.random()-.3)*height*.5,vx:(Math.random()-.5)*.02,vy:-.015,life:1100,size:e.g.width*.35,shape:'smoke',color:[0,0,0]}));
        burst(40,()=>({x:x+(Math.random()-.5)*width,y:y+(Math.random()-.5)*height,vx:(Math.random()-.5)*.05,vy:-(.02+.08*Math.random()),life:700+Math.random()*700,size:e.g.width*.02,color:RGB.fire,fadeIn:.05}));}
      const k=ease.out(span(t,0,1)),burn=span(t,.1,.9);
      context.save();
      for(let r=0;r<n;r++)for(let q=0;q<n;q++){
        const sx=img.width*q/n,sy=img.height*r/n,sw=img.width/n,sh=img.height/n,seedK=((r*7+q*13)%10)/10;
        const dx=(q-(n-1)/2)*width/n*1.8*k*(.7+seedK*.6),dy=-height/2+(r+.5)*height/n-e.g.width*.4*k*(1-seedK)+e.g.width*2.2*t*t;
        context.save();context.globalAlpha=1-burn;context.translate(x+dx,y+dy);context.rotate((q-r+seedK)*1.4*k);
        context.drawImage(img,sx,sy,sw,sh,-width/n/2,-height/n/2,width/n,height/n);
        context.globalCompositeOperation='lighter';context.globalAlpha=(1-burn)*.6*span(t,0,.25);
        context.drawImage(silhouette(img,'#ff9a3c',0).canvas,sx,sy,sw,sh,-width/n/2,-height/n/2,width/n,height/n);context.restore();
      }
      context.restore();glow(context,x,y,e.g.width*1.2,RGB.fire,.5*(1-span(t,0,.4)));
    }
    else if(e.kind==='lp'&&layer==='over'){
      const [x,y]=hudAnchor(e.player),hurt=e.delta<0,c=hurt?RGB.hurt:RGB.heal;
      if(!e.fired){e.fired=true;hud.flash[e.player]=now;hud.flashColor[e.player]=hurt?'#ff5a5a':'#6bff9e';if(hurt&&Math.abs(e.delta)>=1000)addShake(frame.width*.004,300);
        burst(24,()=>{const a=Math.random()*6.28,v=.1+.25*Math.random();return {x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,life:600,size:frame.width*.004,color:c,shape:'spark',trail:25,drag:.005};});}
      const dir=e.player===0?-1:1,pop=ease.back(span(t,0,.25)),size=Math.round(frame.width/24*(.6+.4*pop));
      context.save();context.globalAlpha=1-span(t,.7,1);context.font=`900 ${size}px system-ui`;context.textAlign='center';
      const ty=y+dir*(frame.height*.1+frame.height*.05*ease.out(t)),text=(e.delta>0?'+':'')+e.delta;
      context.lineWidth=Math.max(4,size/7);context.strokeStyle='rgba(0,0,0,.75)';context.strokeText(text,x,ty);
      context.shadowColor=rgba(c,1);context.shadowBlur=size/2;context.fillStyle=rgba(c,1);context.fillText(text,x,ty);context.restore();
    }
  }
}

// LP boxes in opposite corners: the near player bottom-left, the opponent top-right (the phase bar is top centre).
function hudAnchor(player){return player===0?[frame.width*.13,frame.height*.93]:[frame.width*.87,frame.height*.08];}
function drawHud(context,now){
  const view=duelView;if(!view?.started)return;
  view.players.forEach((p,i)=>{
    const shown=hud.lp[i]??p.lp;hud.lp[i]=Math.abs(shown-p.lp)<1?p.lp:shown+(p.lp-shown)*.08;
    const [ax,ay]=hudAnchor(i),w=frame.width*.2,h=frame.height*.085,since=now-(hud.flash[i]||-1e9);
    const jolt=since<400?Math.sin(since*.09)*frame.width*.004*(1-since/400):0,x=ax+jolt,y=ay,current=i===view.current;
    const accent=i===0?RGB.monster:RGB.rival;
    context.save();
    if(current)glow(context,x,y,w*.75,accent,.18+.06*Math.sin(now/500));
    const bg=context.createLinearGradient(x-w/2,y-h/2,x+w/2,y+h/2);bg.addColorStop(0,'rgba(14,22,40,.88)');bg.addColorStop(1,'rgba(6,10,20,.82)');
    context.fillStyle=bg;context.beginPath();context.roundRect?context.roundRect(x-w/2,y-h/2,w,h,h*.22):context.rect(x-w/2,y-h/2,w,h);context.fill();
    context.lineWidth=Math.max(1.5,h/30);context.strokeStyle=current?rgba(accent,.95):'rgba(150,175,215,.45)';context.stroke();
    if(since<600){context.save();context.globalCompositeOperation='lighter';context.globalAlpha=.4*(1-since/600);context.fillStyle=hud.flashColor[i];context.fill();context.restore();}
    // Life bar under the number (8000 = full).
    const frac=clamp(hud.lp[i]/8000),bw=w*.82,bx=x-bw/2,by=y+h*.3,bh=h*.07;
    context.fillStyle='rgba(255,255,255,.1)';context.fillRect(bx,by,bw,bh);
    const lg=context.createLinearGradient(bx,0,bx+bw,0);lg.addColorStop(0,frac<.3?'#ff5a5a':'#5ff2ff');lg.addColorStop(1,frac<.3?'#ffb35c':'#8dffc8');
    context.fillStyle=lg;context.fillRect(bx,by,bw*frac,bh);
    context.textAlign='center';context.fillStyle='#9fb0c9';context.font=`600 ${Math.round(h*.22)}px system-ui`;context.fillText(p.name,x,y-h*.2);
    context.fillStyle='#f2f8ff';context.font=`800 ${Math.round(h*.4)}px system-ui`;context.fillText(`${Math.round(hud.lp[i])}`,x-h*.18,y+h*.2);
    context.fillStyle=rgba(accent,.9);context.font=`700 ${Math.round(h*.2)}px system-ui`;context.textAlign='left';context.fillText('LP',x+context.measureText(`${Math.round(hud.lp[i])}`).width*1.25-h*.1,y+h*.2);
    context.restore();
  });
}

// Effects come from what changed in the duel, never from the camera alone.
function stageEvents(prev,next){
  if(!prev||!next||!document.querySelector('#fx').checked)return;const now=performance.now();
  const before=new Map((prev.board||[]).map(c=>[c.copy_id,c])),after=new Map((next.board||[]).map(c=>[c.copy_id,c]));
  for(const [id,c] of after){
    if(before.has(id))continue;
    if(c.zone.includes('monster')&&c.position!=='facedown_defense')effects.push({kind:'summon',copy:id,rival:c.controller===1,start:now,duration:1300});
    else if(c.position==='facedown_defense'||c.position==='facedown'){const g=zoneGeometry(c.player,c.zone);if(g)effects.push({kind:'set',g,start:now,duration:900});}
  }
  // Spells and Traps turned face-up (placed face-up, or a set card revealed under its face's track).
  for(const [id,c] of after){
    if(!/^spell:|^field$/.test(c.zone)||c.position!=='faceup')continue;
    const was=before.get(id);if(was&&was.position==='faceup')continue;
    const sheet=sheetOf(c.card_id),type=sheet?.card_type==='trap'||/^Trampa/.test(c.type||'')?'trap':'spell';
    effects.push({kind:'activate',copy:id,type,start:now,duration:type==='trap'?1000:1400});
  }
  for(const [id,c] of before)if(!after.has(id)){
    const seen=lastSeen.get(id),image=seen&&cutouts.get(seen.sprite_ref);
    if(seen&&image&&c.zone.includes('monster'))effects.push({kind:'destroy',copy:id,g:seen.g,image,start:now,duration:1100});
  }
  if(prev.pending_attack&&!next.pending_attack){
    const {attacker,target}=prev.pending_attack,from=lastSeen.get(attacker),to=target!=null?lastSeen.get(target):null;
    if(from){
      const aim=to?to.g.center:[from.g.center[0],from.g.center[1]-from.g.width*4];
      effects.push({kind:'attack',attacker,to:aim,start:now,duration:900});
      effects.push({kind:'impact',at:aim,size:from.g.width*1.6,color:from.rival?RGB.rival:RGB.fire,start:now+900*.42,duration:650});
    }
  }
  (next.players||[]).forEach((p,i)=>{const old=prev.players?.[i]?.lp;if(old!=null&&old!==p.lp)effects.push({kind:'lp',player:i,delta:p.lp-old,start:now,duration:1600});});
}

draw();refreshCamera();followAnalysis();
