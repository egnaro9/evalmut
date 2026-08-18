// A deliberately broken scorer, present in the sealed inventory and expected to FAIL the
// clean/defective discrimination contract.
//
// This answers a different question from the witness. The witness proves a scorer EXECUTED. This
// proves the end-to-end harness can still expose a scorer that should fail. A harness that reports
// a comfortable result on a check which cannot fail is worse than no harness, because it launders
// the defect it was bought to find.
//
// Its brokenness is not subtle on purpose: it returns a pass for every input it is shown. A
// subtle control would leave "did the harness miss it, or is the control too gentle" unanswerable.
export function alwaysPasses(_input: string): { isValid: boolean; reason: string } {
  return { isValid: true, reason: 'negative control: this scorer passes everything' };
}
