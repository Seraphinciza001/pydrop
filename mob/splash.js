// Écran de chargement PyDrop, partagé par l'interface PC et la page téléphone.
// À inclure tout au début de <body>.  PySplash.step('texte')  ·  PySplash.done(dureeMinimaleMs)
(function () {
  if (window.PySplash) return;
  const logo = window.PYSPLASH_LOGO || 'SVG%20Mobile/logo.png';
  const style = document.createElement('style');
  style.textContent = `
#pysplash { position: fixed; inset: 0; z-index: 1000; display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: radial-gradient(circle at 50% 40%, #12284a 0%, #0a1426 38%, #070b16 72%); color: #e8eef9; overflow: hidden;
  font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, -apple-system, Roboto, sans-serif;
  transition: opacity .7s ease, visibility .7s; user-select: none; }
#pysplash.out { opacity: 0; visibility: hidden; }
#pysplash.out .ps-orb { transform: scale(1.35); opacity: 0; }
#pysplash .ps-grid { position: absolute; inset: -50%; background-image: radial-gradient(rgba(56,189,248,.16) 1px, transparent 1.4px);
  background-size: 28px 28px; mask: radial-gradient(circle at 50% 50%, #000 0, transparent 45%); -webkit-mask: radial-gradient(circle at 50% 50%, #000 0, transparent 45%);
  animation: psDrift 18s linear infinite; }
#pysplash .ps-orb { position: relative; width: 156px; height: 156px; display: grid; place-items: center; transition: transform .7s cubic-bezier(.3,.7,.3,1), opacity .6s; }
#pysplash .ps-ring { position: absolute; inset: 0; border-radius: 50%; border: 2px solid rgba(56,189,248,.55); opacity: 0; animation: psRipple 2.7s cubic-bezier(.2,.6,.3,1) infinite; }
#pysplash .ps-ring:nth-child(2) { animation-delay: .9s; border-color: rgba(246,139,30,.5); }
#pysplash .ps-ring:nth-child(3) { animation-delay: 1.8s; }
#pysplash .ps-spin { position: absolute; inset: -16px; border-radius: 50%;
  background: conic-gradient(from 0deg, transparent 0 55%, rgba(56,189,248,.9) 78%, #f68b1e 100%);
  mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 2.5px));
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 2.5px));
  animation: psSpin 1.3s linear infinite; }
#pysplash .ps-orbit { position: absolute; inset: -40px; animation: psSpin 3.6s linear infinite; }
#pysplash .ps-orbit.b { inset: -58px; animation-duration: 5.4s; animation-direction: reverse; }
#pysplash .ps-orbit i { position: absolute; top: -4px; left: 50%; width: 8px; height: 8px; margin-left: -4px; border-radius: 50%;
  background: #38bdf8; box-shadow: 0 0 12px 3px rgba(56,189,248,.8); }
#pysplash .ps-orbit.b i { background: #f68b1e; box-shadow: 0 0 12px 3px rgba(246,139,30,.8); width: 6px; height: 6px; }
#pysplash .ps-core { position: relative; width: 116px; height: 116px; border-radius: 50%; display: grid; place-items: center;
  background: radial-gradient(circle at 35% 28%, #1d3157, #0b1426 70%); border: 2px solid rgba(56,189,248,.45);
  box-shadow: 0 0 0 10px rgba(56,189,248,.06), 0 0 60px rgba(56,189,248,.35), inset 0 0 24px rgba(56,189,248,.2);
  animation: psBeat 1.8s ease-in-out infinite; }
#pysplash .ps-core img { width: 70%; height: 70%; object-fit: contain; filter: drop-shadow(0 6px 14px rgba(0,0,0,.45)); animation: psFloat 3s ease-in-out infinite; }
#pysplash .ps-title { margin-top: 42px; font-size: 38px; font-weight: 800; letter-spacing: -.8px; display: flex; }
#pysplash .ps-title span { display: inline-block; opacity: 0; transform: translateY(14px); animation: psRise .6s cubic-bezier(.2,.9,.3,1.2) forwards; }
#pysplash .ps-title .p { color: #38bdf8; } #pysplash .ps-title .d { color: #f68b1e; }
#pysplash .ps-step { margin-top: 10px; height: 20px; font-size: 14px; color: #8b9ab3; transition: opacity .25s; }
#pysplash .ps-bar { margin-top: 18px; width: 190px; height: 4px; border-radius: 9px; background: rgba(148,163,184,.14); overflow: hidden; position: relative; }
#pysplash .ps-bar i { position: absolute; top: 0; bottom: 0; width: 40%; border-radius: 9px; background: linear-gradient(90deg, transparent, #38bdf8, #f68b1e, transparent);
  animation: psSlide 1.25s ease-in-out infinite; }
#pysplash .ps-sign { position: absolute; bottom: max(26px, env(safe-area-inset-bottom)); font-size: 13px; color: #5b6a85; letter-spacing: .5px; }
#pysplash .ps-sign b { background: linear-gradient(90deg, #38bdf8, #f68b1e); -webkit-background-clip: text; background-clip: text; color: transparent; font-weight: 800; }
@keyframes psRipple { 0% { transform: scale(.75); opacity: .9; } 100% { transform: scale(2.3); opacity: 0; } }
@keyframes psSpin { to { transform: rotate(360deg); } }
@keyframes psBeat { 0%,100% { transform: scale(1); } 14% { transform: scale(1.07); } 28% { transform: scale(.98); } 42% { transform: scale(1.04); } 60% { transform: scale(1); } }
@keyframes psFloat { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
@keyframes psRise { to { opacity: 1; transform: translateY(0); } }
@keyframes psSlide { 0% { left: -40%; } 100% { left: 100%; } }
@keyframes psDrift { to { transform: translate(28px, 28px); } }
@media (prefers-reduced-motion: reduce) { #pysplash * { animation-duration: 0s !important; animation-iteration-count: 1 !important; } }
`;
  document.head.appendChild(style);

  const el = document.createElement('div');
  el.id = 'pysplash';
  const letters = [...'Py'].map(c => ['p', c]).concat([...'Drop'].map(c => ['d', c]));
  el.innerHTML = `<div class="ps-grid"></div>
    <div class="ps-orb">
      <div class="ps-ring"></div><div class="ps-ring"></div><div class="ps-ring"></div>
      <div class="ps-orbit"><i></i></div><div class="ps-orbit b"><i></i></div>
      <div class="ps-spin"></div>
      <div class="ps-core"><img src="${logo}" alt=""></div>
    </div>
    <div class="ps-title">${letters.map(([k, c], i) => `<span class="${k}" style="animation-delay:${.15 + i * .07}s">${c}</span>`).join('')}</div>
    <div class="ps-step" id="psStep">Démarrage…</div>
    <div class="ps-bar"><i></i></div>
    <div class="ps-sign">By <b>Seraphin</b></div>`;
  (document.body || document.documentElement).prepend(el);

  const t0 = Date.now();
  let closing = false;
  window.PySplash = {
    step(text) {
      const s = document.getElementById('psStep');
      if (!s || s.textContent === text) return;
      s.style.opacity = 0;
      setTimeout(() => { s.textContent = text; s.style.opacity = 1; }, 200);
    },
    done(min = 1400) {
      if (closing) return;
      closing = true;
      setTimeout(() => {
        el.classList.add('out');
        setTimeout(() => el.remove(), 800);
      }, Math.max(0, min - (Date.now() - t0)));
    },
  };
  // Filet de sécurité : l'écran ne reste jamais bloqué
  setTimeout(() => window.PySplash.done(0), 15000);
})();
