print('=' * 80)
print('BOX TEST - PRE-FLIGHT CHECK')
print('=' * 80)
print()

# Check 1: Cache
print('[CHECK 1] MongoDB Cache')
try:
    from app.models.cloud_research import CloudResearchStore
    store = CloudResearchStore()
    result = store.collection.find_one({'cloud_name': 'Box'})
    if result:
        print('  [WARN] Box in cache (already cleared)')
    else:
        print('  [OK] Box NOT in cache')
except Exception as e:
    print(f'  [ERROR] {e}')

# Check 2: Code
print()
print('[CHECK 2] Server Code')
with open('app/cloud_api_researcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

checks = {
    'Keyword detection': 'user_group_keywords' in content,
    'JS activation': 'should_try_js' in content,
    'JS import': 'from app.js_scraper import scrape_with_javascript' in content,
}

for name, ok in checks.items():
    status = '[OK]' if ok else '[MISS]'
    print(f'  {status} {name}')

all_ok = all(checks.values())
print()
if all_ok:
    print('[READY] All checks passed')
else:
    print('[FAIL] Restart server')

# Show guardrails
print()
print('=' * 80)
print('6 VERIFICATION GUARDRAILS')
print('=' * 80)
print()
print('[ ] 1. JS SCRAPER LOGS')
print('       Must see: [JS SCRAPER] Rendering https://...')
print()
print('[ ] 2. BOX ENDPOINTS')
print('       /2.0/users, /2.0/groups, /2.0/group_memberships')
print()
print('[ ] 3. NORMALIZATION')
print('       [NORMALIZE] Mapping logs')
print()
print('[ ] 4. COVERAGE >= 75%')
print('       Target: 6-8 operations mapped')
print()
print('[ ] 5. CONFIDENCE >= 0.70')
print('       Not 0.40 like before')
print()
print('[ ] 6. NO HALLUCINATIONS')
print('       All /2.0/* format')
print()
print('=' * 80)
print('TEST: Send "Research APIs for Box"')
print('=' * 80)
