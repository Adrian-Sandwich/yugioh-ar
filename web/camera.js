const frame=document.querySelector('#frame'),ctx=frame.getContext('2d');
async function refreshDownloadWatch(){
  const label=document.querySelector('#downloadWatch');if(!label)return;
  try{
    const response=await fetch('/download-status',{cache:'no-store'});if(!response.ok)throw new Error('status');
    const d=await response.json(),age=Date.now()-Date.parse(d.watch_checked_at);
    if(d.watch_state==='complete_pending_content_audit')label.textContent='Neuron: descarga e importación completas; falta auditoría del contenido.';
    else if(d.watch_state==='finished_with_pending_work')label.textContent=`Neuron: proceso terminado con pendientes (${d.remaining_files} fichas por descargar).`;
    else if(!Number.isFinite(age)||age>180000||d.watch_state==='stale_progress')label.textContent='Neuron: monitor sin actualización reciente; revisar el estado.';
    else if(d.watch_state==='downloading')label.textContent=`Neuron: ${d.percent}% · ${d.cached_detail_files.toLocaleString()} / ${d.total_discovered.toLocaleString()} fichas · ${(d.current_run_errors||[]).length} errores registrados`;
    else label.textContent=`Neuron: ${d.watch_state==='stopped'?'descarga detenida':d.watch_state==='access_blocked'?'acceso bloqueado':'monitor no disponible'}.`;
  }catch(e){label.textContent='No se pudo consultar el monitor de descarga.';}
  finally{setTimeout(refreshDownloadWatch,30000);}
}
refreshDownloadWatch();
const status=document.querySelector('#status'),pause=document.querySelector('#pause'),save=document.querySelector('#save');
const recognize=document.querySelector('#recognize'),ar=document.querySelector('#ar'),detection=document.querySelector('#detection');
let paused=false,offline=false,currentBlob=null,currentBitmap=null,frameAt=0,frameNumber=0;
let frameCapturedAt=0;
const sharedAnalysis=globalThis.BroadcastChannel&&navigator.locks?new BroadcastChannel('yugioh-analysis-v1'):null;
let sharedCooldown=0;
let result=null,resultAt=0,generation=0,configured=false,lastAnalyzed=-1;
const overlayMaxAge=2500;
let renderedFrame=-1,renderedResult=null,renderedAR=false,renderedTracks=null;
// Tracks arrive with every frame (X-Tracks header): corners followed by the server between analyses.
let liveTracks=[];
const analysisView=document.querySelector('#analysisView'),analysisFrame=document.querySelector('#analysisFrame');
let lastAnalysis=null,lastAnalysisAt=0,analysisPaint=0;
let passcodeMinCapturedAt=0;
// Diagnostic history only: never feeds identities or stale geometry into live AR.
// Declared here because clearRecognition() resets it.
let qualityTracks=[],qualityNextId=1;
const qualityWindow=10000;
// Duel on the playmat: zone outlines from /playmat, calibration clicks in progress.
let playmat=null,calibration=null,zonesVersion=0,renderedZones=-1;

// Sprites are warped in the browser: a WebGL textured quad with perspective-correct
// texture coordinates, so nothing but corners and a sprite id travel per frame.
const sprites={cache:new Map(),
  get(url){
    if(!url)return null;
    let entry=this.cache.get(url);
    if(!entry){entry={image:null,failed:false};this.cache.set(url,entry);const img=new Image();img.onload=()=>{entry.image=img;};img.onerror=()=>{entry.failed=true;};img.src=url;}
    return entry.image;
  }};
