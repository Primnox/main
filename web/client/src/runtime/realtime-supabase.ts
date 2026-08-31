/* Supabase Realtime implementation of RealtimeSource (resolved Q8).

   Subscribes to INSERTs on the `events` table. RLS scopes the stream to the
   authenticated user's rows, so no client-side filter is needed. The only file
   besides auth/supabase.ts that touches supabase-js. */

import type { RealtimeChannel } from '@supabase/supabase-js';
import { supabase } from '../auth/supabase';
import type { EventRow } from './eventcodec';
import type { RealtimeSource } from './realtime';

export class SupabaseRealtimeSource implements RealtimeSource {
  private channel: RealtimeChannel | null = null;

  onInsert(cb: (row: EventRow) => void): () => void {
    const sb = supabase();
    this.channel = sb
      .channel('primnox-events')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'events' },
        (payload) => cb(payload.new as EventRow),
      )
      .subscribe();

    return () => {
      if (this.channel) {
        void sb.removeChannel(this.channel);
        this.channel = null;
      }
    };
  }
}
