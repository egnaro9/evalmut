import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import * as broken from './broken_scorer';
import { witness } from './witness';

describe('Corpus B negative control', () => {
  it('runs the broken scorer through the same witnessed path', async () => {
    const w = witness(broken, 'alwaysPasses');
    const clean = broken.alwaysPasses('<root><a>1</a></root>');
    const defective = broken.alwaysPasses('<root><a>1</b></root>');
    const ev = await w.evidence('test/cbprobe/broken_scorer.ts:alwaysPasses');
    fs.writeFileSync(process.env.CB_OUT || '/tmp/negctl.json', JSON.stringify({
      card_id: 'NEG-CONTROL-1',
      negative_control: true,
      verdicts: { clean, defective },
      witness: ev,
    }, null, 2));
    expect(ev.invoked).toBe(true);
  });
});