const spriteGL=(()=>{
  const canvas=document.createElement('canvas');const gl=canvas.getContext('webgl',{premultipliedAlpha:false,preserveDrawingBuffer:true});
  if(!gl)return null;
  const compile=(type,src)=>{const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);return s;};
  const program=gl.createProgram();
  gl.attachShader(program,compile(gl.VERTEX_SHADER,'attribute vec2 p;attribute vec3 t;varying vec3 v;uniform vec2 size;void main(){v=t;gl_Position=vec4(p.x/size.x*2.0-1.0,1.0-p.y/size.y*2.0,0.0,1.0);}'));
  gl.attachShader(program,compile(gl.FRAGMENT_SHADER,'precision mediump float;varying vec3 v;uniform sampler2D s;void main(){gl_FragColor=texture2D(s,v.xy/v.z);}'));
  gl.linkProgram(program);gl.useProgram(program);
  const pos=gl.createBuffer(),tex=gl.createBuffer();
  const aP=gl.getAttribLocation(program,'p'),aT=gl.getAttribLocation(program,'t'),uSize=gl.getUniformLocation(program,'size');
  gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
  const textures=new Map();
  function texture(image){
    let t=textures.get(image);
    if(t)return t;
    t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,false);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    textures.set(image,t);return t;
  }
  // Perspective-correct quad: q per corner from the diagonal intersection (Heckbert).
  function weights(c){
    const [a,b,cc,d]=c;const den=(cc[0]-a[0])*(d[1]-b[1])-(cc[1]-a[1])*(d[0]-b[0]);
    if(Math.abs(den)<1e-6)return [1,1,1,1];
    const s=((b[0]-a[0])*(d[1]-b[1])-(b[1]-a[1])*(d[0]-b[0]))/den;
    const x=[a[0]+s*(cc[0]-a[0]),a[1]+s*(cc[1]-a[1])];
    const dist=c.map(p=>Math.hypot(p[0]-x[0],p[1]-x[1]));
    return dist.map((di,i)=>{const dj=dist[(i+2)%4];return dj>1e-6?(di+dj)/dj:1;});
  }
  return {
    draw(width,height,items){
      if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}
      gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.uniform2f(uSize,width,height);
      let drawn=0;
      for(const {corners,image} of items){
        if(!image||corners?.length!==4)continue;
        const q=weights(corners);
        // Corner order follows the card: top-left, top-right, bottom-right, bottom-left.
        const uv=[[0,0],[1,0],[1,1],[0,1]];const order=[0,1,2,0,2,3];
        gl.bindBuffer(gl.ARRAY_BUFFER,pos);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(order.flatMap(i=>corners[i])),gl.STREAM_DRAW);
        gl.enableVertexAttribArray(aP);gl.vertexAttribPointer(aP,2,gl.FLOAT,false,0,0);
        gl.bindBuffer(gl.ARRAY_BUFFER,tex);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(order.flatMap(i=>[uv[i][0]*q[i],uv[i][1]*q[i],q[i]])),gl.STREAM_DRAW);
        gl.enableVertexAttribArray(aT);gl.vertexAttribPointer(aT,3,gl.FLOAT,false,0,0);
        gl.bindTexture(gl.TEXTURE_2D,texture(image));gl.drawArrays(gl.TRIANGLES,0,6);drawn++;
      }
      return drawn?canvas:null;
    }};
})();
function drawSprites(context,cards,width,height){
  if(!spriteGL||!ar.checked)return 0;
  const items=(cards||[]).filter(c=>c.corners?.length===4&&(c.sprite_url||c.sprite_ref)).map(c=>({corners:c.corners,image:sprites.get(c.sprite_url||('/sprite/'+c.sprite_ref))}));
  const layer=spriteGL.draw(width,height,items);
  if(layer)context.drawImage(layer,0,0,width,height);
  return items.filter(i=>i.image).length;
}

function drawCards(context,cards,options={}){
  for(const card of cards||[]){
    if(!card.corners?.length)continue;
    const cut=card.geometry_status==='frame_edge';
    // 'tracked': corners followed by the tracker from an earlier refined analysis.
    const approximate=card.geometry_status&&!['contour_refined','tracked'].includes(card.geometry_status);
    context.save();context.setLineDash(approximate?[12,8]:[]);
    context.beginPath();card.corners.forEach(([x,y],i)=>i?context.lineTo(x,y):context.moveTo(x,y));context.closePath();context.strokeStyle=cut&&options.hints?'#ff8f8f':approximate?'#ffd166':'#80ffbc';context.lineWidth=5;context.stroke();context.restore();
    // Spanish name plus the English one when it differs (most TCG copies are printed in English).
    const en=card.card_id&&typeof sheets!=='undefined'?sheets.get(card.card_id)?.name_en:null;
    const label=card.name?(en&&en!==card.name?`${card.name} · ${en}`:card.name):(cut&&options.hints?'Carta cortada por el borde: muévela dentro del cuadro':null);
    if(!label)continue;
    const x=Math.max(0,Math.min(...card.corners.map(p=>p[0]))),y=Math.max(32,Math.min(...card.corners.map(p=>p[1]))-10);
    context.font='bold 25px system-ui';context.fillStyle='#10141d';context.fillRect(x,y-29,context.measureText(label).width+16,36);context.fillStyle=cut&&!card.name?'#ff8f8f':'#80ffbc';context.fillText(label,x+8,y);
  }
}

async function paintAnalysis(data,token=generation){
  const ticket=++analysisPaint;
  if(!data.image)return;
  const bitmap=await createImageBitmap(await (await fetch(data.image)).blob());
  if(ticket!==analysisPaint||token!==generation||paused){bitmap.close();return;}
  analysisFrame.width=bitmap.width;analysisFrame.height=bitmap.height;
  const context=analysisFrame.getContext('2d');context.drawImage(bitmap,0,0);bitmap.close();
  // Sprites of the same analysis, warped here over the original JPEG.
  drawSprites(context,(data.detections||[]).filter(d=>d.stable),analysisFrame.width,analysisFrame.height);
  drawCards(context,(data.candidates||[]).filter(c=>!c.accepted&&c.geometry_status==='frame_edge'),{hints:true});
  drawCards(context,data.detections);
  analysisView.hidden=false;
  const cut=(data.candidates||[]).filter(c=>!c.accepted&&c.geometry_status==='frame_edge').length;
  document.querySelector('#analysisNames').textContent=((data.detections||[]).map(c=>c.name).join(' / ')||'Sin coincidencia aceptada')+(cut?` · ${cut} carta${cut>1?'s':''} cortada${cut>1?'s':''} por el borde del cuadro`:'');
}
ar.onchange=()=>{if(lastAnalysis)paintAnalysis(lastAnalysis).catch(()=>{});};

