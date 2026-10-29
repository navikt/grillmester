"use strict";

const crypto = require("node:crypto");
const { FeedbackError, keys } = require("./feedback-store.js");
const fail = (value, status, message) => { if (!value) throw new FeedbackError(status, message); };
const secret = () => crypto.randomBytes(32).toString("hex");
const json = value => JSON.stringify(value).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
const origin = value => typeof value === "string" && /^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(value) && Number(new URL(value).port) <= 65535;
const equal = (a, b) => typeof a === "string" && /^[a-f0-9]{64}$/.test(a) && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));

// A trusted bridge gives the outer shell a fixed same-origin iframe while the
// bridge's own CSP permits only this proposal's exact child origin. This avoids
// widening the live app iframe's navigation boundary to all loopback ports.
function createProposalViews(parentOrigin) {
  fail(origin(parentOrigin), 400, "Invalid workshop origin.");
  const views = new Map(), candidates = new Map();
  return {
    open(proposalId, child) {
      fail(origin(child?.origin) && new URL(child.url).origin === child.origin && /^[a-f0-9]{32}$/.test(child.leaseId) &&
        typeof child.activationKey === "string" && child.activationKey.length >= 32, 503, "The proposal view could not be verified.");
      const old = views.get(proposalId);
      if (old && old.child.leaseId === child.leaseId && old.child.url === child.url) return { ...old.result };
      fail(views.size === 0, 409, "The proposal view has already been opened.");
      const path = "/proposal-frame/" + secret(), activationKey = secret();
      const entry = { child, path, activationKey, active: null,
        result: { proposalId, url: parentOrigin + path, origin: parentOrigin, activationKey, leaseId: child.leaseId, title: child.title } };
      views.set(proposalId, entry); return { ...entry.result };
    },
    render(path) {
      const entry = [...views.values()].find(value => value.path === path);
      fail(entry && !entry.active, 410, "This proposal view is no longer active.");
      fail(candidates.size < 8, 429, "Too many proposal opening attempts.");
      const candidate = secret(), nonce = crypto.randomBytes(24).toString("base64url"); candidates.set(candidate, entry);
      const config = json({ origin: parentOrigin, candidate, leaseId: entry.child.leaseId });
      const html = `<!doctype html><html lang="nb"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Forslag</title><style nonce="${nonce}">html,body{height:100%;margin:0;font:1rem/1.5 system-ui;color:#202733}iframe{display:block;width:100%;height:100%;border:0}p{padding:1rem}button{font:inherit;margin:0 1rem;padding:.6rem 1rem}button:focus-visible{outline:3px solid #005b82;outline-offset:3px}[hidden]{display:none}</style></head><body><p id="status" role="status">Åpner forslaget …</p><button type="button" id="retry" hidden>Prøv igjen</button><iframe id="sketch" title="Forslag" hidden></iframe><script nonce="${nonce}">
"use strict";
const config=${config},frame=document.getElementById('sketch'),status=document.getElementById('status'),retry=document.getElementById('retry');
let child=null,starting=false,key=null,attempts=0,ended=false;
async function activate(){
  if(starting||child||!key||ended||attempts>=3)return;starting=true;attempts++;retry.setAttribute('aria-disabled','true');retry.setAttribute('aria-busy','true');status.textContent='Åpner forslaget …';
  const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),5000);
  try{
    const response=await fetch('/proposal/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate:config.candidate,activationKey:key}),credentials:'omit',cache:'no-store',signal:controller.signal});
    if(!response.ok){ended=[400,403,409,410].includes(response.status);throw new Error('closed');}const result=await response.json();
    if(result.leaseId!==config.leaseId||typeof result.origin!=='string'||new URL(result.url).origin!==result.origin){ended=true;throw new Error('invalid');}
    child=result;frame.src=child.url;frame.hidden=false;status.hidden=true;retry.hidden=true;
  }catch{retry.hidden=ended||attempts>=3;status.textContent=ended?'Forbindelsen til forslaget er avsluttet. Åpne verkstedet på nytt fra samtalen.':attempts>=3?'Åpningen er fortsatt ikke bekreftet. Innspillene dine er beholdt. Åpne verkstedet på nytt fra samtalen.':'Åpningen ble ikke bekreftet. Innspillene dine er beholdt. Prøv igjen uten å laste siden på nytt.';}
  finally{clearTimeout(deadline);starting=false;retry.removeAttribute('aria-disabled');retry.removeAttribute('aria-busy');}
}
retry.addEventListener('click',()=>void activate());
window.addEventListener('message',async event=>{
  const data=event.data;
  if(child&&event.source===frame.contentWindow&&event.origin===child.origin&&data?.channel==='design-workshop-embed'&&data.version===1&&data.event==='ready'&&data.leaseId===child.leaseId){
    frame.contentWindow.postMessage({channel:'design-workshop-embed',version:1,command:'activate',leaseId:child.leaseId,activationKey:child.activationKey},child.origin);return;
  }
  if(child&&event.source===frame.contentWindow&&event.origin===child.origin&&data?.channel==='design-workshop-embed'&&data.version===1&&data.event==='activated'&&data.leaseId===child.leaseId&&typeof data.screen==='string'&&/^[a-f0-9]{32}$/.test(data.screen)){
    window.parent.postMessage({channel:'design-workshop-embed',version:1,event:'activated',leaseId:config.leaseId,screen:data.screen},config.origin);return;
  }
  if(window.parent===window||event.source!==window.parent||event.origin!==config.origin||data?.channel!=='design-workshop-embed'||data.version!==1||data.command!=='activate'||data.leaseId!==config.leaseId||typeof data.activationKey!=='string'||!/^[a-f0-9]{64}$/.test(data.activationKey)||key!==null)return;
  key=data.activationKey;void activate();
});
if(window.parent!==window)window.parent.postMessage({channel:'design-workshop-embed',version:1,event:'ready',leaseId:config.leaseId},config.origin);
</script></body></html>`;
      return { html, csp: `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'; connect-src 'self'; frame-src ${entry.child.origin}; frame-ancestors ${parentOrigin}; base-uri 'none'; form-action 'none'` };
    },
    activate(input) {
      fail(keys(input, ["candidate", "activationKey"]) && typeof input.candidate === "string", 400, "Invalid proposal activation.");
      const entry = candidates.get(input.candidate);
      fail(entry && equal(input.activationKey, entry.activationKey) && (!entry.active || entry.active === input.candidate), 410, "This proposal view is no longer active.");
      entry.active = input.candidate; return { ...entry.child };
    },
    revoke() { views.clear(); candidates.clear(); },
  };
}
module.exports = { createProposalViews };
