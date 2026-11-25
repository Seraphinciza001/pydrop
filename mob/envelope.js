// Animation de l'enveloppe, partagée par l'interface PC et la page téléphone.
//   PyEnvelope.send(de, vers, opts)    : le fichier entre dans l'enveloppe, qui part et entre dans la cible
//   PyEnvelope.receive(de, vers, opts) : l'enveloppe sort de l'expéditeur, arrive et s'ouvre
// « de » et « vers » sont des éléments du DOM ou des points { x, y }.
(function () {
  const style = document.createElement('style');
  style.textContent = `
.pe-env { position: fixed; left: 0; top: 0; width: 84px; height: 58px; margin: -29px 0 0 -42px; z-index: 200; pointer-events: none;
  perspective: 300px; filter: drop-shadow(0 10px 22px rgba(0,0,0,.55)) drop-shadow(0 0 16px rgba(56,189,248,.45)); will-change: transform; }
.pe-part { position: absolute; left: 0; right: 0; }
.pe-back { top: 0; bottom: 0; border-radius: 7px; background: #cfe3f7; }
.pe-letter { left: 9px; right: 9px; top: 5px; height: 48px; border-radius: 4px; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.25);
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; color: #0366d6;
  font: 800 11px system-ui, "Segoe UI", sans-serif; text-transform: uppercase; overflow: hidden; }
.pe-letter i { display: block; width: 60%; height: 3px; border-radius: 2px; background: #dbe5f0; }
.pe-front { top: 0; bottom: 0; border-radius: 7px; background: linear-gradient(160deg, #eaf4fd, #bcd6ef);
  clip-path: polygon(0 0, 50% 58%, 100% 0, 100% 100%, 0 100%); }
.pe-flap { top: 0; height: 36px; background: linear-gradient(180deg, #38bdf8, #0284c7); clip-path: polygon(0 0, 100% 0, 50% 100%);
  transform-origin: 50% 0; backface-visibility: visible; }
.pe-count { position: absolute; right: -8px; top: -8px; min-width: 22px; height: 22px; padding: 0 5px; border-radius: 11px; background: #f68b1e; color: #fff;
  font: 800 12px/22px system-ui, "Segoe UI", sans-serif; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,.4); }
.pe-ring { position: fixed; left: 0; top: 0; width: 60px; height: 60px; margin: -30px 0 0 -30px; border-radius: 50%; border: 3px solid #38bdf8; z-index: 199; pointer-events: none; }
.pe-spark { position: fixed; left: 0; top: 0; width: 6px; height: 6px; margin: -3px 0 0 -3px; border-radius: 50%; z-index: 198; pointer-events: none; }
`;
  document.head.appendChild(style);

  const reduced = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const center = t => {
    if (!(t instanceof Element)) return t;
    const r = t.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function build(label, count) {
    const el = document.createElement('div');
    el.className = 'pe-env';
    el.innerHTML = `<div class="pe-part pe-back"></div>
      <div class="pe-part pe-flap"></div>
      <div class="pe-part pe-letter"><span>${esc(label)}</span><i></i><i></i></div>
      <div class="pe-part pe-front"></div>
      ${count > 1 ? `<div class="pe-count">${count}</div>` : ''}`;
    document.body.appendChild(el);
    return {
      el,
      flap: el.querySelector('.pe-flap'),
      letter: el.querySelector('.pe-letter'),
      front: el.querySelector('.pe-front'),
    };
  }
  const flapOpen = e => { e.flap.style.transform = 'rotateX(180deg)'; e.flap.style.zIndex = 0; };
  const flapClosed = e => { e.flap.style.transform = 'rotateX(0deg)'; e.flap.style.zIndex = 3; };
  const at = (p, scale = 1, rot = 0) => `translate(${p.x}px, ${p.y}px) scale(${scale}) rotate(${rot}deg)`;

  // Trajectoire en arc entre deux points
  function arc(a, b, s0, s1, fadeIn, fadeOut) {
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
    const bow = Math.min(90, len * .25);
    const c = { x: (a.x + b.x) / 2 - dy / len * bow, y: (a.y + b.y) / 2 + dx / len * bow };
    const frames = [];
    for (let i = 0; i <= 16; i++) {
      const t = i / 16, u = 1 - t;
      const p = { x: u * u * a.x + 2 * u * t * c.x + t * t * b.x, y: u * u * a.y + 2 * u * t * c.y + t * t * b.y };
      const scale = s0 + (s1 - s0) * t * t;
      frames.push({
        transform: at(p, scale, Math.sin(t * Math.PI) * (dx >= 0 ? 8 : -8)),
        opacity: fadeIn && t < .12 ? t / .12 : fadeOut && t > .9 ? (1 - t) / .1 : 1,
      });
    }
    return frames;
  }
  function ring(p, color) {
    const r = document.createElement('div');
    r.className = 'pe-ring';
    r.style.borderColor = color;
    document.body.appendChild(r);
    const a = r.animate(
      [{ transform: `translate(${p.x}px, ${p.y}px) scale(.5)`, opacity: .9 }, { transform: `translate(${p.x}px, ${p.y}px) scale(2.3)`, opacity: 0 }],
      { duration: 650, easing: 'ease-out' });
    a.finished.finally(() => r.remove());
  }
  function sparks(p, color) {
    for (let i = 0; i < 12; i++) {
      const s = document.createElement('div');
      s.className = 'pe-spark';
      s.style.background = i % 2 ? color : '#f68b1e';
      document.body.appendChild(s);
      const ang = i / 12 * Math.PI * 2, d = 34 + (i % 3) * 16;
      const a = s.animate(
        [{ transform: `translate(${p.x}px, ${p.y}px) scale(1)`, opacity: 1 },
         { transform: `translate(${p.x + Math.cos(ang) * d}px, ${p.y + Math.sin(ang) * d}px) scale(.2)`, opacity: 0 }],
        { duration: 600, easing: 'cubic-bezier(.2,.7,.3,1)' });
      a.finished.finally(() => s.remove());
    }
  }
  function gulp(t) {
    if (!(t instanceof Element)) return;
    t.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.28)' }, { transform: 'scale(.94)' }, { transform: 'scale(1)' }],
      { duration: 520, easing: 'ease-out' });
  }

  async function send(from, to, opts = {}) {
    if (reduced()) return;
    const a = center(from), b = center(to);
    if (!a || !b) return;
    const e = build(opts.label, opts.count || 1);
    e.el.style.transform = at(a, 1);
    flapOpen(e);
    // 1. L'enveloppe apparaît, la feuille descend dedans, le rabat se ferme
    e.el.animate([{ transform: at(a, .3), opacity: 0 }, { transform: at(a, 1.1), opacity: 1 }, { transform: at(a, 1), opacity: 1 }],
      { duration: 260, easing: 'ease-out' });
    await e.letter.animate([{ transform: 'translateY(-46px)', opacity: 0 }, { transform: 'translateY(-46px)', opacity: 1, offset: .35 }, { transform: 'translateY(0)', opacity: 1 }],
      { duration: 520, easing: 'cubic-bezier(.4,0,.3,1)', fill: 'both' }).finished;
    e.flap.style.zIndex = 3;
    await e.flap.animate([{ transform: 'rotateX(180deg)' }, { transform: 'rotateX(0deg)' }],
      { duration: 240, easing: 'ease-in-out', fill: 'both' }).finished;
    flapClosed(e);
    gulp(from);
    // 2. Elle s'envole et 3. entre dans l'appareil cible
    const fly = e.el.animate(arc(a, b, 1, .16, false, true), { duration: 820, easing: 'cubic-bezier(.45,.05,.4,1)', fill: 'forwards' });
    await fly.finished;
    e.el.remove();
    gulp(to);
    ring(b, '#22c55e');
    sparks(b, '#22c55e');
  }

  async function receive(from, to, opts = {}) {
    if (reduced()) return;
    const a = center(from), b = center(to);
    if (!a || !b) return;
    const e = build(opts.label, opts.count || 1);
    flapClosed(e);
    gulp(from);
    ring(a, '#38bdf8');
    // 1. L'enveloppe sort de l'expéditeur et vient jusqu'ici
    const fly = e.el.animate(arc(a, b, .16, 1.15, true, false), { duration: 820, easing: 'cubic-bezier(.3,.6,.3,1)', fill: 'forwards' });
    await fly.finished;
    gulp(to);
    // 2. Elle s'ouvre, la feuille sort, tout s'efface
    await e.flap.animate([{ transform: 'rotateX(0deg)' }, { transform: 'rotateX(180deg)' }],
      { duration: 240, easing: 'ease-in-out', fill: 'both' }).finished;
    flapOpen(e);
    sparks(b, '#38bdf8');
    await e.letter.animate([{ transform: 'translateY(0)' }, { transform: 'translateY(-44px)' }],
      { duration: 340, easing: 'cubic-bezier(.2,.8,.3,1)', fill: 'both' }).finished;
    await e.el.animate([{ transform: at(b, 1.15), opacity: 1 }, { transform: at(b, .5), opacity: 0 }],
      { duration: 280, easing: 'ease-in', fill: 'forwards' }).finished;
    e.el.remove();
  }

  // Étiquette courte affichée sur la feuille : l'extension du fichier, ou DOSSIER
  function label(name, isDir) {
    if (isDir) return 'dossier';
    const parts = String(name || '').split('.');
    return parts.length > 1 ? parts.pop().slice(0, 5) : 'fichier';
  }

  window.PyEnvelope = { send, receive, label };
})();
