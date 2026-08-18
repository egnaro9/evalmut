import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import { handleIsSql } from '../../src/assertions/sql';

const call = async (out: string) => {
  try {
    const r: any = await handleIsSql({ assertion: { type: 'is-sql' }, outputString: out,
      inverse: false, renderedValue: undefined, baseType: 'is-sql', output: out } as any);
    return { pass: r.pass, score: r.score, reason: String(r.reason).slice(0, 140) };
  } catch (e: any) { return { threw: String(e && (e.message || e)).slice(0, 160) }; }
};

describe('CB-002', () => {
  it('records observations', async () => {
    const obs = {
      clean: await call('SELECT name FROM users'),
      defective: await call('SELECT DISTINCT name FROM users'),
      counterexample_ambiguous: await call('SELECT a b FROM t'),
    };
    fs.writeFileSync(process.env.CB_OUT || '/tmp/cb002.json', JSON.stringify(obs, null, 2));
    expect(obs).toBeTruthy();
  });
});
