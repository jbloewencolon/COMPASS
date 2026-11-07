"""Optional browser regression/audit; Playwright and an audited axe script are dev tools.

Start a throwaway demo instance. Pass a local integrity-checked axe script; this
helper never downloads code or changes the app's Content Security Policy.
"""

import argparse
import json
import re
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8000')
parser.add_argument('--axe-script', type=Path, required=True)
parser.add_argument('--chromium', default=shutil.which('chromium'))
parser.add_argument('--output', type=Path, default=Path('/tmp/compass-ui-audit.json'))
args = parser.parse_args()
report=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    # Test-only injection of the integrity-checked audit script. App CSP is unchanged.
    page=browser.new_page(bypass_csp=True,viewport={'width':1280,'height':900})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(args.url,wait_until='networkidle')
    page.get_by_role('button',name=re.compile('Alex Morgan')).click()
    page.get_by_role('button',name='Sources',exact=True).wait_for()
    page.add_script_tag(path=str(args.axe_script))
    def audit(label):
        result=page.evaluate("async () => { const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}}); return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,targets:v.nodes.map(n=>n.target)})),incomplete:r.incomplete.map(v=>v.id),passes:r.passes.length}; }")
        report.append({'page':label,**result})
    for mode in ('simple','advanced'):
        page.locator('#view-mode').select_option(mode)
        page.get_by_role('button',name='Sources',exact=True).click()
        page.get_by_role('button',name='＋ Import source').click()
        dialog=page.get_by_role('dialog')
        dialog.wait_for()
        notice=page.locator('#source-import-safety')
        assert notice.is_visible()
        assert notice.get_attribute('role')=='note'
        assert 'source-import-safety' in dialog.get_by_label('Preserved source text').get_attribute('aria-describedby')
        audit(mode+' source import')
        page.keyboard.press('Escape')
        page.get_by_role('dialog').wait_for(state='hidden')
        for name in ('Home','Reviews','Settings'):
            page.get_by_role('button',name=name,exact=True).click()
            audit(mode+' '+name)
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_role('button',name='Sources',exact=True).click()
    page.get_by_role('button',name='＋ Import source').click()
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    audit('mobile source import')
    assert not errors,errors
    axe_version=page.evaluate('axe.version')
    browser.close()
args.output.write_text(json.dumps({'axe_version':axe_version,'checks':report,'javascript_errors':errors},indent=2))
print(json.dumps({'checks':len(report),'violations':[r for r in report if r['violations']],'javascript_errors':errors},indent=2))

assert not any(row['violations'] for row in report), 'Automated accessibility violations; inspect the report'
