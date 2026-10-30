"""Qualify fixed source calendars before any resource ranking or prediction."""
import argparse,calendar,csv,gzip,hashlib,json,math
from collections import defaultdict,Counter
from fractions import Fraction as F
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def exact(x):return f'{x.numerator}/{x.denominator}'
def write(path,rows):
 with path.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def prepare(records,planned):
 grouped=defaultdict(list);monthly=defaultdict(list);point_rows=defaultdict(list)
 for r in records:
  grouped[r['point_id'],int(r['date'][:4])].append(r);monthly[r['point_id'],r['date'][:7]].append(r);point_rows[r['point_id']].append(r)
 annual=[];months=[];point_audit=[];seen={};valid_years=Counter()
 for p in planned:
  ident=p['id'];signature=hashlib.sha256('\n'.join(r['date']+':'+r['native_w_m2']+':'+r['valid'] for r in sorted(point_rows[ident],key=lambda r:r['date'])).encode()).hexdigest();alias=seen.get(signature,'');seen.setdefault(signature,ident)
  for y in range(2001,2024):
   rows=grouped[ident,y];n=366 if calendar.isleap(y) else 365;valid=[r for r in rows if r['valid']=='True'];assert len(rows)==n and len({r['date'] for r in rows})==n
   good=True
   for month in range(1,13):
    items=monthly[ident,f'{y}-{month:02d}'];total=calendar.monthrange(y,month)[1];count=sum(r['valid']=='True' for r in items);assert len(items)==total;mg=count*100>=95*total;good=good and mg;months.append(dict(point_id=ident,cohort=p['cohort'],year=y,month=month,planned_days=total,valid_days=count,passes_95pct=mg))
   good=good and len(valid)*100>=99*n;valid_years[ident]+=good;resource=sum((F(r['irradiation_kwh_m2_day_exact']) for r in valid),F())/len(valid) if valid else None
   annual.append(dict(point_id=ident,cohort=p['cohort'],year=y,planned_days=n,valid_days=len(valid),complete=len(valid)==n,year_qualified=good,mean_available_daily_kwh_m2_exact=exact(resource) if resource is not None else'',coverage_exact=exact(F(len(valid),n)),reasons='' if good else 'annual_or_monthly_coverage_below_fixed_gate'))
  reasons=[]
  if valid_years[ident]!=23:reasons.append('not_all_23_years_qualified')
  if alias:reasons.append('identical_source_series_alias_'+alias)
  point_audit.append(dict(point_id=ident,cohort=p['cohort'],latitude=p['latitude'],longitude=p['longitude'],nominal_latitude_lower=math.floor(p['latitude']),nominal_longitude_lower=math.floor(p['longitude']),qualified_years=valid_years[ident],series_sha256=signature,alias_of=alias,eligible=not reasons,reasons=';'.join(reasons)))
 selected={r['point_id'] for r in point_audit if r['eligible']};counts=Counter(r['cohort'] for r in point_audit if r['eligible']);
 for r in annual:r['point_eligible']=r['point_id'] in selected
 gate=dict(status='PASS' if counts['west']>=4 and counts['east']>=4 else 'FAIL_MINIMUM_FIXED_COHORT',source_daily_rows=len(records),planned_points=len(planned),eligible_points=len(selected),eligible_by_cohort=dict(counts),annual_rows=len(annual),monthly_rows=len(months),qualified_point_years=sum(r['year_qualified'] for r in annual),complete_point_years=sum(r['complete'] for r in annual),unavailable_daily_rows=sum(r['valid']!='True' for r in records),alias_points=sum(bool(r['alias_of']) for r in point_audit),grid_evidence='Fixed1degree-center requested coordinates andreturned coordinate/source bindings;nominal cell bounds derive from published1degree grid;no internal-source cell ID or independent station accuracy claimed',scope='Mean ofavailable valid daily irradiation,not an imputed annualtotal;fixed unweighted point cohort,not parcels/national sample')
 return annual,months,point_audit,gate
def main():
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=ROOT/'results');a=p.parse_args();a.output_dir.mkdir(exist_ok=True)
 with gzip.open(ROOT/'data/records.csv.gz','rt',encoding='utf-8',newline='') as f:records=list(csv.DictReader(f))
 planned=json.loads((ROOT/'data/planned_points.json').read_text(encoding='utf-8'));annual,months,points,gate=prepare(records,planned)
 for name,rows in [('annual_inputs.csv',annual),('monthly_coverage.csv',months),('point_eligibility.csv',points)]:write(a.output_dir/name,rows)
 (a.output_dir/'source_gate.json').write_bytes((json.dumps(gate,indent=2)+'\n').encode());print(json.dumps(gate));assert gate['status']=='PASS','Preserve failure;no ranking scores'
if __name__=='__main__':main()
