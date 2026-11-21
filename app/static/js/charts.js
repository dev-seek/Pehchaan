// The names of the benchmark systems, shared by the Playground and the Benchmark Lab.
export const systemInfo = id => ({
  B0_asr_plain: 'sys_plain', B1_asr_keywords_C3: 'sys_keywords', B1_asr_keywords_C4: 'sys_keywords',
  B2_naive_llm_C3: 'sys_rewrite', B2_naive_llm_C4: 'sys_rewrite',
  P_on_B1_C3: 'sys_pehchaan', P_on_B1_C4: 'sys_pehchaan',
  P_C0: 'sys_pehchaan_plain', P_C2: 'sys_pehchaan_plain', P_C3: 'sys_pehchaan_plain', P_C4: 'sys_pehchaan_plain',
})[id];

export const systemNames = new Map([
  ['B0_asr_plain', ['Plain speech-to-text', 'No context']],
  ['B1_asr_keywords_C3', ['Keyword-assisted speech-to-text', 'Normal context (C3)']],
  ['B1_asr_keywords_C4', ['Keyword-assisted speech-to-text', 'Misleading hints (C4)']],
  ['B2_naive_llm_C3', ['Generative rewrite', 'Normal context (C3)']],
  ['B2_naive_llm_C4', ['Generative rewrite', 'Misleading hints (C4)']],
  ['P_on_B1_C3', ['Pehchaan', 'Normal context (C3)']],
  ['P_on_B1_C4', ['Pehchaan', 'Misleading hints (C4)']],
  ['P_C0', ['Pehchaan on a plain transcript', 'Rules only (C0)']],
  ['P_C2', ['Pehchaan on a plain transcript', 'Built-in lists (C2)']],
  ['P_C3', ['Pehchaan on a plain transcript', 'Normal context (C3)']],
  ['P_C4', ['Pehchaan on a plain transcript', 'Misleading hints (C4)']],
]);
export const systemTitle = id => (systemNames.get(id) || [id]).join(' · ');
