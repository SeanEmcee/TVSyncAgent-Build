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
const holder={};
const reconnectButton={click:null,addEventListener(_name,cb){this.click=cb;}};
const elements={status,placeholder,screen:holder,reconnect:reconnectButton};
const documentListeners=new Map();
const windowListeners=new Map();
const timers=new Map();
const viewers=[];
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
const document={
 get visibilityState(){return screen.hidden?'hidden':'visible';},
 getElementById(id){return elements[id];},
 querySelectorAll(){return [];},
 addEventListener(name,fn){documentListeners.set(name,fn)}
};
const window={addEventListener(name,fn){windowListeners.set(name,fn)}};
const context=vm.createContext({
 RFB,document,window,status,placeholder,holder,
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
screen.hidden=true;
documentListeners.get('visibilitychange')();
now+=6100;
screen.hidden=false;
documentListeners.get('visibilitychange')();
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
windowListeners.get('pagehide')();
now+=9100;
windowListeners.get('pageshow')();
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
console.log('PASS: 6s iOS background resume, page restore, same-token reconnect, network backoff, auth-fail handling');
