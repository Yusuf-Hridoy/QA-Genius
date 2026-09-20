import { describe, expect, it, vi } from 'vitest';
import { mask } from '@/lib/utils/mask';
import { newId, newRequestId } from '@/lib/utils/id';
import { cn } from '@/lib/utils/cn';
import { log } from '@/lib/utils/log';

describe('mask', () => {
  it('masks long keys as first4…last4', () => {
    expect(mask('abcdefghijklmnopqrstuvwxyz')).toBe('abcd…wxyz');
    expect(mask('1234567890')).toBe('1234…7890');
  });

  it('masks short keys fully', () => {
    expect(mask('12345678')).toBe('••••');
    expect(mask('abc')).toBe('••••');
    expect(mask('')).toBe('••••');
  });
});

describe('ids', () => {
  it('generates unique non-empty ids', () => {
    expect(newId()).toHaveLength(12);
    expect(newRequestId()).toHaveLength(16);
    expect(new Set([newId(), newId(), newId()]).size).toBe(3);
  });
});

describe('cn', () => {
  it('joins truthy class names', () => {
    expect(cn('a', false && 'b', 'c')).toBe('a c');
  });
});

describe('log', () => {
  it('prefixes messages and logs error names only', () => {
    const info = vi.spyOn(console, 'info').mockImplementation(() => {});
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    log.info('hello');
    expect(info).toHaveBeenCalledWith('[qag] hello');
    log.error('generate failed', new TypeError('boom'));
    expect(error).toHaveBeenCalledWith('[qag] generate failed (TypeError)');
    info.mockRestore();
    error.mockRestore();
  });
});
