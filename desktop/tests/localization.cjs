const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const http = require('http');
const assert = require('node:assert/strict');
const fixtureText = fs.readFileSync(path.join(__dirname, 'fixtures/ui.json'), 'utf8');
const offset = Date.now() - Date.parse('2026-10-01T12:07:40Z');
const fixture = JSON.parse(fixtureText, (key, value) => typeof value === 'string' && /^2026-10-01T/.test(value) ? new Date(Date.parse(value) + offset).toISOString() : value);
const locales = ['en', 'ru', 'es', 'pt-BR', 'zh-CN', 'fr', 'it', 'de', 'ja', 'ko', 'ar', 'hi'];
const catalogs = Object.fromEntries(locales.map(locale => [locale, JSON.parse(fs.readFileSync(path.join(__dirname, `../src/locales/${locale}.json`)))]));

(async () => {
  const root = path.join(__dirname, '../dist');
  const server = http.createServer((req, res) => {
    const file = path.join(root, req.url === '/' ? 'index.html' : req.url);
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.woff2') ? 'font/woff2' : 'text/html');
    try { res.end(fs.readFileSync(file)); } catch { res.statusCode = 404; res.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE || undefined, args: ['--no-sandbox', '--disable-gpu'], headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, locale: 'en-US', colorScheme: 'dark' });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(fixture => {
    window.testState = { fixture, cleared: false, calls: [], failure: false, empty: sessionStorage.getItem('test-empty') === '1', generation: 'initial' };
    window.__TAURI_INTERNALS__ = { invoke: async (command, args) => {
      const s = window.testState;
      s.calls.push([command, args]);
      const storage = () => ({ ...fixture.overview.storage, state_count: s.cleared || s.empty ? 0 : 47, generation: s.generation });
      const overview = () => ({ ...fixture.overview, storage: storage() });
      if (command === 'set_locale') { s.locale = args.locale; return null; }
      if (command === 'monitor_status') return { ok: true, result: { overview: s.empty || s.cleared ? null : overview(), error: s.failure ? 'Test backend unavailable' : null } };
      if (command === 'startup_status' || command === 'set_startup_enabled') return { supported: true, enabled: args?.enabled ?? true, error: null };
      if (command === 'refresh_state') { if (s.failure) throw 'Test backend unavailable'; s.empty = false; return overview(); }
      if (command === 'backend_call') {
        const p = args.payload;
        if (p.action === 'investigate') return { ok: true, result: { ...fixture.investigation, question: p.question } };
        if (p.action === 'history_info' || p.action === 'open_history_folder') return { ok: true, result: storage() };
        if (p.action === 'history_page') return { ok: true, result: { ...fixture.page, rows: s.cleared ? [] : fixture.page.rows.slice(p.page * p.page_size, (p.page + 1) * p.page_size), page: p.page, page_size: p.page_size, generation: s.generation } };
        if (p.action === 'clear_history') { if (p.confirmed !== true) throw new Error('Confirmation missing'); s.cleared = true; s.generation = 'new'; return {ok: true, result: {deleted_count:47, storage:storage()}}; }
      }
      throw new Error(command);
    }};
  }, fixture);
  let checks = 0;
  const failures = [];
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByRole('button', { name: 'Check memory', exact: true }).click();
    await page.getByRole('button', { name: 'Investigate →', exact: true }).click();
    await page.getByText('Investigation result', { exact: true }).waitFor();
    for (const locale of locales) {
      const c = catalogs[locale];
      await page.locator('.language-control select').selectOption(locale);
      await page.evaluate(() => document.fonts.ready);
      await page.locator('nav button').nth(0).click();
      await page.getByRole('button', { name: c['Check memory'], exact: true }).click();
      await page.getByRole('button', { name: c['Investigate →'], exact: true }).click();
      await page.getByText(c['Investigation result'], { exact: true }).waitFor();
      assert.equal(await page.locator('html').getAttribute('lang'), locale);
      assert.equal(await page.locator('html').getAttribute('dir'), locale === 'ar' ? 'rtl' : 'ltr');
      assert.equal(await page.evaluate(() => localStorage.getItem('sherlock.locale')), locale);
      assert.equal(await page.evaluate(() => window.testState.locale), locale);
      // The report must preserve the submitted query, including leading ¿ and punctuation.
      const question = c['Is memory pressure high?'];
      await page.locator('nav button').nth(1).click();
      await page.getByRole('tab', {name:c.Summary, exact:true}).click();
      assert.equal(await page.getByRole('textbox', {name:c['Question used for this report'],exact:true}).inputValue(), question);
      const beforeFolder = await page.evaluate(() => window.testState.calls.filter(([command,args]) => command === 'backend_call' && args.payload.action === 'open_history_folder').length);
      await page.locator('footer').getByRole('button', {name:c['History location ↗'],exact:true}).click();
      assert.equal(await page.evaluate(() => window.testState.calls.filter(([command,args]) => command === 'backend_call' && args.payload.action === 'open_history_folder').length), beforeFolder + 1);
      checks += 2;
      for (const [width, height] of [[820, 680], [1024, 768], [1280, 800]]) {
        await page.setViewportSize({ width, height });
        for (const [index, name] of ['Overview', 'Investigation', 'History', 'Settings'].entries()) {
          await page.locator('nav button').nth(index).click();
          if (name === 'History') await page.locator('tbody tr').first().waitFor();
          const measure = async label => {
            const problems = await page.evaluate(() => {
              const results = [];
              for (const selector of ['.topbar', '.metrics', '.tabs', '.workspace', 'footer']) {
                const el = document.querySelector(selector), r = el.getBoundingClientRect();
                if (r.left < -1 || r.right > innerWidth + 1 || r.bottom > innerHeight + 1 || el.scrollWidth > el.clientWidth + 2) results.push(selector + ': outer overflow');
              }
              for (const el of document.querySelectorAll('.workspace button,.workspace h1,.workspace h2,.workspace p,.workspace input,.workspace select,.workspace table,.workspace .activity-row,.workspace .preferences')) {
                if (el.closest('.report-content')) continue; // Report text has an intentional bounded overflow fallback.
                const r = el.getBoundingClientRect();
                if (!r.width || !r.height) continue;
                const panel = el.closest('.panel');
                if (r.left < -1 || r.right > innerWidth + 1 || r.bottom > innerHeight - 30 || panel && r.bottom > panel.getBoundingClientRect().bottom + 1) results.push(el.textContent.slice(0, 50));
              }
              for (const metric of document.querySelectorAll('.metric')) {
                const label = metric.querySelector('span').getBoundingClientRect();
                const value = metric.querySelector('strong').getBoundingClientRect();
                const text = document.createRange(); text.selectNodeContents(metric.querySelector('span'));
                const r = text.getBoundingClientRect();
                if (r.left < label.left - 1 || r.right > label.right + 1 || (r.left < value.right && r.right > value.left && r.top < value.bottom && r.bottom > value.top)) results.push('metric label overlap: ' + metric.querySelector('span').textContent);
              }
              const grid = document.querySelector('.settings-grid'), prefs = document.querySelector('.preferences');
              if (grid && prefs && [...grid.querySelectorAll('p,small,label')].some(el => el.getBoundingClientRect().bottom > prefs.getBoundingClientRect().top + 1)) results.push('settings overlap');
              const table = document.querySelector('table'), pager = document.querySelector('.history-bottom');
              if (table && pager && table.getBoundingClientRect().bottom > pager.getBoundingClientRect().top) results.push('table overlaps pager');
              return results;
            });
            checks++;
            if (problems.length) failures.push({ locale, width, height, view: label, problems });
          };
          if (name === 'Investigation') {
            for (const section of ['Summary', 'Findings', 'Trace', 'Limits']) {
              await page.getByRole('tab', { name: c[section], exact: true }).click();
              await measure(section);
            }
          } else await measure(name);
          if ((width === 1280 || width === 820 && ['de','ar','hi'].includes(locale)) && (name === 'Overview' || name === 'Settings')) {
            const target = path.join(__dirname, '../../docs/assets', `${name.toLowerCase()}-v01-${locale}${width===820?'-compact':''}.png`);
            await page.evaluate(() => document.fonts.ready);
            await page.screenshot({ animations: 'disabled', path: target });
          }
        }
      }
      await page.locator('nav button').nth(3).click();
      await page.locator('.preferences select').selectOption('light');
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
      if (locale === 'ru') await page.screenshot({ animations: 'disabled', path: path.join(__dirname, '../../docs/assets/settings-v01-light-ru.png') });
      await page.locator('.preferences select').selectOption('dark');
      await page.reload();
      await page.locator('nav').waitFor();
      assert.equal(await page.locator('.language-control select').inputValue(), locale);
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      await page.getByRole('button', { name: c['Check memory'], exact: true }).click();
      await page.getByRole('button', { name: c['Investigate →'], exact: true }).click();
      await page.getByText(c['Investigation result'], { exact: true }).waitFor();
      const conclusion = fixture.investigation.report.conclusion;
      assert.ok((await page.locator('.result p').innerText()).includes(c[conclusion]));
      await page.locator('nav button').nth(2).click();
      await page.getByRole('button', { name: c['Clear all states'], exact: true }).click();
      assert.equal(await page.locator('dialog h2').innerText(), c.deleteConfirm.replace('{count}', locale === 'ar' ? '\u206847\u2069' : '47'));
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('dialog').isVisible(), false);
      const cases = {
        INSUFFICIENT_EVIDENCE: 'Not enough historical data to assess deviations.',
        NO_ANOMALY_FOUND: 'No deviations under the selected CPU/RAM/swap rules. This does not establish system health.',
        DATA_UNAVAILABLE: 'Cannot assess deviations: source data is unavailable or invalid.',
      };
      await page.locator('nav button').nth(0).click();
      for (const [status, conclusion] of Object.entries(cases)) {
        await page.evaluate(({status, conclusion}) => Object.assign(window.testState.fixture.investigation.report, {status, conclusion}), {status, conclusion});
        await page.getByRole('button', { name: c['Investigate →'], exact: true }).click();
        await page.getByText(c[conclusion], {exact: true}).waitFor();
        checks++;
      }
      await page.evaluate(report => { window.testState.fixture.investigation.report = report; }, fixture.investigation.report);

    }
    await page.locator('.language-control select').selectOption('ru');
    await page.evaluate(() => { window.testState.failure = true; });
    await page.getByRole('button', { name: catalogs.ru['View error ↗'], exact: true }).click();
    await page.getByText(catalogs.ru['Raw technical details'], { exact: true }).waitFor();
    assert.equal(await page.locator('.error-detail').innerText(), 'Test backend unavailable');
    await page.keyboard.press('Escape');
    await page.evaluate(() => { window.testState.failure = false; });
    await page.evaluate(() => sessionStorage.setItem('test-empty', '1'));
    await page.reload();
    await page.getByText(catalogs.ru['Starting collector…'], {exact: true}).waitFor();
    await page.getByText(catalogs.ru['The next background sample will appear here.'], {exact: true}).waitFor();
    assert.equal(await page.locator('progress').getAttribute('value'), '0');
    checks++;
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ checks, failures, errors }, null, 2));
    assert.deepEqual(failures, []);
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
