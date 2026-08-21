import { fireEvent, render, screen } from '@solidjs/testing-library';
import { For } from 'solid-js';
import { describe, expect, it, vi } from 'vitest';
import { Button, Pagination, SegmentedControl, Select } from '.';

describe('base UI components', () => {
  it('handles button disabled and click states', async () => {
    const click = vi.fn();
    const view = render(() => <Button onClick={click}>保存</Button>);
    await fireEvent.click(screen.getByRole('button', { name: '保存' }));
    expect(click).toHaveBeenCalledOnce();
    view.unmount();
    render(() => <Button disabled>保存</Button>);
    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled();
  });

  it('changes segmented values and pagination', async () => {
    const change = vi.fn();
    render(() => <SegmentedControl value="a" options={[{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }]} onChange={change} />);
    await fireEvent.click(screen.getByRole('button', { name: 'B' }));
    expect(change).toHaveBeenCalledWith('b');
    const page = vi.fn();
    render(() => <Pagination page={2} totalPages={3} onChange={page} />);
    await fireEvent.click(screen.getByRole('button', { name: /下一页/ }));
    expect(page).toHaveBeenCalledWith(3);
  });

  it('Select applies non-first value rendered with <For> options (issue #243)', () => {
    const view = render(() => (
      <Select label="策略" value="smart">
        <For each={[{ value: 'replace', label: 'R' }, { value: 'smart', label: 'S' }]}>
          {(option) => <option value={option.value}>{option.label}</option>}
        </For>
      </Select>
    ));
    expect(document.querySelector('select')!.value).toBe('smart');
    view.unmount();
  });
});
