// The Millennium shield as a solid: a mesh with its two faces and its edge, raised from the relief of
// its two drawings (tools/make_shield_relief.py writes /fx/shield-millennium-*-relief.png: normal in
// R and G, metal in B, height in A), lit by a shader of its own: a key light and a made-up room that
// the gold mirrors as it turns. Drawn in a WebGL canvas of its own and stamped on the 2D view.
//
//   shield3d.draw(context, cx, cy, height, angle, alpha, {nod, flash})  -> false until it can draw
//
// Without WebGL, or while its four pictures load, draw() returns false and the caller keeps its flat shield.
const shield3d=(()=>{
  const SIZE=512;         // px of the WebGL canvas; a shield on the table is 100-300 px tall
  const SPAN=1.25;        // the canvas shows this many shield heights, room for the turn's perspective
  const STEP=3;           // px of the relief map per mesh cell
  const RIM=.017,FRONT=.05,BACK=.025;  // in shield heights: half the edge's thickness, and a height of 1 on each face
  const EYE=3.2;          // the eye's distance, in shield heights: how much the near side grows as it turns
  const names=['front','back','front-relief','back-relief'],images={};
  let gl=null,program=null,count=0,failed=false,canvas=null,uniforms={};

  const VERTEX=`
    attribute vec3 aPos; attribute vec2 aUV; attribute float aKind; attribute vec2 aEdge;
    uniform mat3 uTurn; uniform float uScale, uEye;
    varying vec2 vUV; varying float vKind; varying vec3 vEdge;
    void main(){
      vec3 p=uTurn*aPos; vUV=aUV; vKind=aKind; vEdge=uTurn*vec3(aEdge,0.);
      float near=uEye/(uEye-p.z);
      gl_Position=vec4(p.xy*near*uScale,-p.z*.9,1.);
    }`;
  const FRAGMENT=`
    precision highp float;
    uniform sampler2D uArtFront,uArtBack,uReliefFront,uReliefBack;
    uniform mat3 uTurn; uniform vec3 uLight; uniform float uAlpha,uFlash;
    varying vec2 vUV; varying float vKind; varying vec3 vEdge;
    const vec3 GOLD=vec3(.78,.38,.06);
    vec3 room(vec3 r){
      // What the metal mirrors: a pale ceiling over a dark floor, and a window up and to the left.
      vec3 sky=mix(vec3(.05,.035,.03),vec3(.62,.58,.52),smoothstep(-.25,.75,r.y));
      float window=smoothstep(.80,.97,dot(r,normalize(vec3(-.55,.62,.56))));
      float strip=smoothstep(.90,.99,dot(r,normalize(vec3(.75,.15,.64))));
      return sky+window*vec3(2.6,2.4,2.0)+strip*vec3(.7,.75,.9);
    }
    void main(){
      vec2 back=vec2(1.-vUV.x,vUV.y);
      vec4 artF=texture2D(uArtFront,vUV),artB=texture2D(uArtBack,back);
      vec4 relF=texture2D(uReliefFront,vUV),relB=texture2D(uReliefBack,back);
      float rear=step(.5,vKind)*step(vKind,1.5),wall=step(1.5,vKind);
      vec4 art=mix(artF,artB,rear),rel=mix(relF,relB,rear);
      // The drawing ends a hair inside the mesh's outline: there the shield is its gold rim.
      float drawn=smoothstep(.35,.75,art.a)*(1.-wall);
      vec3 base=mix(GOLD,pow(art.rgb/max(art.a,.01),vec3(2.2)),drawn);
      float metal=mix(1.,rel.b,drawn),height=mix(.5,rel.a,drawn);
      vec2 t=(rel.rg*2.-1.)*drawn; float tz=sqrt(max(1.-dot(t,t),.05));
      // The map's x runs right and its y down the drawing; the back face is the drawing mirrored.
      vec3 n=mix(vec3(t.x,-t.y,tz),vec3(-t.x,-t.y,-tz),rear);
      vec3 N=normalize(mix(uTurn*n,vEdge,wall)),V=vec3(0.,0.,1.);
      if(dot(N,V)<0.)N=reflect(N,V);
      vec3 L=normalize(uLight),H=normalize(L+V);
      float ndl=max(dot(N,L),0.),ndh=max(dot(N,H),0.),ndv=max(dot(N,V),0.);
      float rough=mix(.6,.3,metal),a=rough*rough,d=ndh*ndh*(a*a-1.)+1.,spec=a*a/(3.14159*d*d);
      vec3 f0=mix(vec3(.04),base,metal);
      float hollow=mix(.62,1.,smoothstep(.15,.7,height));   // the low places hold less light
      vec3 col=base*(1.-metal)*(.34+.8*ndl)*hollow;
      col+=f0*(spec*ndl*.9+room(reflect(-V,N))*mix(.12,.85,metal)*hollow);
      col+=pow(1.-ndv,5.)*.35*room(reflect(-V,N))*mix(.2,1.,metal);
      col+=uFlash*vec3(.5,.36,.14)*(.6+.8*metal);   // gold catches the flash more than lacquer and leather
      gl_FragColor=vec4(pow(clamp(col,0.,1.),vec3(1./2.2)),1.)*uAlpha;
    }`;

  function pixels(img){
    const c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;
    const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(img,0,0);return x.getImageData(0,0,c.width,c.height);
  }
  // Height (the map's alpha, 0..1) at a point of a relief map, between its pixels.
  function heightAt(map,x,y){
    const w=map.width,h=map.height;x=Math.min(Math.max(x-.5,0),w-1);y=Math.min(Math.max(y-.5,0),h-1);
    const x0=Math.floor(x),y0=Math.floor(y),x1=Math.min(x0+1,w-1),y1=Math.min(y0+1,h-1),fx=x-x0,fy=y-y0,a=(i,j)=>map.data[(j*w+i)*4+3];
    return ((a(x0,y0)*(1-fx)+a(x1,y0)*fx)*(1-fy)+(a(x0,y1)*(1-fx)+a(x1,y1)*fx)*fy)/255;
  }
  // The solid: a lattice over the front map's silhouette, a shell per face and a wall around the outline.
  function mesh(front,back){
    const W=front.width,H=front.height,nx=Math.ceil(W/STEP),ny=Math.ceil(H/STEP),vx=nx+1,vy=ny+1;
    const cell=new Uint8Array(nx*ny),inCell=(i,j)=>i>=0&&j>=0&&i<nx&&j<ny&&cell[j*nx+i]===1;
    for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
      const x=Math.min(W-1,Math.floor((i+.5)*STEP)),y=Math.min(H-1,Math.floor((j+.5)*STEP));cell[j*nx+i]=front.data[(y*W+x)*4+3]>0?1:0;}
    const px=new Float32Array(vx*vy),py=new Float32Array(vx*vy),used=new Uint8Array(vx*vy),edge=new Uint8Array(vx*vy);
    for(let j=0;j<vy;j++)for(let i=0;i<vx;i++){
      const k=j*vx+i,around=[inCell(i-1,j-1),inCell(i,j-1),inCell(i-1,j),inCell(i,j)],n=around.filter(Boolean).length;
      px[k]=Math.min(i*STEP,W);py[k]=Math.min(j*STEP,H);used[k]=n>0?1:0;edge[k]=n>0&&n<4?1:0;}
    // The lattice's outline is a staircase: each outline point moves toward its outline neighbours.
    for(let pass=0;pass<5;pass++){
      const sx=px.slice(),sy=py.slice();
      for(let j=0;j<vy;j++)for(let i=0;i<vx;i++){
        const k=j*vx+i;if(!edge[k])continue;let ax=0,ay=0,n=0;
        for(let dj=-1;dj<=1;dj++)for(let di=-1;di<=1;di++){
          const ii=i+di,jj=j+dj;if((!di&&!dj)||ii<0||jj<0||ii>=vx||jj>=vy)continue;
          const q=jj*vx+ii;if(edge[q]){ax+=sx[q];ay+=sy[q];n++;}}
        if(n){px[k]=.5*sx[k]+.5*ax/n;py[k]=.5*sy[k]+.5*ay/n;}
      }
    }
    // Outward direction at each outline point, from the wall pieces that meet there.
    const ex=new Float32Array(vx*vy),ey=new Float32Array(vx*vy),walls=[];
    const wallOf=(a,b)=>{const dx=px[b]-px[a],dy=py[b]-py[a],l=Math.hypot(dx,dy)||1,ox=dy/l,oy=-dx/l;ex[a]+=ox;ey[a]+=oy;ex[b]+=ox;ey[b]+=oy;walls.push(a,b);};
    for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
      if(!cell[j*nx+i])continue;const a=j*vx+i,b=a+1,c=a+vx+1,d=a+vx;   // clockwise in the map: a b c d
      if(!inCell(i,j-1))wallOf(a,b);if(!inCell(i+1,j))wallOf(b,c);if(!inCell(i,j+1))wallOf(c,d);if(!inCell(i-1,j))wallOf(d,a);
    }
    const data=[],aspect=W/H,bw=back.width,bh=back.height;
    const put=(k,kind)=>{
      const u=px[k]/W,v=py[k]/H,x=(u-.5)*aspect,y=.5-v,l=Math.hypot(ex[k],ey[k])||1;
      const zf=RIM+(edge[k]?0:FRONT*heightAt(front,px[k],py[k])),zb=RIM+(edge[k]?0:BACK*Math.max(.1,heightAt(back,(1-u)*bw,v*bh)));
      // kind 0 the front face, 1 the back face, 2 and 3 the wall's front and back rim
      data.push(x,y,kind===0||kind===2?zf:-zb,u,v,kind>=2?2:kind,ex[k]/l,-ey[k]/l);
    };
    for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
      if(!cell[j*nx+i])continue;const a=j*vx+i,b=a+1,c=a+vx+1,d=a+vx;
      for(const k of [a,d,b,b,d,c])put(k,0);for(const k of [a,b,d,b,c,d])put(k,1);
    }
    for(let w=0;w<walls.length;w+=2){const a=walls[w],b=walls[w+1];put(a,2);put(b,2);put(a,3);put(b,2);put(b,3);put(a,3);}
    return new Float32Array(data);
  }

  function texture(unit,img,linear){
    const t=gl.createTexture();gl.activeTexture(gl.TEXTURE0+unit);gl.bindTexture(gl.TEXTURE_2D,t);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,linear?0:1);gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL,gl.NONE);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,img);
    for(const [k,v] of [[gl.TEXTURE_MIN_FILTER,gl.LINEAR],[gl.TEXTURE_MAG_FILTER,gl.LINEAR],[gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE],[gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE]])gl.texParameteri(gl.TEXTURE_2D,k,v);
  }
  function shader(type,source){
    const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;
  }
  function setup(){
    try{
      canvas=document.createElement('canvas');canvas.width=canvas.height=SIZE;
      gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:true,depth:true});
      if(!gl)throw new Error('sin WebGL');
      program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,VERTEX));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,FRAGMENT));
      gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));
      gl.useProgram(program);
      const data=mesh(pixels(images['front-relief']),pixels(images['back-relief']));count=data.length/8;
      gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
      for(const [name,size,offset] of [['aPos',3,0],['aUV',2,3],['aKind',1,5],['aEdge',2,6]]){
        const at=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(at);gl.vertexAttribPointer(at,size,gl.FLOAT,false,32,offset*4);}
      // The drawings keep their colours premultiplied (their soft edge would bleed white otherwise); the relief maps are data.
      texture(0,images.front,false);texture(1,images.back,false);texture(2,images['front-relief'],true);texture(3,images['back-relief'],true);
      for(const name of ['uTurn','uScale','uEye','uLight','uAlpha','uFlash'])uniforms[name]=gl.getUniformLocation(program,name);
      ['uArtFront','uArtBack','uReliefFront','uReliefBack'].forEach((name,i)=>gl.uniform1i(gl.getUniformLocation(program,name),i));
      gl.enable(gl.DEPTH_TEST);gl.clearColor(0,0,0,0);gl.viewport(0,0,SIZE,SIZE);
      canvas.addEventListener('webglcontextlost',()=>{gl=null;failed=true;});
    }catch(error){console.warn('shield3d: escudo plano,',error.message);gl=null;failed=true;}
  }
  let loaded=0;
  for(const name of names){const img=new Image();img.onload=()=>{images[name]=img;loaded++;};img.onerror=()=>{failed=true;};img.src=`/fx/shield-millennium-${name}.png`;}

  // `angle`: the turn about the shield's own upright axis, 0 = its front to the viewer. `nod`: a tilt
  // toward the viewer, radians. `flash`: gold light added to every point (its entrance), 0..1.
  function draw(context,cx,cy,height,angle,alpha=1,{nod=0,flash=0}={}){
    if(failed||loaded<names.length)return false;
    if(!gl){setup();if(!gl)return false;}
    const c=Math.cos(angle),s=Math.sin(angle),cn=Math.cos(nod),sn=Math.sin(nod);
    // Columns of nod (about x) times turn (about y).
    gl.uniformMatrix3fv(uniforms.uTurn,false,[c,sn*s,-cn*s, 0,cn,sn, s,-sn*c,cn*c]);
    gl.uniform1f(uniforms.uScale,2/SPAN);gl.uniform1f(uniforms.uEye,EYE);gl.uniform3f(uniforms.uLight,-.42,.62,.66);
    gl.uniform1f(uniforms.uAlpha,alpha);gl.uniform1f(uniforms.uFlash,flash);
    gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.drawArrays(gl.TRIANGLES,0,count);
    const side=height*SPAN;context.drawImage(canvas,cx-side/2,cy-side/2,side,side);
    return true;
  }
  return {draw,get ready(){return !failed&&loaded===names.length;}};
})();
