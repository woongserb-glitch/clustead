import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import json,collections,csv,re,sys
from shapely.geometry import shape
sys.stdout.reconfigure(encoding="utf-8")
R = R
rows=[json.loads(l) for l in open(f"{R}/data/derived/vworld/complex_buildings_v5.jsonl",encoding="utf-8")]
M={(r["k-아파트명"].strip(),r["주소(시군구)"].strip(),r["주소(읍면동)"].strip()):r for r in csv.DictReader(open(f"{R}/data/apartment/seoul_apartments.csv",encoding="cp949"))}
rows=[r for r in rows if tuple(r["key"]) in M]  # 재건축·중복으로 마스터에서 빠진 단지는 건너뛴다
addr=lambda k:(M[tuple(k)]["kapt도로명주소"] or "").strip()
RT=re.compile(r"\(.*?\)|임대|분양|제\d+|SH|sh|공공|국민|행복|영구|아파트|\s")
# 가족 묶음(같은 주소 또는 임대 토큰 뺀 이름 같음 + 같은 구)
fam={}
groups=collections.defaultdict(list)
for i,r in enumerate(rows):
    k=tuple(r["key"]); groups[("a",addr(k))].append(i) if addr(k) else None
    groups[("n",k[1],RT.sub("",k[0]))].append(i)
parent=list(range(len(rows)))
def f(x):
    while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
    return x
for g in groups.values():
    for x in g[1:]: parent[f(x)]=f(g[0])
fams=collections.defaultdict(list)
for i in range(len(rows)): fams[f(i)].append(i)
famstat=collections.Counter(); out=[]
for root,ids in fams.items():
    if len(ids)<2: continue
    w=sum(rows[i]["want"] for i in ids)
    sh=set()
    for i in ids:
        for b in rows[i]["buildings"]: sh.add(json.dumps(b["geom"])[:200])
    n=len(sh)
    ok = n==w or abs(n-w)<=max(1,round(w*0.1))
    for i in ids:
        if rows[i]["status"] in("diff",) : famstat["family_ok" if ok else "family_diff"]+=1
        rows[i]["family"]=[rows[j]["key"][0] for j in ids if j!=i]; rows[i]["family_ok"]=ok
c=collections.Counter(r["status"]+("(가족OK)" if r.get("family_ok") and r["status"]=="diff" else "") for r in rows)
print(c)
print("\n## diff (가족 아님 또는 가족도 불일치) 표본")
d=[r for r in rows if r["status"]=="diff" and not r.get("family_ok")]
print(len(d))
cc=collections.Counter("더많음" if r["n"]>r["want"] else "더적음" for r in d); print(cc)
for r in sorted(d,key=lambda r:-abs(r["n"]-r["want"]))[:int(sys.argv[1]) if len(sys.argv)>1 else 40]:
    print(f"  {r['key'][0]}({r['key'][1]}) 마스터{r['want']} 매칭{r['n']} 라벨{r['labeled']} {r['spbd_method'][:22]} {r['bldg_how']} {r.get('family','')}")
print("\n## none/ghost")
for r in rows:
    if r["status"] in("none","ghost"): print(f"  [{r['status']}] {r['key'][0]}({r['key'][1]} {r['key'][2]}) 마스터{r['want']}동 {M[tuple(r['key'])]['k-사용검사일-사용승인일'][:4]} {addr(r['key'])}")