function clearRecognition(){
  generation++;analysisPaint++;result=null;resultAt=0;liveTracks=[];qualityTracks=[];
  passcodeMinCapturedAt=Date.now()/1000;
  document.querySelector('#passcodeCards').replaceChildren();
  document.querySelector('#passcodeStatus').textContent='Esperando un nuevo análisis.';
}
pause.onclick=()=>{paused=!paused;pause.textContent=paused?'Reanudar':'Pausar';clearRecognition();if(paused)status.textContent='Imagen pausada';};
recognize.onchange=()=>{clearRecognition();detection.textContent=recognize.checked?'Esperando el siguiente análisis…':'Vista de cámara sin reconocimiento';};
save.onclick=()=>{
  if(!currentBlob)return;
  const url=URL.createObjectURL(currentBlob),a=document.createElement('a');
  a.href=url;a.download=`carta-${new Date().toISOString().replace(/[:.]/g,'-')}.jpg`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};

// Rendering and camera acquisition never wait for model inference.
function draw(){
  const visibleResult=recognize.checked&&result&&performance.now()-resultAt<overlayMaxAge?result:null;
  // Live tracks belong to the current frame; without them, fall back to the last analysis while it is fresh.
  const tracks=recognize.checked&&liveTracks.length?liveTracks:null;
  // Camera delivery is ~5 fps. Repainting the same full-resolution bitmap at
  // display refresh rate wastes CPU; still redraw when an overlay expires.
  if(!paused&&currentBitmap&&(renderedFrame!==frameNumber||renderedResult!==visibleResult||renderedAR!==ar.checked||renderedTracks!==tracks||renderedZones!==zonesVersion)){
    if(frame.width!==currentBitmap.width||frame.height!==currentBitmap.height){frame.width=currentBitmap.width;frame.height=currentBitmap.height;}
    ctx.drawImage(currentBitmap,0,0);
    if(tracks){
      drawSprites(ctx,tracks.filter(t=>t.stable),frame.width,frame.height);
      drawCards(ctx,tracks);
    }else if(visibleResult){
      ctx.save();ctx.scale(frame.width/(result.width||frame.width),frame.height/(result.height||frame.height));
      drawSprites(ctx,(result.detections||[]).filter(d=>d.stable),result.width||frame.width,result.height||frame.height);
      drawCards(ctx,result.detections);
      ctx.restore();
    }
    drawTableOverlay(ctx);
    frame.dataset.frameNumber=String(frameNumber);frame.dataset.tracks=String(tracks?tracks.length:0);
    renderedFrame=frameNumber;renderedResult=visibleResult;renderedAR=ar.checked;renderedTracks=tracks;renderedZones=zonesVersion;
  }
  if(lastAnalysis&&!analysisView.hidden){
    const caption=`Fotograma solicitado hace ${Math.floor((performance.now()-lastAnalysisAt)/1000)} s · análisis ${Math.round(lastAnalysis.processing_ms)} ms · imagen de referencia, no vídeo en vivo`;
    const age=document.querySelector('#analysisAge');if(age.textContent!==caption)age.textContent=caption;
  }
  requestAnimationFrame(draw);
}

