/* GROUND CONTROL — landing interactions */
(() => {
  'use strict';

  /* ---- UTC mission clock ---- */
  const clock = document.getElementById('utc-clock');
  if (clock) {
    const tick = () => {
      const d = new Date();
      const p = (n) => String(n).padStart(2, '0');
      clock.textContent =
        `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
    };
    tick();
    setInterval(tick, 1000);
  }

  /* ---- footer stamp date ---- */
  const stamp = document.getElementById('footer-stamp');
  if (stamp) {
    const y = new Date().getUTCFullYear();
    stamp.textContent = `GROUND CONTROL // SP STATION // R001 // ${y}`;
  }

  /* ---- reduced motion flag (used elsewhere) ---- */
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  /* Reveal-on-scroll desativado de propósito: o conteúdo nunca deve depender
     de JS/observer para ser visível (quebra em screenshots, impressão, no-JS).
     A entrada animada fica só na hero, via keyframe CSS puro. */

  /* ---- count-up telemetry (only numeric) ---- */
  const counters = document.querySelectorAll('.tm-v[data-count]');
  if (!reduce && 'IntersectionObserver' in window) {
    const co = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          const el = e.target;
          const target = parseInt(el.getAttribute('data-count'), 10);
          if (Number.isNaN(target) || target === 0) {
            co.unobserve(el);
            return;
          }
          const prefix = el.textContent.trim().startsWith('R$') ? 'R$ ' : '';
          let cur = 0;
          const step = Math.max(1, Math.round(target / 28));
          const run = () => {
            cur = Math.min(target, cur + step);
            el.textContent = prefix + cur;
            if (cur < target) requestAnimationFrame(run);
          };
          run();
          co.unobserve(el);
        });
      },
      { threshold: 0.6 }
    );
    counters.forEach((c) => co.observe(c));
  }

  /* ---- smooth anchor + history ---- */
  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener('click', (ev) => {
      const id = a.getAttribute('href').slice(1);
      const t = document.getElementById(id);
      if (!t) return;
      ev.preventDefault();
      t.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
      history.replaceState(null, '', `#${id}`);
    });
  });

  /* ---- demo form: graceful, no backend yet ---- */
  const form = document.getElementById('demo-form');
  const note = document.getElementById('df-note');
  if (form && note) {
    const DEFAULT = note.textContent;
    form.addEventListener('submit', (ev) => {
      ev.preventDefault();
      const data = new FormData(form);
      const nome = (data.get('nome') || '').toString().trim();
      const email = (data.get('email') || '').toString().trim();
      const empresa = (data.get('empresa') || '').toString().trim();
      const agentes = (data.get('agentes') || '').toString().trim();
      const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

      if (!nome || !emailOk || !empresa) {
        note.textContent = 'PREENCHA NOME, E-MAIL VÁLIDO E EMPRESA';
        note.classList.remove('ok');
        note.classList.add('err');
        return;
      }

      // Sem backend conectado ainda: abre o cliente de e-mail com tudo pronto.
      const subject = encodeURIComponent('Demonstração Ground Control — ' + empresa);
      const body = encodeURIComponent(
        `Nome: ${nome}\nE-mail: ${email}\nMSP/Empresa: ${empresa}\nAgentes: ${agentes || 'n/d'}\n\nGostaria de agendar uma demonstração da plataforma Ground Control.`
      );
      window.location.href =
        `mailto:contato@was.dev.br?subject=${subject}&body=${body}`;

      note.textContent = 'ABRINDO CANAL · CONFIRME O ENVIO NO SEU E-MAIL';
      note.classList.remove('err');
      note.classList.add('ok');
      setTimeout(() => {
        note.textContent = DEFAULT;
        note.classList.remove('ok');
      }, 6000);
    });
  }

  console.info(
    '%c GROUND CONTROL ',
    'background:#FF6B1A;color:#0A0A0A;font-weight:700;padding:3px 8px;letter-spacing:.1em'
  );
  console.info('Service Desk platform · white-label · MSP-first · engineered by WAS');
})();
