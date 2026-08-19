import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup, screen } from '@testing-library/react';
import { Select, Slider, Field } from './primitives';

/**
 * Two properties, both of which regressed silently once already.
 *
 * A <select> has no placeholder to fall back on, so before `label` existed
 * every dropdown in Settings, About and the chat model picker reached a screen
 * reader as an unnamed combobox — eight of them. The same held for the range
 * inputs. `label` is a required prop on both so the compiler, not a review,
 * catches the next one.
 *
 * The slider's thumb styling also used to be an inline <style> block keyed on
 * useId(), which put an identical copy in the DOM per mounted slider. It is a
 * static `.px-slider` rule now, so no slider should render a <style> at all.
 */

afterEach(cleanup);

const options = [
  { value: 's3', label: 'S3-compatible' },
  { value: 'gdrive', label: 'Google Drive' },
];

describe('Select', () => {
  it('exposes its label as the accessible name', () => {
    render(<Select label="Storage provider" value="s3" onChange={() => {}} options={options} />);
    expect(screen.getByRole('combobox', { name: 'Storage provider' })).toBeDefined();
  });
});

describe('Slider', () => {
  it('exposes its label as the accessible name', () => {
    render(<Slider label="Backup every" value={24} onChange={() => {}} min={1} max={168} />);
    expect(screen.getByRole('slider', { name: 'Backup every' })).toBeDefined();
  });

  it('announces the formatted value, not the bare number', () => {
    render(
      <Slider label="Backup every" value={24} onChange={() => {}} min={1} max={168}
        format={(v) => `${v}h`} />
    );
    expect(screen.getByRole('slider').getAttribute('aria-valuetext')).toBe('24h');
  });

  it('leaves aria-valuetext off when there is no format function', () => {
    render(<Slider label="VAD sensitivity" value={50} onChange={() => {}} />);
    expect(screen.getByRole('slider').hasAttribute('aria-valuetext')).toBe(false);
  });

  it('styles the thumb from a stylesheet rule, not a per-instance <style> tag', () => {
    const { container } = render(
      <>
        <Slider label="One" value={1} onChange={() => {}} />
        <Slider label="Two" value={2} onChange={() => {}} />
      </>
    );
    expect(container.querySelectorAll('style')).toHaveLength(0);
    for (const el of container.querySelectorAll('input[type=range]')) {
      expect(el.classList.contains('px-slider')).toBe(true);
    }
  });

  it('still paints the track fill inline, since it varies with the value', () => {
    render(<Slider label="Half" value={50} onChange={() => {}} min={0} max={100} />);
    expect(screen.getByRole('slider').getAttribute('style')).toContain('50%');
  });
});

describe('Field', () => {
  it('falls back to the placeholder for its name when no label is given', () => {
    render(<Field value="" onChange={() => {}} placeholder="hey primnox" />);
    expect(screen.getByPlaceholderText('hey primnox').hasAttribute('aria-label')).toBe(false);
  });

  it('prefers an explicit label over the placeholder', () => {
    render(<Field value="" onChange={() => {}} placeholder="Work" label="Display name" />);
    expect(screen.getByRole('textbox', { name: 'Display name' })).toBeDefined();
  });
});