async function refreshCamera(){
  // The server serves a cached stream frame, so polling can run faster than the old 200 ms.
  let delay=66;const started=performance.now(),token=generation;
  try{
    if(!paused){
      const response=await fetch('/snapshot?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(10000)});
      if(!response.ok)throw Error('Cámara no disponible');
      const blob=await response.blob(),bitmap=await createImageBitmap(blob);
      if(paused||token!==generation){bitmap.close();return;}
      const timestamp=Number(response.headers.get('X-Captured-At'));
      frameCapturedAt=timestamp>0&&Number.isFinite(timestamp)?timestamp:(performance.timeOrigin+started)/1000;
      let tracks=[];
      try{tracks=JSON.parse(response.headers.get('X-Tracks')||'[]');}catch(e){tracks=[];}
      if(currentBitmap)currentBitmap.close();currentBitmap=bitmap;currentBlob=blob;
      // Tracks belong to exactly this frame; identities in them were confirmed by an earlier analysis.
      liveTracks=Array.isArray(tracks)?tracks.filter(t=>t.card_id&&t.corners?.length===4):[];
      if(liveTracks.length)updateTable(liveTracks).catch(()=>{});
      frameAt=performance.now()-Math.max(0,Date.now()-frameCapturedAt*1000);frameNumber++;
      save.disabled=false;
      status.textContent=`${offline?'Captura guardada':'Cámara en vivo'} · fotograma ${frameNumber} · ${Math.round(performance.now()-started)} ms${liveTracks.length?` · ${liveTracks.length} carta${liveTracks.length>1?'s':''} seguida${liveTracks.length>1?'s':''}`:''}`;
    }
  }catch(e){
    if(token!==generation)return;
    clearRecognition();
    if(!paused)status.textContent='Sin señal de cámara. La imagen es la última recibida. Reintentando…';
    delay=1500;
  }finally{setTimeout(refreshCamera,Math.max(50,delay-(performance.now()-started)));}
}

async function acceptAnalysis(data,token,sourceAt){
    if(paused||!recognize.checked||token!==generation||data.captured_at<passcodeMinCapturedAt)return;
    if(lastAnalysis?.captured_at>data.captured_at)return;
    for(const d of data.detections||[])if(d.sprite_url)sprites.get(d.sprite_url);
    result=data;resultAt=sourceAt;
    lastAnalysis=data;lastAnalysisAt=sourceAt;
    if(!liveTracks.length)updateTable(data.detections).catch(()=>{});
    await paintAnalysis(data,token);
    if(paused||!recognize.checked||token!==generation||lastAnalysis!==data)return;
    try{await paintQuality(data,sourceAt,token);}catch(e){document.querySelector('#qualityStatus').textContent='No se pudo preparar la comparación de reflejos.';}
    if(paused||!recognize.checked||token!==generation||lastAnalysis!==data)return;
    const names=(data.detections||[]).map(c=>`${c.name}${c.track_id?` · objeto ${c.track_id}`:''} · ${c.stable?'confirmada':'detectada'}${c.acceptance==='art_verified'?' · por ilustración verificada':''}${c.identity_source==='track'?' · identidad conservada por seguimiento':''}`).join(' / ');
    const cut=(data.candidates||[]).filter(c=>!c.accepted&&c.geometry_status==='frame_edge').length;
    detection.textContent=`Último análisis: ${names||'sin coincidencia aceptada'} · ${data.processing_ms} ms${data.reused_cards?` · ${data.reused_cards} sin recodificar`:''}${cut?` · ${cut} carta${cut>1?'s':''} cortada${cut>1?'s':''} por el borde`:''}`;
    detection.dataset.completed=String(Number(detection.dataset.completed||0)+1);
}

// "Cartas en la mesa": one sheet per recognized identity, from /card-info (local registry).
const sheets=new Map();let tableKey='';
const formats={tcg:'TCG',ocg:'OCG','ocg-kr':'OCG Corea',speed:'Speed Duel',masterduel:'Master Duel',genesys:'Genesys'};
function sheetNode(info,count){
  const box=document.createElement('article');box.className='sheet';
  box.append(textNode('h3',(count>1?`${count}× `:'')+info.name));
  if(info.name_en&&info.name_en!==info.name){const en=textNode('p',info.name_en);en.className='en';box.append(en);}
  const line=textNode('p',info.line);line.className='line';box.append(line);
  if(info.card_type==='monster'){const stats=textNode('p',info.link?`ATK ${info.atk??'?'} · LINK-${info.link}`:`ATK ${info.atk??'?'} / DEF ${info.def??'?'}`);stats.className='stats';box.append(stats);}
  if(info.effect){const effect=textNode('p',info.effect);effect.className='effect';box.append(effect);}
  const legal=Object.entries(info.legality||{}).map(([k,v])=>`${formats[k]||k}: ${v.estado}${v.puntos?` (${v.puntos} pts)`:''}`).join(' · ');
  const extra=textNode('p',[legal,info.master_duel?`Master Duel: ${info.master_duel.toUpperCase()}`:''].filter(Boolean).join(' · '));extra.className='legal';box.append(extra);
  return box;
}
async function updateTable(cards){
  const counts=new Map();
  for(const c of cards||[])if(c.card_id)counts.set(c.card_id,(counts.get(c.card_id)||0)+1);
  const key=[...counts].sort().map(([id,n])=>id+':'+n).join('|');
  if(key===tableKey)return;tableKey=key;
  await Promise.all([...counts.keys()].filter(id=>!sheets.has(id)).map(async id=>{
    try{const r=await fetch('/card-info?id='+encodeURIComponent(id));sheets.set(id,r.ok?await r.json():null);}catch(e){sheets.set(id,null);}
  }));
  if(key!==tableKey)return;  // a newer set arrived while fetching
  const nodes=[...counts].filter(([id])=>sheets.get(id)).map(([id,n])=>sheetNode(sheets.get(id),n));
  document.querySelector('#tableCards').replaceChildren(...nodes);
  document.querySelector('#tableStatus').textContent=nodes.length?`${nodes.length} carta${nodes.length>1?'s':''} distinta${nodes.length>1?'s':''} reconocida${nodes.length>1?'s':''} en la mesa.`:'Sin cartas reconocidas en este momento.';
}

if(sharedAnalysis)sharedAnalysis.onmessage=event=>{
  const data=event.data;
  if(!data||!Number.isFinite(data.captured_at)||!Array.isArray(data.detections))return;
  sharedCooldown=performance.now()+200;
  const sourceAt=performance.now()-Math.max(0,Date.now()-data.captured_at*1000);
  acceptAnalysis(data,generation,sourceAt).catch(()=>{});
};

async function requestRecognition(token){
    if(!configured||paused||!recognize.checked||!currentBlob||lastAnalyzed===frameNumber||performance.now()-frameAt>2500)return;
    if(performance.now()<sharedCooldown)return;
    const sourceAt=frameAt,blob=currentBlob,capturedAt=frameCapturedAt;lastAnalyzed=frameNumber;
    const response=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'image/jpeg','X-Captured-At':String(capturedAt)},body:blob,signal:AbortSignal.timeout(30000)});
    if(response.status===503){
      // Busy is backpressure, not a broken camera or a new recognition session.
      // Preserve valid diagnostics; the live overlay still expires by source age.
      if(token===generation&&!paused&&recognize.checked)detection.textContent='Reconocimiento ocupado; la cámara sigue en vivo.';
      return 700+Math.random()*600;
    }
    if(!response.ok)throw Error('Falló el análisis; la cámara sigue en vivo.');
    const data=await response.json();
    if(paused||!recognize.checked||token!==generation)return;
    sharedCooldown=performance.now()+200;
    if(sharedAnalysis)sharedAnalysis.postMessage(data);
    const actualSourceAt=Number.isFinite(data.captured_at)?performance.now()-Math.max(0,Date.now()-data.captured_at*1000):sourceAt;
    await acceptAnalysis(data,token,actualSourceAt);
}

