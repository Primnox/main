/* BIP-39 mnemonic generation.

   A 12-word phrase is NOT 12 independent random words. It is 128 bits of
   entropy plus a 4-bit SHA-256 checksum, packed into 132 bits and sliced into
   twelve 11-bit indices. Picking 12 uniform words satisfies the checksum with
   probability 1/16, so ~94% of such phrases are rejected by any standard
   BIP-39 implementation on restore — after the user has written them down. */

import { WORDLIST } from './wordlist.js';

const WORD_COUNT = 12;
const ENTROPY_BYTES = 16;      // 128 bits
const CHECKSUM_BITS = 4;       // ENT / 32
const INDEX_BITS = 11;

let current = [];
let grid, checkEl, copyBtn;

const bitAt = (bytes, i) => (bytes[i >> 3] >> (7 - (i & 7))) & 1;

async function generateMnemonic() {
  const entropy = new Uint8Array(ENTROPY_BYTES);
  crypto.getRandomValues(entropy);

  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', entropy));
  const entropyBits = ENTROPY_BYTES * 8;

  const words = [];
  for (let w = 0; w < WORD_COUNT; w++) {
    let index = 0;
    for (let b = 0; b < INDEX_BITS; b++) {
      const pos = w * INDEX_BITS + b;
      const bit = pos < entropyBits
        ? bitAt(entropy, pos)
        : bitAt(digest, pos - entropyBits);
      index = (index << 1) | bit;
    }
    words.push(WORDLIST[index]);
  }
  return words;
}

/* Round-trips the phrase back to entropy and re-derives the checksum, so the
   badge on the page reflects a real verification rather than a claim. */
async function verifyMnemonic(words) {
  if (words.length !== WORD_COUNT) return false;

  const bits = [];
  for (const word of words) {
    const idx = WORDLIST.indexOf(word);
    if (idx < 0) return false;
    for (let b = INDEX_BITS - 1; b >= 0; b--) bits.push((idx >> b) & 1);
  }

  const entropyBits = bits.length - CHECKSUM_BITS;
  const entropy = new Uint8Array(entropyBits / 8);
  for (let i = 0; i < entropyBits; i++) {
    if (bits[i]) entropy[i >> 3] |= 1 << (7 - (i & 7));
  }

  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', entropy));
  for (let i = 0; i < CHECKSUM_BITS; i++) {
    if (bits[entropyBits + i] !== bitAt(digest, i)) return false;
  }
  return true;
}

export function initSeed(root = document) {
  grid = root.querySelector('#seedGrid');
  if (!grid) return;

  checkEl = root.querySelector('#seedCheck');
  copyBtn = root.querySelector('#copyBtn');

  root.querySelector('.seed-wrap')?.addEventListener('click', onClick);
  refresh();
}

function onClick(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  if (action === 'seed:new') refresh();
  if (action === 'seed:copy') copy();
}

async function refresh() {
  if (!crypto?.subtle) {
    grid.innerHTML = '';
    if (checkEl) {
      checkEl.textContent = 'Unavailable — this page must be served over HTTPS';
      checkEl.style.color = 'var(--accent)';
    }
    return;
  }

  current = await generateMnemonic();

  const frag = document.createDocumentFragment();
  current.forEach((word, i) => {
    const el = document.createElement('div');
    el.className = 'seed-word';
    el.innerHTML = '<span class="sw-num"></span><span class="sw-text"></span>';
    el.querySelector('.sw-num').textContent = String(i + 1).padStart(2, '0');
    el.querySelector('.sw-text').textContent = word;
    frag.appendChild(el);
  });
  grid.replaceChildren(frag);

  const ok = await verifyMnemonic(current);
  if (checkEl) {
    checkEl.textContent = ok
      ? '● Valid BIP-39 checksum · 128-bit entropy'
      : '● Checksum verification failed — do not use this phrase';
    checkEl.style.color = ok ? 'var(--green)' : 'var(--accent)';
  }
}

async function copy() {
  if (!current.length) return;
  const label = copyBtn?.querySelector('span');
  try {
    await navigator.clipboard.writeText(current.join(' '));
    if (label) {
      label.textContent = 'Copied';
      setTimeout(() => { label.textContent = 'Copy to clipboard'; }, 2000);
    }
  } catch {
    if (label) {
      label.textContent = 'Copy failed — select manually';
      setTimeout(() => { label.textContent = 'Copy to clipboard'; }, 2600);
    }
  }
}
