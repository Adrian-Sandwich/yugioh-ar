// Camera viewer (/): sprites warped over the
// video in the browser. A WebGL textured quad with perspective-correct texture
// coordinates, so nothing but corners and a sprite id travel per frame.
const sprites=imageCache();   // by URL (common.js)
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
