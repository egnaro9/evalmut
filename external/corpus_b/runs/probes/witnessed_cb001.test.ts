import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import * as xml from '../../src/assertions/xml';
import { witness } from './witness';

describe('witnessed CB-001', () => {
  it('records invocation beside the verdict', async () => {
    const w = witness(xml, 'validateXml');
    const clean = xml.validateXml('<root><a>1</a></root>');
    const defective = xml.validateXml('<root><a>1</b></root>');
    const ev = await w.evidence('src/assertions/xml.ts:validateXml');
    fs.writeFileSync(process.env.CB_OUT || '/tmp/w.json',
      JSON.stringify({ verdicts: { clean, defective }, witness: ev }, null, 2));
    expect(ev.invoked).toBe(true);
  });
});
