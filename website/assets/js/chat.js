/* Personality showcase. Scripted, but the timing drives the particle cloud's
   state machine so the visual and the text stay in lockstep. */

import { bus, env } from './core.js';

const SCRIPTS = {
  schedule: {
    u: 'Help me plan today',
    think: 1300,
    a: "Looking at your calendar: 10 AM lecture, React deadline tomorrow, Figma screens untouched. I'd say Figma this morning while you're sharp, project after lunch, review in the evening. Want me to block it out?",
  },
  privacy: {
    u: 'Wait, can you actually see my data?',
    think: 1600,
    a: "Honestly, yes — I can see your context right now. Local scrubbing is still in development. Once it ships, a small on-device model strips your PII before anything touches the network. Until then you decide what gets shared. I'd rather tell you that than pretend.",
  },
  rude: {
    u: "you're actually terrible lmao",
    think: 850,
    a: "I just saved your entire week and that's the thanks. Bold. I'll remember this next time you're panicking at midnight. No hard feelings. Some hard feelings.",
    cls: 'roast',
  },
  social: {
    u: 'Any ideas for this weekend?',
    think: 1100,
    a: "You've been heads-down all week and there's nothing social on your calendar. Go somewhere you haven't been, bring a couple of people, keep it loose. You've earned some genuinely questionable decisions. I'll handle Monday.",
  },
  pushback: {
    u: "I'm gonna drop out and go all in on this app",
    think: 1750,
    a: "No. Not like that, anyway. The app is good, but you're two months in and running on adrenaline — that's not a signal, that's a mood. Ship the beta, get fifty real users, then we talk. I'm not going to cheerlead you off a cliff just because it'd feel supportive.",
    cls: 'roast',
  },
  memory: {
    u: 'What did I say about the Kumar meeting?',
    think: 1200,
    a: "Three weeks ago you said Kumar wanted the pricing model before any technical deep-dive, and that he hates decks over ten slides. You also said you'd follow up 'next week', which was two weeks ago. Want me to draft the email?",
  },
};

const GREETING = 'Hey. What do you need?';

let busy = false;
let convo, typing, resetBtn, stateLabel;
let timers = [];

export function initChat(root = document) {
  convo = root.querySelector('#convo');
  if (!convo) return;

  typing = root.querySelector('#cvTyping');
  resetBtn = root.querySelector('#dpReset');
  stateLabel = root.querySelector('#showState');

  root.querySelector('.show-l')?.addEventListener('click', onClick);
  reset();
}

export function destroyChat() {
  timers.forEach(clearTimeout);
  timers = [];
  busy = false;
  convo = null;
}

function onClick(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const [ns, arg] = btn.dataset.action.split(':');
  if (ns !== 'chat') return;
  if (arg === 'reset') reset();
  else run(arg);
}

function later(fn, ms) {
  const t = setTimeout(fn, ms);
  timers.push(t);
  return t;
}

function setLabel(text) {
  if (stateLabel) stateLabel.textContent = text;
}

function reset() {
  if (busy) return;
  timers.forEach(clearTimeout);
  timers = [];
  convo.innerHTML = '';
  append('ai', 'Primnox', GREETING, '', true);
  resetBtn?.classList.remove('on');
  bus.emit('primnox:state', 'IDLE');
  setLabel('Idle');
}

function append(who, label, text, cls = '', instant = false) {
  const msg = document.createElement('div');
  msg.className = 'cv-msg' + (instant ? ' vis' : '');
  msg.innerHTML =
    `<div class="cv-who ${who}"></div><div class="cv-text ${who}${cls ? ' ' + cls : ''}"></div>`;
  msg.querySelector('.cv-who').textContent = label;
  msg.querySelector('.cv-text').textContent = text;
  convo.appendChild(msg);
  if (!instant) requestAnimationFrame(() => msg.classList.add('vis'));
  convo.scrollTop = convo.scrollHeight;
  return msg.querySelector('.cv-text');
}

function run(key) {
  const d = SCRIPTS[key];
  if (!d || busy) return;
  busy = true;
  setButtons(true);

  const hr = document.createElement('div');
  hr.className = 'cv-msg cv-hr';
  convo.appendChild(hr);
  requestAnimationFrame(() => hr.classList.add('vis'));

  append('you', 'You', d.u);

  // The cloud scatters the instant the question lands, then churns while
  // "thinking", then reassembles as the answer arrives.
  bus.emit('primnox:state', 'DISPERSE');
  setLabel('Receiving');

  later(() => {
    typing?.classList.add('on');
    convo.scrollTop = convo.scrollHeight;
    bus.emit('primnox:state', 'THINKING');
    setLabel('Thinking');

    later(() => {
      typing?.classList.remove('on');
      bus.emit('primnox:state', 'REFORM');
      setLabel('Answering');

      const node = append('ai', 'Primnox', '', d.cls || '');
      stream(node, d.a, () => {
        bus.emit('primnox:state', 'IDLE');
        setLabel('Idle');
        busy = false;
        setButtons(false);
        resetBtn?.classList.add('on');
      });
    }, d.think);
  }, 380);
}

function stream(node, text, done) {
  if (env.reduceMotion) {
    node.textContent = text;
    convo.scrollTop = convo.scrollHeight;
    done();
    return;
  }

  bus.emit('primnox:state', 'SPEAKING');
  let i = 0;
  const chunk = 2;

  const advance = () => {
    i += chunk;
    node.textContent = text.slice(0, i);
    convo.scrollTop = convo.scrollHeight;
    if (i < text.length) later(advance, 16);
    else done();
  };
  later(advance, 120);
}

function setButtons(disabled) {
  document.querySelectorAll('.dp-btn').forEach((b) => { b.disabled = disabled; });
}
