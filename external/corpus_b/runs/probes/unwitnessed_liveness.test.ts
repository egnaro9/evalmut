import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import * as xml from '../../src/assertions/xml';
import { witness } from './witness';

// The liveness case: a probe that produces a verdict WITHOUT calling the upstream scorer. This is
// the harness answering for itself, and the witness must report zero calls rather than staying
// silent. A witness never seen reporting absence is indistinguishable from one that cannot.
describe('unwitnessed path', () => {
  it('reports zero invocations when the scorer is bypassed', async () => {
    const w = witness(xml, 'validateXml');
    const fabricated = { isValid: true, reason: 'the harness decided this itself' };
    const ev = await w.evidence('src/assertions/xml.ts:validateXml');
    fs.writeFileSync(process.env.CB_OUT || '/tmp/w2.json',
      JSON.stringify({ verdicts: { clean: fabricated, defective: fabricated }, witness: ev },
        null, 2));
    expect(ev.calls).toBe(0);
  });
});
