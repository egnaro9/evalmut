import fs from 'node:fs';
import { describe, expect, it, vi } from 'vitest';

// The matcher is the UPSTREAM scorer, not the code under test. Stubbing it fixes the score so the
// THRESHOLD logic can be observed in isolation. This is the same boundary promptfoo's own tests
// mock, and the raw upstream value is recorded below beside the verdict rather than inferred.
vi.mock('../../src/external/matchers/deepeval', () => ({
  matchesConversationRelevance: vi.fn(async () => ({
    pass: false, score: 0, reason: 'Response is not relevant to the conversation context',
  })),
}));

describe('CB-006', () => {
  it('records observations', async () => {
    const mod: any = await import('../../src/external/assertions/deepeval');
    const handler = mod.handleConversationRelevance ?? mod.handleConversationalRelevance;
    const base = {
      assertion: { type: 'conversation-relevance' },
      outputString: 'totally unrelated reply',
      renderedValue: 'what is the capital of France?',
      inverse: false, baseType: 'conversation-relevance',
      output: 'totally unrelated reply',
      test: { vars: {}, options: {} },
      prompt: 'what is the capital of France?',
      providerCallContext: {},
    };
    const call = async (assertion: any) => {
      try {
        const r: any = await handler({ ...base, assertion });
        return { pass: r.pass, score: r.score, raw_upstream_score: 0,
                 reason: String(r.reason).slice(0, 120) };
      } catch (e: any) { return { threw: String(e && (e.message || e)).slice(0, 160) }; }
    };
    const obs = {
      handler_found: typeof handler === 'function',
      default_threshold: await call({ type: 'conversation-relevance' }),
      explicit_zero: await call({ type: 'conversation-relevance', threshold: 0 }),
      explicit_half: await call({ type: 'conversation-relevance', threshold: 0.5 }),
    };
    fs.writeFileSync(process.env.CB_OUT || '/tmp/cb006.json', JSON.stringify(obs, null, 2));
    expect(obs).toBeTruthy();
  });
});
