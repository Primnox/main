/* CRS §1.1 identifiers: "<prefix>_<uuidv7>". Generated client-side so that a
   turn, its message, and its events all have stable ids the moment they are
   created — which lets AAD bind each ciphertext to its exact envelope
   (CRS/1.0-W §5) and lets optimistic UI reconcile by id rather than by guess. */

import { uuidv7 } from 'uuidv7';

export type IdPrefix = 'conv' | 'fld' | 'turn' | 'msg' | 'evt' | 'job' | 'ws' | 'asset' | 'mem' | 'cu';

export function newId(prefix: IdPrefix): string {
  return `${prefix}_${uuidv7()}`;
}

const ID_RE = /^[a-z]{2,5}_[0-9a-f-]{10,}$/i;
export const looksLikeId = (s: string): boolean => ID_RE.test(s);
