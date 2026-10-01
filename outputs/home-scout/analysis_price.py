"""Read-only pre-implementation cohort check. Writes only this report directory."""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from services.transaction_service import normalize_name, normalize_dong, normalize_address, is_trusted_batch_mapping

def rows(path, encoding='utf-8-sig'):
    with path.open(encoding=encoding, newline='') as f:
        yield from csv.DictReader(f)

def main():
    masters = {(r['k-아파트명'], r['주소(시군구)'], r['주소(읍면동)']): r for r in rows(ROOT/'data/apartment/seoul_apartments.csv', 'cp949')}
    lookup = defaultdict(set)
    for r in rows(ROOT/'data/transactions/apartment_transaction_mapping.csv'):
        ident = (r.get('clustead_name') or r.get('livefit_name'), r['gu'], r['dong'])
        road = normalize_address(r['transaction_road_address'])
        if ident in masters and road and is_trusted_batch_mapping(r):
            lookup[(r['gu'],normalize_dong(r['dong']),normalize_name(r['transaction_apt_name']),road)].add(ident)
    buckets = defaultdict(list)
    months = Counter()
    reasons = Counter()
    matches = set()
    for r in rows(ROOT/'data/transactions/transaction_master.csv'):
        month = r['contract_date'][:7]
        months[month] += 1
        kind = r['transaction_type']
        if kind == 'rent' and r['monthly_rent_manwon'] not in ('0','0.0'):
            continue
        if kind not in ('trade','rent'):
            continue
        targets = lookup.get((r['gu'],normalize_dong(r['dong']),normalize_name(r['apartment_name']),normalize_address(r['road_address'])),set())
        if len(targets) != 1:
            reasons['ambiguous' if targets else 'unmapped'] += 1
            continue
        ident = next(iter(targets))
        matches.add(ident)
        area = float(r['area_m2'] or 0)
        band = next((label for label,lo,hi in ((59,55,60),(84,80,85),(114,110,115)) if lo <= area <= hi),None)
        if not band:
            continue
        price = float(r['trade_price_manwon'] if kind == 'trade' else r['deposit_manwon'])
        if price > 0:
            buckets[(ident,kind,band,month)].append(price)
    def eligible(ident, hh=300, strict=True):
        m = masters[ident]
        return float(m['k-전체세대수'] or 0)>=hh and (not strict or (m['k-세대타입(분양형태)']=='분양' and m['기타/의무/임대/임의=1/2/3/4']!='임대' and not re.search('임대|장기전세|행복주택',ident[0])))
    combos = {(k[0],k[1],k[2]) for k in buckets}
    def calc(start,split,end,min_n=5,hh=300,strict=True):
        result = {'trade':[],'rent':[]}
        for ident,kind,band in combos:
            if not eligible(ident,hh,strict): continue
            before,after = [],[]
            for month in months:
                if start<=month<split: before.extend(buckets.get((ident,kind,band,month),[]))
                elif split<=month<=end: after.extend(buckets.get((ident,kind,band,month),[]))
            if min(len(before),len(after))<min_n: continue
            a,b = median(before),median(after)
            result[kind].append(dict(name=ident[0],gu=ident[1],dong=ident[2],band=band,before=a,after=b,before_n=len(before),after_n=len(after),pct=round((b/a-1)*100,4)))
        for values in result.values(): values.sort(key=lambda x:(-x['pct'],x['gu'],x['dong'],x['name'],x['band']))
        return result
    output = {'months':dict(sorted(months.items())),'matching':dict(reasons),'matched_complexes':len(matches),'cases':{},'sensitivity':[]}
    windows = {'3m':('2026-03','2026-06','2026-08'),'6m':('2025-09','2026-03','2026-08'),'latest3m':('2026-04','2026-07','2026-09')}
    for name,window in windows.items():
        output['cases'][name] = calc(*window)
        for min_n in (3,5,10):
            for hh in (200,300,500):
                c=calc(*window,min_n=min_n,hh=hh)
                output['sensitivity'].append(dict(window=name,min_n=min_n,hh=hh,**{k:len(v) for k,v in c.items()}))
    output['unfiltered6m'] = calc(*windows['6m'],strict=False)
    target = Path(__file__).with_name('analysis_price.json')
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k not in ('cases','unfiltered6m')},ensure_ascii=False,indent=2))
    for name,case in output['cases'].items():
        for kind,values in case.items(): print(name,kind,len(values),json.dumps(values[:3]+values[-3:],ensure_ascii=False))

if __name__=='__main__': main()