// Server loop: the server analyzes the newest stream frame on its own; every tab
// long-polls for the next result, so no tab sends frames or takes turns.
let serverLoop=false,analysisSequence=-1;
async function followServerLoop(token){
  const response=await fetch('/analysis?after='+analysisSequence,{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(response.status===204)return 0;
  if(!response.ok)throw Error('Falló el análisis; la cámara sigue en vivo.');
  const data=await response.json();
  if(Number.isFinite(data.sequence))analysisSequence=data.sequence;
  if(paused||!recognize.checked||token!==generation)return 0;
  if(data.error){detection.textContent=`El análisis falló (${data.error}); el servidor reintenta. La cámara sigue en vivo.`;return 500;}
  const sourceAt=performance.now()-Math.max(0,Date.now()-data.captured_at*1000);
  await acceptAnalysis(data,token,sourceAt);
  return 0;
}

async function refreshRecognition(){
  let delay=200;const token=generation;
  try{
    if(!configured||paused||!recognize.checked)return;
    if(serverLoop){delay=await followServerLoop(token);return;}
    if(sharedAnalysis){
      await navigator.locks.request('yugioh-recognition-v1',{ifAvailable:true},async lock=>{
        if(lock)delay=await requestRecognition(token)||200;
      });
    }else delay=await requestRecognition(token)||200;
  }catch(e){
    if(token!==generation)return;
    clearRecognition();if(!paused&&recognize.checked)detection.textContent=e.name==='TimeoutError'?'El análisis tardó demasiado; reintentando. La cámara sigue en vivo.':e.message;
    delay=1000;
  }finally{setTimeout(refreshRecognition,delay);}
}

fetch('/config').then(r=>{if(!r.ok)throw Error();return r.json();}).then(c=>{
  offline=!!c.offline;serverLoop=!!c.server_loop;
  document.querySelector('#source').textContent=offline?'Prueba con una captura guardada · no es vídeo en vivo':`Cámara: ${c.camera}`;
  document.querySelector('#method').textContent=`${c.mode}${c.experimental?' · método experimental; umbrales todavía sin calibrar':''}. La cámara sigue en vivo.${c.live_tracking?' Las cartas confirmadas se siguen entre análisis.':''}${c.stream?(c.stream.connected?' Vídeo por stream MJPEG.':' Stream MJPEG no disponible; sondeo de fotogramas.'):''}${c.inference?.isolated?' Inferencia en un proceso aparte con reinicio automático.':''} El resultado detallado conserva la imagen exacta analizada; las marcas antiguas sólo se retiran del vídeo en vivo.`;
  if(serverLoop)document.querySelector('#method').textContent+=' El servidor analiza el fotograma más reciente en cuanto termina el anterior.';
  else if(sharedAnalysis)document.querySelector('#method').textContent+=' Análisis compartido entre pestañas de este navegador.';
  ar.disabled=!c.ar;ar.checked=!!c.ar;recognize.disabled=!c.recognition;recognize.checked=!!c.recognition;
  detection.textContent=c.recognition?`${c.references} referencias cargadas.`:'Reconocimiento desactivado en el servidor.';configured=true;
}).catch(()=>{detection.textContent='No se pudo cargar la configuración. Recarga la página para activar el reconocimiento.';});
draw();refreshCamera();refreshRecognition();

const passcodeStates={candidate:'Lectura candidata',repeated_match:'Lectura repetida y coincidencia en la base',unreadable:'Sin lectura fiable',not_in_registry:'Número leído; sin coincidencia en la base',ambiguous_reading:'Lecturas contradictorias',ambiguous_identity:'El número aparece en varias identidades',visual_conflict:'El número no coincide con la identificación visual'};
const nameStates={matched:'Coincidencia por nombre en la base',conflict:'Conflicto: el nombre no coincide con la imagen o el serial',ambiguous:'Nombre ambiguo: varias identidades posibles',low_confidence:'Lectura de nombre poco fiable',too_short:'Texto demasiado corto para asociar una carta',not_in_registry:'Texto leído; sin coincidencia normalizada',registry_unavailable:'Texto leído; registro no disponible',unreadable:'Nombre sin lectura fiable',error:'No se pudo leer el nombre',skipped:'Lectura del nombre omitida'};
let passcodeSequence=-1;
function textNode(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}
async function refreshPasscodes(){
  const token=generation;
  try{
    if(paused||!configured||!recognize.checked)return;
    const response=await fetch('/passcodes',{cache:'no-store',signal:AbortSignal.timeout(5000)});
    if(!response.ok)throw Error('No se pudo consultar el lector');
    const data=await response.json(),status=document.querySelector('#passcodeStatus');
    if(paused||!recognize.checked||token!==generation)return;
    if(data.state==='disabled'){status.textContent='El lector está desactivado en este servicio.';return;}
    if(data.state==='loading'){status.textContent='Cargando el lector local…';return;}
    if(data.state==='unavailable'||data.state==='error'){status.textContent='Lector no disponible: '+(data.error||'error de lectura');return;}
    if(!data.sequence){status.textContent='Esperando una carta detectada. Acerca la cámara para que el número sea legible.';return;}
    if(data.captured_at<passcodeMinCapturedAt)return;
    const age=Math.max(0,Math.floor(Date.now()/1000-data.captured_at));
    status.textContent=`Recortes del último análisis · hace ${age} s · OCR ${data.processing_ms} ms${data.pending?' · nuevo fotograma pendiente':''}. El zoom amplía la imagen; no añade detalle.`;
    if(data.sequence===passcodeSequence)return;passcodeSequence=data.sequence;
    const container=document.querySelector('#passcodeCards');container.replaceChildren();
    if(!data.items.length){container.append(textNode('p','No hay cartas detectadas para recortar.'));return;}
    for(const item of data.items)container.append(passcodeCard(item));
  }catch(e){if(token===generation&&!paused)document.querySelector('#passcodeStatus').textContent='No se pudo actualizar el zoom. Reintentando…';}
  finally{setTimeout(refreshPasscodes,750);}
}
function imageNode(src,alt,className){const img=document.createElement('img');img.src=src;img.alt=alt;img.className=className;return img;}
function registryLink(text,query){const link=textNode('a',text);link.href='http://127.0.0.1:8769/?'+query;link.target='_blank';link.rel='noopener';return link;}
function alternateNode(summary,src,alt,className){
  const alternate=document.createElement('details');alternate.append(textNode('summary',summary),imageNode(src,alt,className));return alternate;
}
function evidenceNodes(evidence){
  const labels={conflict:'Conflicto entre lecturas: identidad sin confirmar',candidate:'Identidad candidata',corroborated:'Fuentes concordantes',repeated:'Lectura repetida en capturas distintas',insufficient:'Evidencia insuficiente'};
  return [textNode('p',labels[evidence.status]||'Pendiente'),
    textNode('small',`${evidence.consistent_frames||0} capturas concordantes · fuentes: ${Object.keys(evidence.sources||{}).join(', ')}`)];
}
function setNodes(set){
  const states={matched:'coincidencia en el registro',not_in_registry:'sin coincidencia en el registro',ambiguous:'lectura ambigua',skipped:'omitido por tamaño o geometría'};
  const nodes=[textNode('p',`Set code: ${set.code||'sin lectura'} · ${states[set.status]||'sin coincidencia fiable'}`)];
  if(set.code)nodes.push(registryLink('Consultar impresiones compatibles','mode=set&q='+encodeURIComponent(set.code)));
  if(set.status==='matched')nodes.push(textNode('small','El set code puede compartir varias rarezas y ediciones.'));
  return nodes;
}
function nameSection(title){
  const section=document.createElement('section');section.className='name-reading';
  section.append(textNode('p','Nombre leído por OCR'),textNode('strong',title.text||'Sin texto legible'));
  section.append(textNode('p',nameStates[title.status]||'Pendiente'));
  if(title.reason)section.append(textNode('small',({small_text:'Acerca la carta: el título tiene pocos píxeles reales.',uncertain_geometry:'Faltan bordes fiables.',reader_unavailable:'El lector de nombres no está disponible.'})[title.reason]||title.reason));
  if(title.visual_conflict)section.append(textNode('p','El texto contradice la identificación visual.'));
  if(title.serial_conflict)section.append(textNode('p','El texto contradice el serial leído.'));
  const names=match=>(match.names||[]).map(n=>`${n.language.toUpperCase()}: ${n.name}`).join(' · ');
  for(const match of title.matches||[])section.append(registryLink(names(match),'q='+encodeURIComponent(match.card_id)));
  if(title.suggestions?.length){
    section.append(textNode('p','Sugerencias por texto parecido · no confirman identidad'));
    for(const suggestion of title.suggestions)section.append(textNode('p',names(suggestion)));
  }
  const details=document.createElement('details');details.append(textNode('summary','Lecturas del nombre sin corregir'));
  details.append(textNode('p',(title.raw_observations||[]).map(o=>`${o.orientation}° / ${o.variant}: ${o.text} (${o.score})`).join(' | ')||'Sin observaciones'));
  section.append(details);
  return section;
}
function passcodeCard(item){
  const card=document.createElement('article');card.className='passcode-card';
  card.append(textNode('h3',item.visual_name||`Carta detectada ${item.track_id}`));
  card.append(textNode('p',item.geometry_status==='contour_refined'?'Geometría ajustada a bordes visibles · ajuste experimental':item.geometry_status==='tracked'?'Geometría del seguimiento · se leerá al volver a ajustarla':'Geometría sin resolver · recortes desactivados'));
  if(item.rectified)card.append(imageNode(item.rectified,'Carta rectificada; regiones de nombre y serial marcadas','rectified'));
  if(item.name_crop){
    card.append(textNode('p','Nombre · recorte de la imagen'),imageNode(item.name_crop,'Franja del nombre ampliada','name-zoom'));
    if(item.name_crop_alternative)card.append(alternateNode('Orientación dudosa: ver el extremo opuesto',item.name_crop_alternative,'Posible nombre con orientación opuesta','name-zoom'));
  }
  if(item.evidence)card.append(...evidenceNodes(item.evidence));
  if(item.art_match&&item.art_match.status!=='skipped'){
    const art=item.art_match,best=art.matches?.[0];
    const artStates={matched:`Ilustración verificada por rasgos locales · ${best?.inliers??0} puntos coincidentes`,ambiguous:'Ilustración compatible con varias candidatas · sin verificar',unverified:'Ilustración sin verificación geométrica',error:'No se pudo verificar la ilustración'};
    card.append(textNode('small',artStates[art.status]||'Ilustración: pendiente'));
  }
  if(item.ocr_reused)card.append(textNode('p','Mostrando lectura de una captura reciente de mejor calidad; no suma una nueva confirmación.'));
  if(item.set_ocr)card.append(...setNodes(item.set_ocr));
  if(item.name_ocr)card.append(nameSection(item.name_ocr));
  if(item.crop)card.append(textNode('p','Serial · esquina inferior izquierda de la carta'),imageNode(item.crop,'Recorte ampliado de la esquina inferior izquierda','zoom'));
  if(item.crop_alternative)card.append(alternateNode('Orientación dudosa: posible serial en el extremo opuesto',item.crop_alternative,'Posible serial con orientación opuesta','zoom'));
  card.append(textNode('p',passcodeStates[item.status]||'Pendiente'),textNode('code',item.passcode||'????????'));
  for(const match of item.matches||[]){const p=document.createElement('p');p.append(registryLink(match.name,'mode=passcode&q='+encodeURIComponent(item.passcode)));card.append(p);}
  card.append(textNode('p',item.quality_hint||''));
  if(item.native_card_height)card.append(textNode('small',`Carta original: ${item.native_card_width} × ${item.native_card_height} px · dígitos ≈ ${item.estimated_digit_height} px de alto · ${item.consistent_frames} capturas concordantes`));
  const details=document.createElement('details');details.append(textNode('summary','Lecturas OCR sin corregir'));
  details.append(textNode('p',(item.raw_observations||[]).map(o=>`${o.orientation}° / ${o.variant}: ${o.text||'—'}`).join(' | ')));card.append(details);
  return card;
}
refreshPasscodes();

function cardSample(bitmap,corners){
  if(corners?.length!==4||corners.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v))))return null;
  const left=Math.max(0,Math.floor(Math.min(...corners.map(p=>p[0]))));
  const top=Math.max(0,Math.floor(Math.min(...corners.map(p=>p[1]))));
  const right=Math.min(bitmap.width,Math.ceil(Math.max(...corners.map(p=>p[0]))));
  const bottom=Math.min(bitmap.height,Math.ceil(Math.max(...corners.map(p=>p[1]))));
  const w=right-left,h=bottom-top;if(w<8||h<8)return null;
  const scale=Math.min(1,220/Math.max(w,h)),canvas=document.createElement('canvas');
  canvas.width=Math.max(1,Math.round(w*scale));canvas.height=Math.max(1,Math.round(h*scale));
  const c=canvas.getContext('2d',{willReadFrequently:true});
  c.beginPath();corners.forEach(([x,y],i)=>i?c.lineTo((x-left)*scale,(y-top)*scale):c.moveTo((x-left)*scale,(y-top)*scale));c.closePath();c.clip();
  c.drawImage(bitmap,left,top,w,h,0,0,canvas.width,canvas.height);
  const pixels=c.getImageData(0,0,canvas.width,canvas.height).data;
  let count=0,white=0,dark=0;
  for(let i=0;i<pixels.length;i+=4){
    if(pixels[i+3]<250)continue;count++;
    const lo=Math.min(pixels[i],pixels[i+1],pixels[i+2]),hi=Math.max(pixels[i],pixels[i+1],pixels[i+2]);
    if(lo>=245)white++;if(hi<=25)dark++;
  }
  if(!count)return null;
  return {url:canvas.toDataURL('image/png'),white:white/count,dark:dark/count,width:w,height:h,
    center:[(left+right)/2,(top+bottom)/2],size:Math.hypot(w,h)};
}
async function paintQuality(data,sourceAt,token){
  if(!data.image)return;
  const bitmap=await createImageBitmap(await (await fetch(data.image)).blob());
  if(paused||token!==generation||lastAnalysis?.captured_at>data.captured_at){bitmap.close();return;}
  const named=new Map((data.detections||[]).map(d=>[JSON.stringify(d.corners),d]));
  const samples=[];
  try{
    for(const candidate of (data.candidates||data.detections||[]).slice(0,20)){
      const sample=cardSample(bitmap,candidate.corners);if(!sample)continue;
      const match=named.get(JSON.stringify(candidate.corners));
      samples.push({...sample,identity:match?.card_id||match?.id||null,name:match?.name||'Carta sin identificar',at:sourceAt});
    }
  }finally{bitmap.close();}
  const old=qualityTracks.filter(t=>sourceAt-t.at<qualityWindow);
  // Mutual, unambiguous nearest neighbors. A merged/tied detection starts afresh.
  function choices(sample,tracks){return tracks.map((t,i)=>({i,d:Math.hypot(sample.center[0]-t.center[0],sample.center[1]-t.center[1])/sample.size}))
    .filter(o=>sample.identity&&tracks[o.i].identity===sample.identity&&o.d<.2&&Math.abs(tracks[o.i].size/sample.size-1)<.2).sort((a,b)=>a.d-b.d);}
  const next=samples.map((s,index)=>{
    const options=choices(s,old);let previous=null;
    if(options.length&&(options.length===1||options[1].d-options[0].d>.1)){
      const back=choices(old[options[0].i],samples);
      if(back[0]?.i===index&&(back.length===1||back[1].d-back[0].d>.1))previous=old[options[0].i];
    }
    const history=[...(previous?.history||[]),s].filter(x=>sourceAt-x.at<qualityWindow).slice(-4);
    // Only compare similar sizes; avoid choosing an underexposed frame simply because it is dark.
    const comparable=history.filter(x=>Math.abs(x.size/s.size-1)<.15&&x.dark<=s.dark+.05);
    const best=comparable.reduce((a,b)=>b.white<a.white?b:a,s);
    return {...s,id:previous?.id||qualityNextId++,history,best};
  });
  qualityTracks=next;
  const container=document.querySelector('#qualityCards');container.replaceChildren();
  for(const t of next){
    const item=document.createElement('article');item.className='quality-card';
    item.append(textNode('h3',`${t.name} · muestra ${t.id}`));
    for(const [sample,label] of [[t,'Captura actual'],[t.best,'Captura reciente con menos blanco saturado']]){
      const img=document.createElement('img');img.src=sample.url;img.alt=label;item.append(img);
    }
    const pct=(t.white*100).toFixed(1);
    item.append(textNode('p',`${pct}% de blanco saturado${t.white>=.03?' · posible reflejo: prueba mover la luz hacia un lado.':'.'}`));
    item.append(textNode('small',`Recorte actual: ${t.width} × ${t.height} px. Captura derecha: ${(t.best.white*100).toFixed(1)}% · ${Math.max(0,Math.round((performance.now()-t.best.at)/1000))} s al actualizar.`));
    container.append(item);
  }
  document.querySelector('#qualityStatus').textContent=`${next.length} contornos detectados; ${(data.detections||[]).length} identificaciones aceptadas. Comparación del último análisis; no es vídeo en vivo. Una captura menos saturada no garantiza mejor reconocimiento.`;
}

