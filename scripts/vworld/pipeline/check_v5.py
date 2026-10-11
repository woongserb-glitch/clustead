import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import json,collections,csv,re,sys
from shapely.geometry import shape
from shapely.strtree import STRtree
sys.stdout.reconfigure(encoding="utf-8")
rows=[json.loads(l) for l in open(f"{R}/data/derived/vworld/complex_buildings_v5.jsonl",encoding="utf-8")]
M={(r["k-아파트명"].strip(),r["주소(시군구)"].strip(),r["주소(읍면동)"].strip()):r for r in csv.DictReader(open(f"{R}/data/apartment/seoul_apartments.csv",encoding="cp949"))}
rows=[r for r in rows if tuple(r["key"]) in M]  # 재건축·중복으로 마스터에서 빠진 단지는 건너뛴다
addr=lambda k:(M[tuple(k)]["kapt도로명주소"] or "").strip()
RT=re.compile(r"\(.*?\)|임대|분양|제\d+|SH|sh|공공|국민|행복|영구|아파트|\s")
fam=lambda a,b: addr(a)==addr(b) or RT.sub("",a[0])==RT.sub("",b[0])
G=[];O=[]
for ri,r in enumerate(rows):
    for b in r["buildings"]:
        G.append(shape(b["geom"]).buffer(0)); O.append(ri)
t=STRtree(G); pairs=collections.Counter()
for i,g in enumerate(G):
    for j in t.query(g):
        j=int(j)
        if j<=i or O[i]==O[j]: continue
        if g.intersection(G[j]).area>0.5*min(g.area,G[j].area):
            a,b=rows[O[i]],rows[O[j]]
            if fam(a["key"],b["key"]): continue
            pairs[(O[i],O[j])]+=1
print("가족 아닌 단지쌍 공유:",len(pairs),"건물",sum(pairs.values()))
for (a,b),c in pairs.most_common(int(sys.argv[1]) if len(sys.argv)>1 else 25):
    print(f"  {rows[a]['key'][0]}({rows[a]['bldg_how'][:16]},{rows[a]['want']}/{rows[a]['n']}) <> {rows[b]['key'][0]}({rows[b]['bldg_how'][:16]},{rows[b]['want']}/{rows[b]['n']}) 공유{c}")
