"use strict";
const crypto = require('node:crypto');
const closed = (value, required) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === required.length && required.every(key => Object.hasOwn(value, key));
const fail = (condition, status, message) => { if (!condition) throw Object.assign(new Error(message), { status, expose: true }); };
const opaque = () => crypto.randomBytes(32).toString('hex');
const safeEqual = (left, right) => typeof left === 'string' && typeof right === 'string' && /^[a-f0-9]{64}$/.test(left) && /^[a-f0-9]{64}$/.test(right)
  && crypto.timingSafeEqual(Buffer.from(left), Buffer.from(right));
function createHtmlEmbedding(input) {
  let origin = null; try { origin = new URL(input?.parentOrigin).origin; } catch { /* Invalid input stays a bounded validation error. */ }
  fail(closed(input, ['parentOrigin', 'leaseId']) && /^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(input.parentOrigin)
    && origin === input.parentOrigin && /^[a-f0-9]{32}$/.test(input.leaseId), 400, 'Invalid workshop embedding.');
  const parentOrigin = input.parentOrigin, leaseId = input.leaseId, invitation = opaque(), activationKey = opaque();
  const candidates = new Map(); let active = null, revoked = false;
  return {
    parentOrigin, leaseId, invitation, activationKey,
    candidate(value) {
      fail(!revoked && safeEqual(value, invitation), 410, 'The proposal view has expired.');
      fail(!active && candidates.size < 8, 409, 'This proposal is already open. Return to the workshop.');
      const id = opaque(), nonce = crypto.randomBytes(18).toString('base64url');
      candidates.set(id, { nonce }); return { candidate: id, nonce };
    },
    activate(input) {
      fail(!revoked, 410, 'The proposal view has expired.');
      fail(closed(input, ['candidate', 'activationKey']) && safeEqual(input.activationKey, activationKey)
        && candidates.has(input.candidate), 403, 'Proposal activation is unavailable.');
      fail(!active || active === input.candidate, 409, 'This proposal is already open. Return to the workshop.');
      active = input.candidate;
      return { nonce: candidates.get(active).nonce };
    },
    get active() { return !revoked && active !== null; },
    revoke() { revoked = true; active = null; candidates.clear(); },
  };
}
function renderEmbeddingBootstrap({ parentOrigin, leaseId, candidate, nonce }) {
  const config = JSON.stringify({ parentOrigin, leaseId, candidate }).replace(/</g, '\\u003c');
  return `<!doctype html><html lang="nb"><meta charset="utf-8"><title>Forslag</title><body>
<p role="status" aria-live="polite">Åpner forslaget …</p><button type="button" hidden>Prøv igjen</button>
<script nonce="${nonce}">(()=>{'use strict';const config=${config};let pending=false,done=false,key=null,attempts=0;
const status=document.querySelector('[role=status]'),retry=document.querySelector('button');
async function activate(){
  if(done||pending||!key||attempts>=3)return;
  attempts++;pending=true;retry.disabled=true;retry.setAttribute('aria-busy','true');status.textContent='Åpner forslaget …';
  const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),5000);
  let definite=false;
  try{
    const response=await fetch('/embedded/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate:config.candidate,activationKey:key}),credentials:'omit',cache:'no-store',signal:controller.signal});
    if(!response.ok){definite=[400,403,409,410].includes(response.status);throw new Error('unavailable');}
    const html=await response.text();done=true;document.open();document.write(html);document.close();
  }catch{
    retry.hidden=definite||attempts>=3;
    status.textContent=definite?'Forbindelsen til forslaget er avsluttet. Åpne verkstedet på nytt fra samtalen.':attempts>=3?'Åpningen er fortsatt ikke bekreftet. Forslaget er beholdt. Åpne verkstedet på nytt fra samtalen.':'Åpningen ble ikke bekreftet. Forslaget er beholdt. Prøv igjen uten å laste siden på nytt.';
  }finally{clearTimeout(deadline);pending=false;if(!done){retry.disabled=false;retry.removeAttribute('aria-busy');}}
}
retry.addEventListener('click',()=>{void activate();});
window.addEventListener('message',event=>{
  const data=event.data;
  if(done||pending||key!==null||window.parent===window||event.source!==window.parent||event.origin!==config.parentOrigin||!data||data.channel!=='design-workshop-embed'||data.version!==1||data.command!=='activate'||data.leaseId!==config.leaseId||typeof data.activationKey!=='string'||!/^[a-f0-9]{64}$/.test(data.activationKey))return;
  key=data.activationKey;void activate();
});
if(window.parent!==window)window.parent.postMessage({channel:'design-workshop-embed',version:1,event:'ready',leaseId:config.leaseId},config.parentOrigin);
else status.textContent='Åpne forslaget fra verkstedet.';
})();</script></body></html>`;
}
module.exports = { createHtmlEmbedding, renderEmbeddingBootstrap };
