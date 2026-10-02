// Shared by the camera viewer (/) and the duel view (/duelo); loaded before ar.js and the page script.

function textNode(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}

// Hidden tab: polling waits until the page is shown again (a background tab kept pulling ~15 JPEG/s).
function visible(){return document.hidden?new Promise(r=>document.addEventListener('visibilitychange',function f(){if(!document.hidden){document.removeEventListener('visibilitychange',f);r();}})):Promise.resolve();}

// Images by key, loaded once: get() returns the image when ready, null meanwhile (or if it failed).
function imageCache(urlOf=key=>key){
  return {cache:new Map(),
    get(key){
      if(!key)return null;
      let entry=this.cache.get(key);
      if(!entry){entry={image:null,failed:false};this.cache.set(key,entry);const img=new Image();
        img.onload=()=>{entry.image=img;};img.onerror=()=>{entry.failed=true;};img.src=urlOf(key);}
      return entry.image;
    }};
}

// Card sheets from /card-info (local registry). cache: id -> sheet, or null while loading / unknown.
const cardInfo={cache:new Map(),
  async load(id){
    let sheet=null;
    try{const r=await fetch('/card-info?id='+encodeURIComponent(id));sheet=r.ok?await r.json():null;}catch(e){}
    this.cache.set(id,sheet);return sheet;
  },
  // Synchronous read for drawing code: starts the request the first time and calls onLoad once it arrives.
  peek(id,onLoad){
    if(!id)return null;
    if(!this.cache.has(id)){this.cache.set(id,null);this.load(id).then(s=>{if(s&&onLoad)onLoad(s);});}
    return this.cache.get(id);
  }};

// The server's newest camera frame with the tracks of that exact frame (X-Tracks): identities in them
// were confirmed by an earlier analysis. Throws when the camera is unavailable.
async function fetchFrame(){
  const response=await fetch('/snapshot?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw Error('Cámara no disponible');
  const blob=await response.blob(),bitmap=await createImageBitmap(blob);
  const timestamp=Number(response.headers.get('X-Captured-At'));
  let tracks=[];
  try{tracks=JSON.parse(response.headers.get('X-Tracks')||'[]');}catch(e){tracks=[];}
  tracks=Array.isArray(tracks)?tracks.filter(t=>t.card_id&&t.corners?.length===4):[];
  return {bitmap,blob,tracks,capturedAt:timestamp>0&&Number.isFinite(timestamp)?timestamp:null};
}

// Links to the lab's other services on this same host (whatever name the page was opened with).
document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('a[data-port]').forEach(a=>{a.href=`${location.protocol}//${location.hostname}:${a.dataset.port}/`;}));
