import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup, screen, fireEvent } from '@testing-library/react';
import { SkillActivity } from './SkillActivity';

/**
 * The activity panel replaced a bare spinner that sat there for 30s+ while
 * a multi-step skill ran. Two properties matter beyond "it renders":
 * commands stay behind a toggle so the default view reads as progress
 * rather than a debug log, and the panel never invents a completion state
 * while a step is still running.
 */

afterEach(cleanup);

const running = [
  { skill: 'pptx', phase: 'loaded the pptx skill', status: 'done' as const, total: 6 },
  { skill: 'pptx', phase: 'building the slide master', status: 'running' as const, step: 2, total: 6, command: 'node · build.js' },
];

const finished = [
  { skill: 'pptx', phase: 'loaded the pptx skill', status: 'done' as const, total: 6 },
  { skill: 'pptx', phase: 'building the slide master', status: 'done' as const, step: 1, total: 6, command: 'node · build.js', detail: 'wrote q3.pptx' },
];

describe('SkillActivity', () => {
  it('renders nothing when there are no phases', () => {
    const { container } = render(<SkillActivity phases={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows working state and the step counter while a phase is running', () => {
    render(<SkillActivity phases={running} />);
    expect(screen.getByText('working')).toBeTruthy();
    expect(screen.getByText('step 2 of 6')).toBeTruthy();
  });

  it('shows every phase label so progress is legible at a glance', () => {
    render(<SkillActivity phases={running} />);
    expect(screen.getByText('loaded the pptx skill')).toBeTruthy();
    expect(screen.getByText('building the slide master')).toBeTruthy();
  });

  it('reports completion only once nothing is running', () => {
    render(<SkillActivity phases={finished} />);
    expect(screen.getByText('completed')).toBeTruthy();
    expect(screen.queryByText('working')).toBeNull();
  });

  it('surfaces a failed step instead of claiming success', () => {
    render(<SkillActivity phases={[{ phase: 'running node', status: 'failed', step: 1, total: 6 }]} />);
    expect(screen.getByText('finished with errors')).toBeTruthy();
  });

  it('keeps commands hidden until the activity log is opened', () => {
    render(<SkillActivity phases={finished} />);
    expect(screen.queryByText(/build\.js/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'activity' }));
    expect(screen.getByText(/build\.js/)).toBeTruthy();
  });

  it('does not offer the activity log while a step is still running', () => {
    // The sandbox footer and log toggle appear on completion — mid-run the
    // panel stays focused on what's happening now.
    render(<SkillActivity phases={running} />);
    expect(screen.queryByRole('button', { name: 'activity' })).toBeNull();
  });

  it('collapses to a single summary row', () => {
    render(<SkillActivity phases={finished} />);
    expect(screen.getByText('loaded the pptx skill')).toBeTruthy();

    fireEvent.click(screen.getByText('completed'));
    expect(screen.queryByText('loaded the pptx skill')).toBeNull();
    expect(screen.getByText('completed')).toBeTruthy();
  });
});
