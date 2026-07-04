#!/usr/bin/env python3
"""Publish a new lease version in one step.

Usage:
    python3 tools/release_lease.py --version "Version 1.6" --date "July 20, 2026"

Does, in order:
  1. Updates version/versionDate in data/identity.json (the single source).
  2. Rewrites the version line on lease/index.html.
  3. Rebuilds all PDFs (tools/build_lease_docs.py).
  4. Snapshots lease.md + the three public PDFs into lease/archive/v<Y.M.D>/.
  5. Runs tools/check_site.py.

You still edit lease/lease.md's own header by hand (it's legal text), and
this script will fail the final check step if you forget — by design.
"""

import argparse, datetime, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True, help='e.g. "Version 1.6"')
    ap.add_argument('--date', required=True, help='e.g. "July 20, 2026"')
    args = ap.parse_args()

    when = datetime.datetime.strptime(args.date, '%B %d, %Y')
    archive = os.path.join(ROOT, 'lease', 'archive', f'v{when.strftime("%Y.%m.%d")}')

    # 1. identity.json
    ident_path = os.path.join(ROOT, 'data', 'identity.json')
    ident = json.load(open(ident_path))
    old = f"{ident['version']}, {ident['versionDate']}"
    ident['version'], ident['versionDate'] = args.version, args.date
    with open(ident_path, 'w') as f:
        json.dump(ident, f, indent=2)
        f.write('\n')
    print(f'identity.json: {old} -> {args.version}, {args.date}')

    # 2. lease/index.html version line
    page_path = os.path.join(ROOT, 'lease', 'index.html')
    page = open(page_path).read()
    new_line = f'{args.version}, {args.date}.'
    page2 = re.sub(r'Version \d+\.\d+, [A-Z][a-z]+ \d+, \d{4}\.', new_line, page, count=1)
    if page2 == page:
        print('WARNING: version line on lease/index.html not found — update it by hand')
    open(page_path, 'w').write(page2)

    # 3. rebuild
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'build_lease_docs.py')], check=True)

    # 4. archive snapshot
    os.makedirs(archive, exist_ok=True)
    for f in ('lease.md', 'lease.pdf', 'lease-terms-sheet.pdf', 'letter-of-intent.pdf'):
        shutil.copy2(os.path.join(ROOT, 'lease', f), os.path.join(archive, f))
    print('archived to', os.path.relpath(archive, ROOT))

    # 5. checks (fails loudly if lease.md's own header wasn't bumped, etc.)
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'check_site.py')], check=True)
    print('release complete — review `git status`, then commit.')

if __name__ == '__main__':
    main()
