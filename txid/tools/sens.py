import base64,re,subprocess,json,os
html=open('loggedout.html',encoding='utf8').read()
m=re.search(r'(name="twitter-site-verification"[^>]*content=")([^"]+)"',html)
key=bytearray(base64.b64decode(m.group(2)))
def run(k):
    h=html.replace(m.group(2),base64.b64encode(bytes(k)).decode())
    open('/tmp/mut.html','w').write(h)
    p=subprocess.run(['node','run.mjs','/tmp/mut.html'],capture_output=True,text=True)
    a=[l for l in p.stderr.splitlines() if l.startswith('ANIMATE') or 'currentTime' in l]
    return tuple(a)
base=run(key)
print(base)
for i in range(len(key)):
    for delta in (1,5):
        k=bytearray(key); k[i]=(k[i]+delta)%256
        r=run(k)
        if r!=base:
            print(i,delta,'row' if r[0]!=base[0] else '', 'time' if r[1:]!=base[1:] else '')
