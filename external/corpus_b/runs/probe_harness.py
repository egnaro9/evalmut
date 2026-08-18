"""Execute the frozen Corpus B cards against promptfoo's OWN code.

Each card runs twice: at the PARENT of its fix (defect present) and at the fix commit (defect
repaired). The second run is not decoration. A probe that returns the same thing on both sides is
not measuring the defect, and reporting the first result alone would be an instrument nobody
proved. That control is what separates "the defect reproduced" from "the probe ran".
"""
from __future__ import annotations

import json
import pathlib
import subprocess

WT = pathlib.Path(__file__).resolve().parent / "pfwt"
OUT = pathlib.Path(__file__).resolve().parent / "cb_raw.json"

PROBES = {
    "CB-001": ("96929e8758ca", "src/assertions/xml.ts", r"""
import { validateXml } from './src/assertions/xml';
const r = (s: string) => { try { return validateXml(s); } catch (e: any) { return {threw: String(e && e.message)}; } };
console.log(JSON.stringify({
  clean: r('<root><a>1</a></root>'),
  defective: r('<root><a>1</b></root>'),
  counterexample_legal: r('<root><![CDATA[x < y]]></root>'),
}));
"""),
    "CB-002": ("c08cfc454d38", "src/assertions/sql.ts", r"""
import { handleIsSql } from './src/assertions/sql';
const call = async (out: string) => { try {
  const r: any = await handleIsSql({ assertion: { type: 'is-sql' }, outputString: out,
    inverse: false, renderedValue: undefined, baseType: 'is-sql', output: out } as any);
  return { pass: r.pass, score: r.score, reason: r.reason };
} catch (e: any) { return { threw: String(e && (e.message || e)) }; } };
(async () => { console.log(JSON.stringify({
  clean: await call('SELECT name FROM users'),
  defective: await call('SELECT DISTINCT name FROM users'),
  counterexample_ambiguous: await call('SELECT a b FROM t'),
})); })();
"""),
    "CB-003": ("386c0129bf50", "src/assertions/rouge.ts", r"""
import { handleRougeScore } from './src/assertions/rouge';
const call = (out: string, ref: string) => { try {
  return handleRougeScore({ assertion: { type: 'rouge-n', threshold: 0.9 }, baseType: 'rouge-n',
    renderedValue: ref, outputString: out, inverse: false, output: out,
    providerResponse: {} as any, test: {} as any, context: {} as any } as any);
} catch (e: any) { return { threw: String(e && e.message) }; } };
console.log(JSON.stringify({
  clean: call('the cat sat on the mat', 'the cat sat on the mat'),
  defective: call('The Cat Sat On The Mat', 'the cat sat on the mat'),
}));
"""),
    "CB-004": ("560ea2d236e7", "src/assertions/levenshtein.ts", r"""
import { handleLevenshtein } from './src/assertions/levenshtein';
const call = (inverse: boolean) => { try {
  return handleLevenshtein({ assertion: { type: inverse ? 'not-levenshtein' : 'levenshtein', threshold: 3 },
    renderedValue: 'hello world', outputString: 'hello world', inverse, baseType: 'levenshtein',
    output: 'hello world', providerResponse: {} as any, test: {} as any, context: {} as any } as any);
} catch (e: any) { return { threw: String(e && e.message) }; } };
console.log(JSON.stringify({ clean: call(false), defective: call(true) }));
"""),
    "CB-005": ("49c0f6d77496", "src/assertions/traceSpanDuration.ts", r"""
import { handleTraceSpanDuration } from './src/assertions/traceSpanDuration';
const spans = [ { spanId:'1', name:'a', startTime:0, endTime:10 }, { spanId:'2', name:'b', startTime:0, endTime:20 },
  { spanId:'3', name:'c', startTime:0, endTime:5000 } ];
const call = (percentile: number) => { try {
  return handleTraceSpanDuration({ assertion: { type: 'trace-span-duration', value: { max: 100, percentile } },
    renderedValue: { max: 100, percentile },
    assertionValueContext: { trace: { spans } } as any,
    outputString: '', inverse: false, baseType: 'trace-span-duration', output: '' } as any);
} catch (e: any) { return { threw: String(e && e.message) }; } };
console.log(JSON.stringify({ clean: call(95), defective: call(150), counterexample_boundary: call(100) }));
"""),
    "CB-007": ("cc8c0c65f137", "src/assertions/gleu.ts", r"""
import { calculateGleuScore } from './src/assertions/gleu';
const call = (c: string, r: string) => { try { return { score: calculateGleuScore(c, [r]) }; }
  catch (e: any) { return { threw: String(e && e.message) }; } };
console.log(JSON.stringify({
  clean: call('the cat sat', 'the cat sat'),
  defective: call('   ', '...'),
  empty_output: call('', 'the cat sat'),
}));
"""),
    "CB-009": ("ffd892292644", "src/assertions/openai.ts", r"""
import { handleIsValidOpenAiToolsCall } from './src/assertions/openai';
const provider: any = { config: { tools: [ { type: 'function',
  function: { name: 'f', parameters: { type: 'object', properties: {}, required: [] } } } ] } };
const call = async (output: any) => { try {
  const r: any = await handleIsValidOpenAiToolsCall({ assertion: { type: 'is-valid-openai-tools-call' },
    output, outputString: JSON.stringify(output), inverse: false,
    baseType: 'is-valid-openai-tools-call', renderedValue: undefined, provider,
    test: { vars: {} } as any } as any);
  return { pass: r.pass, score: r.score, reason: String(r.reason).slice(0, 120) };
} catch (e: any) { return { threw: String(e && (e.message || e)).slice(0, 160) }; } };
(async () => { console.log(JSON.stringify({
  clean: await call([{ function: { name: 'f', arguments: '{}' } }]),
  defective: await call([{ id: 'call_1' }]),
})); })();
"""),
}

# CB-006's handler did not exist as a standalone assertion file at its parent commit; the fix
# touched src/external/assertions/deepeval.ts. Recorded rather than guessed at.
UNPROBED = {
    "CB-006": ("2812d7622b2e", "src/external/assertions/deepeval.ts",
               "handler is not a standalone assertion module at the parent commit; the default "
               "threshold lives in src/external/assertions/deepeval.ts behind a matcher that "
               "requires a provider. Not probed in this pass rather than probed with a "
               "substitute, which would measure the substitute.")
}


def git(*args) -> str:
    return subprocess.run(["git", "-C", str(WT), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def run_probe(ref: str, src: str) -> dict:
    git("checkout", "--detach", "-f", ref)
    p = WT / "cb_probe.ts"
    p.write_text(src)
    try:
        r = subprocess.run(["./node_modules/.bin/tsx", "cb_probe.ts"], cwd=str(WT),
                           capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            return {"_error": (r.stderr or r.stdout).strip().splitlines()[-6:]}
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}
    finally:
        p.unlink(missing_ok=True)


def main():
    results = {}
    for cid, (fix, path, src) in PROBES.items():
        print(f"{cid}: at parent of {fix[:8]} ...", flush=True)
        pre = run_probe(f"{fix}^", src)
        print(f"{cid}: at fix {fix[:8]} ...", flush=True)
        post = run_probe(fix, src)
        results[cid] = {"fix_commit": fix, "module": path, "pre_fix": pre, "post_fix": post}
    for cid, (fix, path, why) in UNPROBED.items():
        results[cid] = {"fix_commit": fix, "module": path, "not_probed": why}
    OUT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
