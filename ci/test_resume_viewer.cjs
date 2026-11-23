#!/usr/bin/env node
// Headless regression for iOS suspension and reconnect: no browser, credentials,
// Android SDK, external services, or user sessions are accessed.
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');

const html=fs.readFileSync('ci/live-emulator.html','utf8');
const match=html.match(/<script type="module">([\s\S]*?)<\/script>/);
assert(match,'viewer module script must exist');
const js=match[1].replace(/^\s*import RFB from ['"].+?['"];\s*/,'');
new vm.Script(js,{filename:'live-emulator-viewer.mjs'});

const screen={hidden:false};
const status={textContent:'',style:{}};
const placeholder={hidden:false};
const inputStatus={textContent:'',style:{}};
const theaterToggleLabel={textContent:'Fullscreen'};
const theaterHint={textContent:''};
const theaterStage={clientWidth:844,clientHeight:390};
const remoteEvents=new Map();
const theaterRemote={offsetLeft:600,offsetTop:274,offsetWidth:234,offsetHeight:107,style:{}};
const remoteHandle={
 addEventListener(name,fn){remoteEvents.set(name,fn)},
 setPointerCapture(id){this.captureId=id},
};
const theatreClasses=new Set();
const body={classList:{add(...names){for(const n of names)theatreClasses.add(n)},remove(...names){for(const n of names)theatreClasses.delete(n)},toggle(name,enabled){if(enabled)theatreClasses.add(name);else theatreClasses.delete(name)},contains(name){return theatreClasses.has(name)}}};
const theaterToggle={click:null,attrs:{},addEventListener(_event,fn){this.click=fn},setAttribute(k,v){this.attrs[k]=v}};
let portrait=true;
const holder={};
const reconnectButton={click:null,addEventListener(_name,cb){this.click=cb;}};
const elements={status,placeholder,screen:holder,reconnect:reconnectButton,inputStatus,theaterStage,theaterToggle,theaterToggleLabel,theaterHint,theaterRemote,theaterRemoteHandle:remoteHandle};
const documentListeners=new Map();
const windowListeners=new Map();
const timers=new Map();
const viewers=[];
const controls=[];
let id=1;
let now=1000;

class RFB {
 constructor(_holder,url,opts){
  this.url=url;this.opts=opts;this.events=new Map();
  viewers.push(this);
 }
 addEventListener(type,cb){this.events.set(type,cb);}
 disconnect(){this.wasDisconnected=true;this.emit('disconnect');}
 emit(type){this.events.get(type)?.();}
}
class FakeWebSocket {
 constructor(url){this.url=url;this.readyState=0;this.sent=[];controls.push(this)}
 send(data){this.sent.push(JSON.parse(data))}
 open(){this.readyState=1;this.onopen?.()}
 close(){this.readyState=3;this.onclose?.()}
}
function emit(map,name){for(const cb of map.get(name)||[])cb()}
const document={
 body,fullscreenElement:null,
 get visibilityState(){return screen.hidden?'hidden':'visible';},
 getElementById(id){return elements[id];},
 querySelectorAll(){return [];},
 addEventListener(name,fn){documentListeners.set(name,[...(documentListeners.get(name)||[]),fn])}
};
const window={addEventListener(name,fn){windowListeners.set(name,[...(windowListeners.get(name)||[]),fn])},matchMedia(){return {matches:portrait}},innerWidth:390,innerHeight:844,screen:{}};
const context=vm.createContext({
 RFB,WebSocket:FakeWebSocket,document,window,status,placeholder,holder,
 URLSearchParams,
 Date:{now:()=>now},
 location:{search:'?session=not-a-real-token',protocol:'https:',host:'test.example'},
 setTimeout(fn,delay){const k=id++;timers.set(k,{fn,delay});return k;},
 clearTimeout(k){timers.delete(k);},
 fetch:async()=>({ok:true}),
 encodeURIComponent,Math,
});
vm.runInContext(js,context,{filename:'live-emulator-viewer.mjs'});
assert.equal(viewers.length,1,'first screen connects at load');
assert(viewers[0].url.includes('?session=not-a-real-token'));
viewers[0].emit('connect');
assert.match(status.textContent,/Connected/);
assert.equal(controls.length,1,'remote WebSocket opens independently of display');
assert(controls[0].url.includes('/remote-ws?session=not-a-real-token'));
controls[0].open();
vm.runInContext("send('left');send('left');send('ok')",context);
assert.equal(controls[0].sent.length,3,'three D-pad commands send without waiting for a prior HTTP response');
assert.deepEqual(controls[0].sent.map(m=>m.key),['left','left','ok']);

screen.hidden=true;
emit(documentListeners,'visibilitychange');
now+=6100;
screen.hidden=false;
emit(documentListeners,'visibilitychange');
assert.equal(viewers.length,2,'backgrounded 6.1 seconds reconnects automatically');
assert.equal(viewers[1].url,viewers[0].url,'session token is retained after backgrounding');
assert.equal(viewers[0].wasDisconnected,true,'old socket is safely closed');
assert.equal(timers.size,0,'foreground resume is immediate');
viewers[1].emit('connect');
viewers[1].emit('disconnect');
assert.equal(timers.size,1,'visible network disconnect schedules automatic retry');
const retry=[...timers.values()][0];
assert(retry.delay>=100&&retry.delay<=12000,'retry has bounded backoff');
timers.clear();retry.fn();
assert.equal(viewers.length,3,'retry restores the screen');
viewers[2].emit('connect');
emit(windowListeners,'pagehide');
now+=9100;
emit(windowListeners,'pageshow');
assert.equal(viewers.length,4,'page lifecycle resume restores session');
assert.equal(viewers[3].url,viewers[0].url,'page lifecycle preserves the same token');
viewers[3].emit('connect');
viewers[3].emit('securityfailure');
assert.match(status.textContent,/access expired/i);
const n=viewers.length;
viewers[3].emit('disconnect');
assert.equal(timers.size,0,'access failure does not retry indefinitely');
reconnectButton.click();
assert.equal(viewers.length,n+1,'manual reconnect retries after access failure');
assert.equal(viewers.at(-1).url,viewers[0].url);
assert(!/location\s*\.\s*(reload|assign|replace)|window\.location\s*=/.test(js),'viewer does not navigate into Cloudflare email login on resume');
assert(!/localStorage|sessionStorage/.test(js),'bearer credential not copied into browser storage');
assert.equal(controls.length>=2,true,'remote control reconnects after background suspension');
assert.equal(controls[1].url,controls[0].url,'remote channel preserves private token after return');
const htmlButtonCount=(html.match(/data-key="(?:up|down|left|right|ok|back|home)"/g)||[]).length;
assert(htmlButtonCount>=14,'both regular and compact remotes retain all seven key types');
assert.equal(theaterToggle.attrs['aria-pressed'],undefined,'starts in non-theater mode');
theaterToggle.click();
assert(theatreClasses.has('theater-active'),'fullscreen toggle enters TV theater');
assert(theatreClasses.has('theater-rotate'),'iPhone portrait uses sideways CSS fallback');
assert.equal(theaterToggle.attrs['aria-pressed'],'true');
assert.match(theaterHint.textContent,/sideways/);
const testPointer={pointerId:1,button:0,clientX:300,clientY:600,preventDefault(){}};
remoteEvents.get('pointerdown')(testPointer);
remoteEvents.get('pointermove')({...testPointer,clientX:210,clientY:540});
assert.equal(remoteHandle.captureId,1,'drag captures only the handle pointer');
assert.equal(theaterRemote.style.left,'540px','rotated portrait X delta follows screen Y');
assert.equal(theaterRemote.style.top,'275px','rotated portrait remote remains in bounds');
remoteEvents.get('pointerup')(testPointer);
portrait=false;
emit(windowListeners,'resize');
assert(!theatreClasses.has('theater-rotate'),'landscape viewport must not remain rotated');
theaterToggle.click();
assert(!theatreClasses.has('theater-active'),'fullscreen toggle exits TV theater');
assert(!theatreClasses.has('theater-rotate'),'portrait rotation class cleared on exit');
assert.equal(theaterToggle.attrs['aria-pressed'],'false');
assert.equal(theaterToggleLabel.textContent,'Fullscreen');
assert.equal(theaterHint.textContent,'');
assert.equal(controls[0].sent.length,3,'theater toggling must not send extraneous D-pad inputs or restart video');

console.log('PASS: low-latency D-pad WebSocket, 6s iOS background resume, no lost token, bounded reconnect, landscape mini remote');
