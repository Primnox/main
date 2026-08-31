import { describe, expect, it } from 'vitest';
import { buildBundle } from './bundle';

describe('buildBundle', () => {
  it('passes small inputs through untouched', () => {
    const b = buildBundle({
      systemPrompt: 'You are Primnox.',
      history: [
        { role: 'user', text: 'hello' },
        { role: 'assistant', text: 'hi' },
      ],
      userText: 'what is 2+2?',
    });
    expect(b.droppedTurns).toBe(0);
    expect(b.system).toBe('You are Primnox.');
    expect(b.messages).toEqual([
      { role: 'user', content: 'hello' },
      { role: 'assistant', content: 'hi' },
      { role: 'user', content: 'what is 2+2?' },
    ]);
  });

  it('folds memory, assets and workspace files into the system block', () => {
    const b = buildBundle({
      systemPrompt: 'base',
      history: [],
      memory: [{ text: 'user prefers metric units' }],
      assets: [{ name: 'notes.txt', text: 'the meeting is friday' }],
      workspaceFiles: [{ path: 'main.py', content: 'print(1)' }],
      userText: 'go',
    });
    expect(b.system).toContain('## Relevant memory');
    expect(b.system).toContain('- user prefers metric units');
    expect(b.system).toContain('### notes.txt');
    expect(b.system).toContain('```main.py');
  });

  it('trims oldest history to fit the budget, keeping the floor and the new message', () => {
    const history = Array.from({ length: 20 }, (_, i) => ({
      role: (i % 2 === 0 ? 'user' : 'assistant') as 'user' | 'assistant',
      text: 'x'.repeat(400), // ~100 tokens each
    }));
    const b = buildBundle({
      systemPrompt: 'base',
      history,
      userText: 'latest',
      budgetTokens: 300, // only a few turns fit
    });
    expect(b.droppedTurns).toBeGreaterThan(0);
    expect(b.messages.length).toBeLessThan(history.length + 1);
    expect(b.messages.at(-1)).toEqual({ role: 'user', content: 'latest' });
    expect(b.messages.length).toBeGreaterThanOrEqual(3); // KEEP_MIN_TURNS + new
  });
});
