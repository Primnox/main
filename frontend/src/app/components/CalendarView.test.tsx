import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor, screen, fireEvent } from '@testing-library/react';
import { CalendarView } from './CalendarView';

/**
 * Regression guard for the Tasks priority vocabulary mismatch.
 *
 * The backend's task priority is 'low' | 'normal' | 'urgent' everywhere
 * (notes_manager.add_task's default, tools.py's add_task tool schema, and
 * the `t.priority === 'urgent'` checks SummaryViews.tsx uses to flag a task
 * red / surface it in the "Urgent —" focus banner). CalendarView's own
 * inline "add task" form used to default to and only offer
 * 'low' | 'medium' | 'high' instead — neither 'medium' nor 'high' is a value
 * anything else in the app ever checks for, so a task created here as "high
 * priority" would silently never be flagged urgent anywhere.
 */

function jsonResponse(body: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  } as Response);
}

beforeEach(() => {
  globalThis.fetch = vi.fn((url: string) => {
    const u = String(url);
    if (u.includes('/api/events')) return jsonResponse({ events: [] });
    if (u.includes('/tasks')) return jsonResponse([]);
    return jsonResponse({});
  }) as never;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('CalendarView add-task priority', () => {
  it('offers low/normal/urgent, not low/medium/high', async () => {
    render(<CalendarView onNavigate={() => {}} />);

    await waitFor(() => expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole('button', { name: /task/i }));

    expect(screen.getByRole('button', { name: 'urgent' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'normal' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'low' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'medium' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'high' })).toBeNull();
  });

  it('submits a new task with priority "normal" by default, not "medium"', async () => {
    render(<CalendarView onNavigate={() => {}} />);

    await waitFor(() => expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole('button', { name: /task/i }));
    fireEvent.change(screen.getByPlaceholderText('Task title...'), { target: { value: 'Ship the release' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => {
      const postCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        (call: any[]) => String(call[0]).includes('/tasks') && call[1]?.method === 'POST',
      );
      expect(postCall).toBeTruthy();
      const body = JSON.parse((postCall![1] as RequestInit).body as string);
      expect(body.priority).toBe('normal');
    });
  });
});
