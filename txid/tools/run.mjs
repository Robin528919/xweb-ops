import {JSDOM} from 'jsdom';
import fs from 'fs';
const html=fs.readFileSync(process.argv[2]||'loggedout.html','utf8');
const dom=new JSDOM(html,{url:'https://x.com/',pretendToBeVisual:true});
const w=dom.window;
const NOW=Number(process.env.NOW||1760000000000), RND=Number(process.env.RND||0x5a);
const D=w.Date; class FD extends D{constructor(...a){a.length?super(...a):super(NOW)} static now(){return NOW}}
const acc=new Set();

function bez(x1,y1,x2,y2,x){ // CSS cubic-bezier: solve t for x, return y
  const cx=(t)=>3*x1*t*(1-t)**2+3*x2*t*t*(1-t)+t**3, cy=(t)=>3*y1*t*(1-t)**2+3*y2*t*t*(1-t)+t**3;
  let lo=0,hi=1,t=x; for(let i=0;i<100;i++){ t=(lo+hi)/2; if(cx(t)<x) lo=t; else hi=t; } return cy(t);
}
function hex(c){ c=c.replace('#',''); return [0,2,4].map(i=>parseInt(c.slice(i,i+2),16)); }
const ANIMS=new WeakMap();
w.HTMLElement.prototype.animate=function(kf,opts){ const st={kf,opts:(typeof opts==='number'?{duration:opts}:opts),currentTime:0}; ANIMS.set(this,st);
  console.error('ANIMATE',JSON.stringify(kf),JSON.stringify(opts));
  return {pause(){}, play(){}, cancel(){}, set currentTime(v){ st.currentTime=v; console.error('  currentTime',v);}, get currentTime(){return st.currentTime;}}; };
globalThis.__computed=(el)=>{ const st=ANIMS.get(el); if(!st) return null;
  const m=/cubic-bezier\(([^)]*)\)/.exec(st.kf.easing); const [a,b,c,d]=m[1].split(',').map(Number);
  const p=bez(a,b,c,d, st.currentTime/st.opts.duration);
  const c0=hex(st.kf.color[0]), c1=hex(st.kf.color[1]);
  const col=c0.map((v,i)=>Math.max(0,Math.min(255,Math.round(v+(c1[i]-v)*p))));
  const r0=parseFloat(/rotate\(([-\d.]+)deg/.exec(st.kf.transform[0])[1]), r1=parseFloat(/rotate\(([-\d.]+)deg/.exec(st.kf.transform[1])[1]);
  const deg=r0+(r1-r0)*p, rad=deg*Math.PI/180; const f=(x)=>{ const r=Math.round(x*1e6)/1e6; return String(Object.is(r,-0)?0:r); };
  return {color:`rgb(${col.join(', ')})`, transform:`matrix(${f(Math.cos(rad))}, ${f(Math.sin(rad))}, ${f(-Math.sin(rad))}, ${f(Math.cos(rad))}, 0, 0)`};
};
const wp=new Proxy(w,{get(t,p){ if(typeof p==='string') acc.add(p);
  if(p==='document') return dp; if(p==='Date') return FD;
  if(p==='Math'){ return new Proxy(Math,{get(m,k){ if(k==='random') return ()=>RND/256; return m[k];}}); }
  if(p==='crypto') return {subtle:{digest:async(alg,data)=>{console.error('DIGEST',alg,new TextDecoder().decode(data));return globalThis.crypto.subtle.digest(alg,data);}}, getRandomValues:(a)=>{a.fill(RND);return a;}};
  if(p==='TextEncoder') return TextEncoder; if(p==='Uint8Array') return Uint8Array; if(p==='Uint32Array') return Uint32Array; if(p==='Array') return Array; if(p==='Number') return Number; if(p==='Promise') return Promise; if(p==='Function') return Function; if(p==='Error') return Error;
  if(p==='getComputedStyle') return (el,...a)=>{ console.error('GCS on',el.outerHTML.slice(0,400)); console.error('STYLE.anim', el.style.animation, '|', el.style.cssText.slice(0,500)); for(const a of el.getAnimations?el.getAnimations():[]) console.error('ANIM',a); for (const ss of w.document.styleSheets){ try{ for(const r of ss.cssRules) if(/keyframes|@/.test(r.cssText.slice(0,20))) console.error('RULE',r.cssText.slice(0,600)); }catch(e){} } const cs=w.getComputedStyle(el,...a); const fake=globalThis.__computed(el); return new Proxy(cs,{get(c,k){ const v=(fake&&(k==='color'||k==='transform'))?fake[k]:c[k]; console.error('  GCS.'+String(k),'=',typeof v==='function'?'fn':JSON.stringify(v)); return typeof v==='function'?v.bind(c):v;}});};
  if(p==='RTCPeerConnection'){ console.error('RTC accessed'); return undefined; }
  const v=Reflect.get(t,p); return typeof v==='function' && /^[a-z]/.test(p) ? v.bind(t) : v;}});
const dp=new Proxy(w.document,{get(t,p){ const v=Reflect.get(t,p); if(typeof v==='function') return (...a)=>{ const r=v.apply(t,a); console.error('DOC.'+String(p)+'('+a.map(x=>typeof x==='string'?x:typeof x).join(',')+') ->', r&&r.length!==undefined?('len '+r.length):(r&&r.tagName)); return r;}; console.error('DOC.'+String(p)); return v;}});
w.Element.prototype._ga=w.Element.prototype.getAttribute; w.Element.prototype.getAttribute=function(n){ console.error('  getAttribute',this.tagName,this.id||'',n); return this._ga(n); };
const qs=w.Element.prototype.querySelectorAll; w.Element.prototype.querySelectorAll=function(s){ const r=qs.call(this,s); console.error('  el.qsa',this.tagName,this.id||'',s,'len',r.length); return r;};
const ch=Object.getOwnPropertyDescriptor(w.Element.prototype,'children'); 
globalThis.window=wp; globalThis.document=dp; globalThis.self=wp;
// getComputedStyle in jsdom doesn't animate; log calls
const m=await import('./sign.mjs');
const f=await m.default();
const path=process.env.TXPATH||'/i/api/graphql/abc/UserByScreenName', method=process.env.TXMETHOD||'GET';
const id=await f(path,method);
console.log(JSON.stringify({id, accessed:[...acc].filter(x=>!x.startsWith('_sentry'))}));
