

// Plain words for each state. "Thinking" and "Writing" are separate on purpose:
// waiting on a slow provider and receiving a slow reply look identical under a
// single spinner, and telling them apart is most of what a status is for.
export const STATUS_COPY: Record<string, string> = {
  queued: 'Queued',
  building_context: 'Gathering context',
  thinking: 'Thinking',
  streaming: 'Writing',
  tool_running: 'Running a tool',
  awaiting_input: 'Waiting for you',
};

