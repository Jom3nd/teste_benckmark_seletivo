import ast,argparse,subprocess,time,json,csv,statistics,hashlib,sys
from pathlib import Path
ROOT=Path.cwd(); SRC=ROOT/'src'; TEST=ROOT/'tests'; CACHE=ROOT/'.cache/index.json'
def files(): return sorted([*SRC.rglob('*.py'),*TEST.rglob('*.py')])
def key(p): return p.relative_to(ROOT).as_posix()
def changed():
 try:
  out=subprocess.check_output(['git','diff','--name-only','HEAD'],text=True).splitlines()+subprocess.check_output(['git','diff','--name-only','--cached'],text=True).splitlines()
  return sorted({x for x in out if x.endswith('.py')})
 except Exception: return []
def parse_all():
 t=time.perf_counter(); fs=files(); discovery=(time.perf_counter()-t)*1000; t=time.perf_counter(); deps={key(f):set() for f in fs}; symbols={};
 for f in fs:
  tree=ast.parse(f.read_text()); symbols[key(f)]={'classes':[n.name for n in ast.walk(tree) if isinstance(n,ast.ClassDef)],'functions':[n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]}
  for n in ast.walk(tree):
   names=[]
   if isinstance(n,ast.Import): names=[a.name for a in n.names]
   if isinstance(n,ast.ImportFrom) and n.module: names=[n.module]
   for m in names:
    p=m.replace('.','/')+'.py'; q=m.replace('.','/')+'/__init__.py'
    for cand in (p,q):
     if cand in deps: deps[key(f)].add(cand)
 astms=(time.perf_counter()-t)*1000; t=time.perf_counter(); rev={x:set() for x in deps}
 for a,bs in deps.items():
  for b in bs: rev.setdefault(b,set()).add(a)
 graphms=(time.perf_counter()-t)*1000; return fs,deps,rev,symbols,discovery,astms,graphms
def fingerprint(fs):
 h=hashlib.sha256()
 for f in fs: h.update(key(f).encode()); h.update(f.read_bytes())
 return h.hexdigest()
def build_index():
 fs,deps,rev,sym,d,a,g=parse_all(); t=time.perf_counter(); obj={'fingerprint':fingerprint(fs),'deps':{k:sorted(v) for k,v in deps.items()},'rev':{k:sorted(v) for k,v in rev.items()},'symbols':sym}; CACHE.parent.mkdir(exist_ok=True); CACHE.write_text(json.dumps(obj)); idx=(time.perf_counter()-t)*1000; return obj,(d,a,g,idx),len(fs)
def load_index():
 t=time.perf_counter(); obj=json.loads(CACHE.read_text()); ms=(time.perf_counter()-t)*1000; return obj,ms
def select(rev,ch):
 t=time.perf_counter(); seen=set(ch); q=list(ch); paths={x:[x] for x in ch}
 while q:
  x=q.pop(0)
  for y in rev.get(x,[]):
   if y not in seen: seen.add(y); paths[y]=paths[x]+[y]; q.append(y)
 tests=sorted(x for x in seen if x.startswith('tests/')); return tests,paths,(time.perf_counter()-t)*1000
def run_tests(selected=None):
 t=time.perf_counter(); cmd=[sys.executable,'-m','pytest','-q'];
 if selected is not None: cmd += selected if selected else ['--collect-only']
 r=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); return (time.perf_counter()-t)*1000,r.returncode
def one(mode,execute=True):
 start=time.perf_counter(); ch=changed(); alltests=[key(x) for x in TEST.rglob('test_*.py')]; d=a=g=i=s=0.; analyzed=0; paths={}; selected=alltests
 if mode=='full': pass
 elif mode=='selective':
  fs,deps,rev,sym,d,a,g=parse_all(); analyzed=len(fs); selected,paths,s=select(rev,ch)
 elif mode=='indexed':
  if CACHE.exists():
   obj,i=load_index(); fs=files()
   if obj.get('fingerprint')!=fingerprint(fs): obj,(d,a,g,i),analyzed=build_index()
  else: obj,(d,a,g,i),analyzed=build_index()
  selected,paths,s=select(obj['rev'],ch)
 tm,rc=run_tests(selected if mode!='full' else None) if execute else (0,0); total=(time.perf_counter()-start)*1000
 return {'mode':mode,'changed':ch,'total_tests':len(alltests),'selected_tests':len(selected),'ignored_tests':len(alltests)-len(selected),'discovery_ms':d,'ast_ms':a,'graph_ms':g,'index_ms':i,'selection_ms':s,'test_ms':tm,'total_ms':total,'files_analyzed':analyzed,'selected':selected,'paths':paths,'test_exit':rc}
def report(r):
 print('='*40+'\nSELECTIVE TEST ANALYSIS\n'+'='*40); print('Changed files:',*(r['changed'] or ['(none)']),sep='\n- '); print('Selected tests:',*(r['selected'] or ['(none)']),sep='\n- '); print(f"tests={r['total_tests']} selected={r['selected_tests']} ignored={r['ignored_tests']} ast={r['ast_ms']:.3f}ms selection={r['selection_ms']:.3f}ms tests={r['test_ms']:.3f}ms total={r['total_ms']:.3f}ms")
 for t in r['selected']:
  if t in r['paths']: print('Reason: '+' -> '.join(r['paths'][t]))
def main():
 p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['full','selective','indexed','benchmark'],default='selective'); p.add_argument('--repeat',type=int,default=5); p.add_argument('--results',default='../benchmark/results'); a=p.parse_args(); modes=['full','selective','indexed'] if a.mode=='benchmark' else [a.mode]; rows=[]
 for m in modes:
  for _ in range(a.repeat if a.mode=='benchmark' else 1): rows.append(one(m))
 for r in rows: report(r)
 if a.mode=='benchmark':
  out=Path(a.results); out.mkdir(parents=True,exist_ok=True); stamp=str(int(time.time())); (out/f'python-{stamp}.json').write_text(json.dumps(rows,indent=2)); cols=[k for k,v in rows[0].items() if not isinstance(v,(list,dict))];
  with (out/f'python-{stamp}.csv').open('w',newline='') as f: q=csv.DictWriter(f,fieldnames=cols); q.writeheader(); q.writerows([{k:r[k] for k in cols} for r in rows])
  for m in modes:
   xs=[r for r in rows if r['mode']==m]; print(m,{k:{'mean':statistics.mean(r[k] for r in xs),'min':min(r[k] for r in xs),'max':max(r[k] for r in xs),'stdev':statistics.pstdev(r[k] for r in xs)} for k in ['ast_ms','selection_ms','test_ms','total_ms']})
if __name__=='__main__': main()
