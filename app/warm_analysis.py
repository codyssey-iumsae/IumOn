"""Analyze public policy text only. No personal profile is sent or saved."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from engine import load_catalog,retrieve
from analysis import analyze

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=36)
    args=parser.parse_args()
    catalog,_=load_catalog()
    # Diversify public pre-analysis across all needs, local and central sources.
    ordered=[];seen=set()
    for topic in ['생활비','건강','돌봄','주거','일자리']:
        for p in retrieve(catalog,{'priority':topic,'needs':[topic]})[:max(12,args.limit//3)]:
            if p['id'] not in seen:ordered.append(p);seen.add(p['id'])
    chosen=ordered[:args.limit] if args.limit>0 else catalog
    done=failed=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(analyze,p):p for p in chosen}
        for future in as_completed(futures):
            try:future.result();done+=1
            except Exception:failed+=1
            print(f'public analysis {done+failed}/{len(chosen)}, verified={done}, failed={failed}',flush=True)

if __name__=='__main__':main()
