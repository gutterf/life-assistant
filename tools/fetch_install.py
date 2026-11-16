import sys, httpx

urls = [
    'https://cdn.jsdelivr.net/gh/debpalash/VoiceStudio@main/scripts/install.ps1',
    'https://raw.githubusercontent.com/debpalash/VoiceStudio/main/scripts/install.ps1',
    'https://github.com/debpalash/VoiceStudio/raw/main/scripts/install.ps1',
]
out = sys.argv[1]
for url in urls:
    try:
        r = httpx.get(url, timeout=15, trust_env=False, follow_redirects=True)
        print(url.split('/')[2], r.status_code, len(r.content), flush=True)
        if r.status_code == 200:
            open(out, 'wb').write(r.content)
            print('SAVED', out, flush=True)
            break
    except Exception as e:
        print(url.split('/')[2], 'ERR', str(e)[:100], flush=True)