// ---- Duelo en la mesa: calibración del tapete y panel ------------------------------------
const $d=s=>document.querySelector(s);
const CORNERS=['arriba a la izquierda (lado del rival)','arriba a la derecha (lado del rival)','abajo a la derecha (su lado)','abajo a la izquierda (su lado)'];
const PHASES={draw:'Fase de Robo',standby:'Fase de Espera',main1:'Fase Principal 1',battle:'Fase de Batalla',main2:'Fase Principal 2',end:'Fase Final'};
const POSITIONS={attack:'ataque',defense:'defensa',facedown_defense:'defensa boca abajo',faceup:'boca arriba',facedown:'boca abajo'};
let duelView=null;

function drawTableOverlay(context){
  if(playmat&&$d('#showZones')?.checked&&!calibration){
    context.save();context.lineWidth=2;context.font='14px system-ui';
    for(const z of playmat.zones||[]){
      context.strokeStyle=z.player===0?'rgba(141,229,202,.55)':'rgba(255,209,102,.55)';
      context.beginPath();z.polygon.forEach(([x,y],i)=>i?context.lineTo(x,y):context.moveTo(x,y));context.closePath();context.stroke();
      const [cx,cy]=z.polygon.reduce(([a,b],[x,y])=>[a+x/4,b+y/4],[0,0]);
      context.fillStyle='rgba(233,238,247,.75)';context.fillText(z.zone.replace('monster:','M').replace('extra_monster:','EM').replace('spell:','MT'),cx-10,cy);
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
      playmat?.mode?`Tapetes calibrados (${playmat.modes[playmat.mode]}). Si mueves la cámara, vuelve a calibrar.`:'Sin tapete: elige un modo. La plantilla impresa no necesita calibración.';
    return;}
  const player=calibration.mats.length,who=calibration.mode==='one'?'tu tapete':`el tapete del jugador ${player+1} (${$d('#name'+player).value})`;
  $d('#calibrationHelp').textContent=`Haz clic en ${who}, esquina ${calibration.points.length+1} de 4: ${CORNERS[calibration.points.length]}, como lo ve ese jugador sentado.`;
}

$d('#calibrate').onclick=async()=>{
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
  if(questionsKey!==renderDuel.questionsKey){renderDuel.questionsKey=questionsKey;$d('#duelQuestions').replaceChildren(...(view.questions||[]).map(questionNode));}
  const board=view.board||[];
  $d('#duelBoard').replaceChildren(...(board.length?[textNode('h3','En el campo')]:[]),...board.map(c=>textNode('p',`${view.players[c.player]?.name} · ${c.zone_label}: ${c.name||'carta boca abajo'} · ${POSITIONS[c.position]||c.position}${c.atk!=null?` · ATK ${c.atk}${c.def!=null?` / DEF ${c.def}`:''}`:''}`)));
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
    if((!playmat||playmat.mode==='printed')&&!calibration){const m=await fetch('/playmat');if(m.ok){const next=await m.json();if(JSON.stringify(next)!==JSON.stringify(playmat)){playmat=next;zonesVersion++;}calibrationStep();}}
  }catch(e){}
  finally{setTimeout(refreshDuel,800);}
}
refreshDuel();
