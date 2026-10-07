// "Put it on your Home Screen" guide, for phones that can't install with one tap (every iPhone,
// and Android browsers without Chrome's install dialog). Shows numbered steps with pictures of
// the real buttons, matched to the browser:
//   - Safari on iPhone/iPad (iOS 26+: the ⋯ page menu next to the address bar, then Share;
//     older iOS: the Share button), "Add to Home Screen", keep "Open as Web App" on, Add.
//   - Chrome, Firefox, and Edge on iPhone; DuckDuckGo, Firefox, and Samsung Internet on Android.
//   - In-app browsers (Instagram, Facebook, Gmail, LinkedIn...): open the page in Safari first.
// Self-contained (styles included). Copied into each app; keep the copies in sync:
// bluey-ai-friend/install-help.js, ky-gray-portfolio/assets/install-help.js,
// nightshift-dispatch/app/static/install-help.js, and the React version of the same steps in
// pictalk/src/InstallLink.jsx.
// API: window.installHelp.{isIOS, isInstalled, browser, open(appName)}
(function(){
'use strict';
const ua=navigator.userAgent||'';
const isIOS=/iPhone|iPad|iPod/.test(ua)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
const isInstalled=()=>matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
function browser(){
 if(/FBAN|FBAV|Instagram|LinkedInApp|GSA\/|Line\/|Snapchat|Twitter|musical_ly|TikTok/i.test(ua))return 'inapp';
 if(isIOS){if(/CriOS/.test(ua))return 'ios-chrome';if(/FxiOS/.test(ua))return 'ios-firefox';if(/EdgiOS/.test(ua))return 'ios-edge';return 'ios-safari'}
 if(/DuckDuckGo/.test(ua))return 'ddg';if(/SamsungBrowser/.test(ua))return 'samsung';if(/Firefox/.test(ua))return 'firefox';return 'android';
}
// Small pictures of the buttons people look for.
const ICON={
 more:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>',
 share:'<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3M7.5 7.5 12 3l4.5 4.5"/><path d="M8 10H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-2"/></svg>',
 add:'<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M12 8v8M8 12h8"/></svg>',
 toggle:'<svg viewBox="0 0 34 20" aria-hidden="true"><rect x="1" y="1" width="32" height="18" rx="9" fill="#34c759"/><circle cx="24" cy="10" r="7.5" fill="#fff"/></svg>',
 menu:'<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
 dots:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/></svg>',
 safari:'<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z" fill="currentColor"/></svg>'
};
function steps(app){
 const add=['add','Scroll down and tap <b>Add to Home Screen</b>.','Not in the list? Tap <b>Edit Actions</b> at the bottom and add it.'];
 switch(browser()){
  case 'inapp':return{lead:'This page is open inside another app. Open it in your phone\'s browser first:',list:[['dots','Tap the <b>⋯</b> or <b>⋮</b> menu in the corner.'],['safari',`Tap <b>Open in ${isIOS?'Safari':'browser'}</b>.`],['add',`Then come back to this guide there.`]]};
  case 'ios-chrome':return{list:[['share','Tap the <b>Share</b> button in the address bar, at the top right.'],add,['add','Tap <b>Add</b>.']]};
  case 'ios-firefox':return{list:[['menu','Tap the <b>menu</b> button (three lines) at the bottom right.'],['share','Tap <b>Share</b>.'],add,['add','Tap <b>Add</b>.']]};
  case 'ios-edge':return{list:[['more','Tap the <b>⋯</b> menu at the bottom.'],['share','Tap <b>Share</b>.'],add,['add','Tap <b>Add</b>.']]};
  case 'ios-safari':return{list:[['more','Tap the <b>⋯</b> button next to the address bar.','Older iPhones: tap the Share button instead and skip to step 3.'],['share','Tap <b>Share</b>.'],add,['toggle','Keep <b>Open as Web App</b> on, then tap <b>Add</b>.']]};
  case 'ddg':return{list:[['dots','Tap the <b>⋮</b> menu.'],['add','Tap <b>Add to Home Screen</b>, then <b>Add</b>.']]};
  case 'samsung':return{list:[['menu','Tap the <b>☰</b> menu.'],['add','Tap <b>Add page to</b>, then <b>Home screen</b>.']]};
  case 'firefox':return{list:[['dots','Tap the <b>⋮</b> menu.'],['add','Tap <b>Add app to Home screen</b> (it may say <b>Install</b>).']]};
  default:return{list:[['dots','Tap the <b>⋮</b> menu at the top right.'],['add','Tap <b>Add to Home screen</b> or <b>Install app</b>.']]};
 }
}
const CSS=`.ih-back{position:fixed;inset:0;z-index:9999;background:rgba(15,25,35,.45);display:flex;align-items:flex-end;justify-content:center;padding:0 10px max(10px,env(safe-area-inset-bottom))}
.ih-sheet{width:min(440px,100%);max-height:calc(100vh - 40px);overflow-y:auto;background:#fff;color:#14263a;border-radius:20px;padding:20px 20px 16px;box-shadow:0 18px 50px rgba(0,0,0,.28);font:16px/1.45 -apple-system,system-ui,"Segoe UI",sans-serif;animation:ih-up .22s ease-out}
@keyframes ih-up{from{transform:translateY(24px);opacity:0}to{transform:none;opacity:1}}
@media(min-width:700px){.ih-back{align-items:center}}
.ih-sheet h2{margin:0 0 4px;font-size:20px;line-height:1.25}
.ih-sheet .ih-lead{margin:0 0 14px;color:#4a5d6e;font-size:15px}
.ih-sheet ol{list-style:none;margin:0;padding:0;counter-reset:ih}
.ih-sheet li{counter-increment:ih;display:grid;grid-template-columns:30px 36px 1fr;gap:10px;align-items:start;padding:10px 0;border-top:1px solid #edf1f4}
.ih-sheet li:first-child{border-top:0}
.ih-sheet li::before{content:counter(ih);display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--ih-accent,#0a78c2);color:#fff;font-weight:700;font-size:14px}
.ih-icon{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;background:#f0f4f7;color:#007aff}
.ih-icon svg{width:22px;height:22px;fill:currentColor}.ih-icon svg[fill="none"]{fill:none}
.ih-sheet li small{display:block;color:#66788a;font-size:13px;margin-top:2px}
.ih-sheet .ih-after{margin:12px 0 14px;color:#4a5d6e;font-size:15px}
.ih-sheet button{width:100%;border:0;border-radius:14px;background:var(--ih-accent,#0a78c2);color:#fff;font:600 16px/1 -apple-system,system-ui,sans-serif;padding:14px;cursor:pointer}
.ih-sheet button:focus-visible{outline:3px solid #64c8ef;outline-offset:2px}`;
function open(app,opts={}){
 if(!document.getElementById('ih-style')){const st=document.createElement('style');st.id='ih-style';st.textContent=CSS;document.head.appendChild(st)}
 const s=steps(app);const back=document.createElement('div');back.className='ih-back';back.setAttribute('role','dialog');back.setAttribute('aria-modal','true');back.setAttribute('aria-label',`Put ${app} on your Home Screen`);
 if(opts.accent)back.style.setProperty('--ih-accent',opts.accent);
 const li=s.list.map(([icon,text,small])=>`<li><span class="ih-icon">${ICON[icon]||''}</span><span>${text}${small?`<small>${small}</small>`:''}</span></li>`).join('');
 back.innerHTML=`<div class="ih-sheet"><h2>Put ${app} on your Home Screen</h2><p class="ih-lead">${s.lead||`It takes about 20 seconds. Then ${app} opens from its own icon, full screen, like an app.`}</p><ol>${li}</ol>${s.lead?'':`<p class="ih-after">Then look for the new icon on your Home Screen.</p>`}<button type="button">Got it</button></div>`;
 const close=()=>{back.remove();document.removeEventListener('keydown',esc);opts.onClose&&opts.onClose()};
 const esc=e=>{if(e.key==='Escape')close()};
 back.addEventListener('click',e=>{if(e.target===back)close()});back.querySelector('button').addEventListener('click',close);document.addEventListener('keydown',esc);
 document.body.appendChild(back);back.querySelector('button').focus({preventScroll:true});
 return back;
}
window.installHelp={isIOS,isInstalled,browser,open};
})();
