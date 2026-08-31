/* Plain words for each turn phase. "Thinking" and "Writing" are separate on
   purpose: waiting on a slow provider and receiving a slow reply look identical
   under one spinner, and telling them apart is most of what a status is for
   (CRS §5.1.1). */

import type { TurnStatus } from './events';

export const STATUS_COPY: Record<TurnStatus, string> = {
  queued: 'Queued',
  building_context: 'Gathering context',
  thinking: 'Thinking',
  streaming: 'Writing',
  tool_running: 'Running a tool',
  awaiting_input: 'Waiting for you',
  completed: 'Done',
  failed: 'Failed',
  cancelled: 'Stopped',
};
