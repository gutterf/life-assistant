import httpx

URL = 'https://wbapp-pvhbane0i9g0u3m2gdh8us.app.workbuddy.host/api/v1/chat'
r = httpx.post(URL, json={
    'text': '附近有什么好玩的',
    'location': {'latitude': 30.2741, 'longitude': 120.1551},
    'session_id': 'livetest2',
}, params={'sharecode': '46ZRHVVXRQ'}, timeout=120, trust_env=False)
print('status', r.status_code)
if r.status_code != 200:
    print(r.text[:300])
else:
    d = r.json()
    print('intent', d.get('intent'))
    cards = d.get('cards') or []
    print('cards', len(cards), [c.get('type') for c in cards])
    print('reply_head', (d.get('reply') or '')[:80])
