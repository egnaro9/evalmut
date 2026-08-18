// Invocation evidence for the Corpus B path.
//
// evalmut's sentinel is Python and cannot see a TypeScript function running in a subprocess, so
// the witness is produced HERE and REQUIRED on the Python side. What it prevents: a row carrying a
// verdict with no proof the upstream scorer ran. Such a row is indistinguishable from one where
// the harness answered for itself, and "checked and clean" versus "never checked" is the confusion
// this project keeps paying for.
//
// vi.spyOn calls through by default and records every return in mock.results, so the raw upstream
// value is captured without reimplementing the call. Nothing here changes what the scorer does.
import { vi } from 'vitest';

export function witness<T extends object, K extends keyof T>(obj: T, method: K) {
  const spy = vi.spyOn(obj as any, method as any);
  return {
    calls: () => spy.mock.calls.length,
    async evidence(target: string) {
      const raw: unknown[] = [];
      for (const r of spy.mock.results) {
        if (r.type !== 'return') { raw.push({ threw: String(r.value).slice(0, 120) }); continue; }
        const v: any = r.value;
        raw.push(v && typeof v.then === 'function' ? await v : v);
      }
      return {
        target,
        invoked: spy.mock.calls.length > 0,
        calls: spy.mock.calls.length,
        raw_upstream: raw,
      };
    },
    restore: () => spy.mockRestore(),
  };
}
