import argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--modules',type=int,required=True);a=p.parse_args(); r=Path('generated');
if r.exists(): import shutil; shutil.rmtree(r)
for i in range(a.modules):
 d=r/f'mod{i:04d}'; d.mkdir(parents=True); (d/'module.py').write_text(f'def value(): return {i}\n'); (d/'test_module.py').write_text(f'from generated.mod{i:04d}.module import value\ndef test_value(): assert value()=={i}\n')
print(f'generated {a.modules} modules')
