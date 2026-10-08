import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const read = locale => JSON.parse(readFileSync(new URL(`../src/locales/${locale}.json`, import.meta.url)));
const en = read('en');
const tokens = text => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();
for (const locale of ['ru', 'es', 'pt-BR', 'zh-CN', 'fr', 'it', 'de', 'ja', 'ko', 'ar', 'hi']) {
  test(`${locale}: all translation keys and placeholders match English`, () => {
    const catalog = read(locale);
    assert.deepEqual(Object.keys(catalog).sort(), Object.keys(en).sort());
    for (const key of Object.keys(en)) {
      assert.ok(catalog[key].trim(), `Empty translation: ${key}`);
      assert.deepEqual(tokens(catalog[key]), tokens(en[key]), key);
    }
  });
}
test('standard report statements in the fixture have translations or parameterized handlers', () => {
  const { report } = JSON.parse(readFileSync(new URL('./fixtures/ui.json', import.meta.url))).investigation;
  const parameterized = [/^Check system deviations for state \d+\.$/, /^One read, up to \d+ historical states;/, /^(cpu_percent|memory_percent|swap_percent) is (above|below) the historical/, /^Observed (cpu_percent|memory_percent|swap_percent) >=/, /^Relative deviation does not meet the (cpu_percent|memory_percent|swap_percent) >=/];
  const strings = [report.conclusion, ...report.limitations, ...report.findings.map(x => x.statement), ...report.trace.flatMap(x => [x.stage, x.detail]), ...report.reasoning.hypotheses.map(x => x.statement), ...report.reasoning.verdicts.flatMap(x => [x.status, x.reason])];
  for (const text of strings) assert.ok(Object.hasOwn(en, text) || parameterized.some(regex => regex.test(text)), text);
});
