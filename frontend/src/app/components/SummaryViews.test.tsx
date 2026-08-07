import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import { SummariesExpanded } from './SummaryViews';

/**
 * Regression guard for the dashboard polling loop.
 *
 * The initial fetch used to live in the same effect as the backoff interval,
 * with `dashFailCount` in its dependency array. A failed fetch incremented that
 * count, which re-ran the effect, which fetched again immediately — and a fetch
 * against an unreachable backend rejects in microseconds. Measured against the
 * real build, that spun at ~500 requests/second (5036 hits on /api/dashboard in
 * 10 seconds) for as long as the dashboard was open, and the backoff interval
 * never fired at all because it was torn down before its first tick.
 */

const dashboardCalls = () =>
  (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) =>
    String(url).includes('/api/dashboard'),
  ).length;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  // Reject like a refused connection: immediately, with no network delay.
  globalThis.fetch = vi.fn(() => Promise.reject(new Error('ECONNREFUSED'))) as never;
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('SummariesExpanded dashboard polling', () => {
  it('fetches once on mount when the backend is unreachable', async () => {
    render(<SummariesExpanded onNavigate={() => {}} />);

    // Let the rejection settle and any resulting re-renders flush.
    await waitFor(() => expect(dashboardCalls()).toBeGreaterThan(0));
    await vi.advanceTimersByTimeAsync(50);

    expect(dashboardCalls()).toBe(1);
  });

  it('does not re-fetch when a failure updates the backoff state', async () => {
    render(<SummariesExpanded onNavigate={() => {}} />);
    await waitFor(() => expect(dashboardCalls()).toBeGreaterThan(0));

    // Well beyond the microsecond turnaround of the old hot loop, but short of
    // the 30s minimum poll interval — so a correct implementation is idle here.
    await vi.advanceTimersByTimeAsync(5_000);

    expect(dashboardCalls()).toBe(1);
  });

  it('waits a full backoff step before polling again', async () => {
    render(<SummariesExpanded onNavigate={() => {}} />);
    await waitFor(() => expect(dashboardCalls()).toBeGreaterThan(0));

    // The mount fetch has already failed, so the failure count is 1 and the
    // interval is armed at 30s * 2^1 = 60s — not the 30s healthy floor. The
    // bounds are deliberately loose: what matters is that nothing polls in the
    // first 30 seconds and that polling does resume, not the exact tick.
    await vi.advanceTimersByTimeAsync(30_000);
    expect(dashboardCalls()).toBe(1);

    await vi.advanceTimersByTimeAsync(60_000);
    expect(dashboardCalls()).toBe(2);
  });

  it('backs off rather than polling at a fixed rate while failing', async () => {
    render(<SummariesExpanded onNavigate={() => {}} />);
    await waitFor(() => expect(dashboardCalls()).toBeGreaterThan(0));

    // Five minutes of a downed backend. At the 30s floor that would be ~10
    // polls; with backoff to 120s it must be far fewer. The old loop managed
    // roughly 150,000.
    await vi.advanceTimersByTimeAsync(300_000);

    const calls = dashboardCalls();
    expect(calls).toBeGreaterThan(1);
    expect(calls).toBeLessThanOrEqual(6);
  });

  it('stops polling once unmounted', async () => {
    const view = render(<SummariesExpanded onNavigate={() => {}} />);
    await waitFor(() => expect(dashboardCalls()).toBeGreaterThan(0));

    view.unmount();
    const afterUnmount = dashboardCalls();

    await vi.advanceTimersByTimeAsync(300_000);
    expect(dashboardCalls()).toBe(afterUnmount);
  });
});
