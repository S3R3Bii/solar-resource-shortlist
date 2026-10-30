"""Independent SQL calendar groups and Decimal reconstruction from native flux."""
import calendar,csv,gzip,hashlib,json,sqlite3
from collections import Counter,defaultdict
from decimal import Decimal,ROUND_FLOOR
from fractions import Fraction as Q
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(name):
 with (ROOT/'results'/name).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def main():
 with gzip.open(ROOT/'data/records.csv.gz','rt',encoding='utf-8',newline='') as f:raw=list(csv.DictReader(f))
 planned=json.loads((ROOT/'data/planned_points.json').read_text(encoding='utf-8'));conn=sqlite3.connect(':memory:');conn.execute('CREATE TABLE records(point TEXT,day TEXT,flux TEXT,good INTEGER,PRIMARY KEY(point,day))');conn.executemany('INSERT INTO records VALUES(?,?,?,?)',[(r['point_id'],r['date'],r['native_w_m2'],int(Decimal(r['native_w_m2']).is_finite() and Decimal(r['native_w_m2'])>=0)) for r in raw]);checks=0
 def check(actual,expected,label):
  nonlocal checks
  assert actual==str(expected),(label,actual,expected);checks+=1
 monthly={};qualified={};complete={};mean={};signature={};aliases={};seen={};by_id={p['id']:p for p in planned}
 for ident,y,m,n,good in conn.execute('SELECT point,CAST(substr(day,1,4) AS INTEGER),CAST(substr(day,6,2) AS INTEGER),COUNT(*),SUM(good) FROM records GROUP BY point,substr(day,1,7)'):
  assert n==calendar.monthrange(y,m)[1];monthly[ident,y,m]=(n,good,good*100>=95*n);checks+=1
 for ident in sorted(by_id,key=lambda i:list(by_id).index(i)):
  cells=list(conn.execute('SELECT day,flux,good FROM records WHERE point=? ORDER BY day',[ident]));payload='\n'.join(day+':'+flux+':'+str(bool(good)) for day,flux,good in cells);digest=hashlib.sha256(payload.encode()).hexdigest();signature[ident]=digest;aliases[ident]=seen.get(digest,'');seen.setdefault(digest,ident)
  for year in range(2001,2024):
   n=sum(monthly[ident,year,m][0] for m in range(1,13));count=sum(monthly[ident,year,m][1] for m in range(1,13));assert n==365+calendar.isleap(year);qualified[ident,year]=count*100>=99*n and all(monthly[ident,year,m][2] for m in range(1,13));complete[ident,year]=n==count
   values=[Q(Decimal(flux))*Q(24,1000) for day,flux,good in cells if day[:4]==str(year) and good];mean[ident,year]=sum(values,Q())/len(values) if values else None;checks+=1
 eligible={ident for ident in by_id if all(qualified[ident,y] for y in range(2001,2024)) and not aliases[ident]};counts=Counter(by_id[i]['cohort'] for i in eligible)
 rows=read('monthly_coverage.csv');assert len(rows)==len(monthly);seen_month=set()
 for r in rows:
  ident=r['point_id'];y=int(r['year']);m=int(r['month']);key=(ident,y,m);assert key not in seen_month;seen_month.add(key);n,count,good=monthly[key]
  for col,v in [('cohort',by_id[ident]['cohort']),('planned_days',n),('valid_days',count),('passes_95pct',good)]:check(r[col],v,col)
 rows=read('annual_inputs.csv');assert len(rows)==len(mean);seen_year=set()
 for r in rows:
  ident=r['point_id'];year=int(r['year']);key=(ident,year);assert key not in seen_year;seen_year.add(key);n=sum(monthly[ident,year,m][0] for m in range(1,13));count=sum(monthly[ident,year,m][1] for m in range(1,13));v=mean[key];ratio=Q(count,n)
  expected=dict(cohort=by_id[ident]['cohort'],planned_days=n,valid_days=count,complete=complete[key],year_qualified=qualified[key],mean_available_daily_kwh_m2_exact=f'{v.numerator}/{v.denominator}' if v is not None else'',coverage_exact=f'{ratio.numerator}/{ratio.denominator}',reasons='' if qualified[key] else 'annual_or_monthly_coverage_below_fixed_gate',point_eligible=ident in eligible)
  for col,v in expected.items():check(r[col],v,col)
 rows=read('point_eligibility.csv');assert len(rows)==len(by_id);seen_point=set()
 for r in rows:
  ident=r['point_id'];assert ident not in seen_point;seen_point.add(ident);p=by_id[ident];qyears=sum(qualified[ident,y] for y in range(2001,2024));reason=[]
  if qyears!=23:reason.append('not_all_23_years_qualified')
  if aliases[ident]:reason.append('identical_source_series_alias_'+aliases[ident])
  expected=dict(cohort=p['cohort'],latitude=p['latitude'],longitude=p['longitude'],nominal_latitude_lower=int(Decimal(str(p['latitude'])).to_integral_value(rounding=ROUND_FLOOR)),nominal_longitude_lower=int(Decimal(str(p['longitude'])).to_integral_value(rounding=ROUND_FLOOR)),qualified_years=qyears,series_sha256=signature[ident],alias_of=aliases[ident],eligible=ident in eligible,reasons=';'.join(reason))
  for col,v in expected.items():check(r[col],v,col)
 gate=json.loads((ROOT/'results/source_gate.json').read_text(encoding='utf-8'));expected=dict(status='PASS' if counts['west']>=4 and counts['east']>=4 else 'FAIL_MINIMUM_FIXED_COHORT',source_daily_rows=len(raw),planned_points=12,eligible_points=len(eligible),eligible_by_cohort=dict(counts),annual_rows=len(mean),monthly_rows=len(monthly),qualified_point_years=sum(qualified.values()),complete_point_years=sum(complete.values()),unavailable_daily_rows=conn.execute('SELECT COUNT(*) FROM records WHERE good=0').fetchone()[0],alias_points=sum(bool(x) for x in aliases.values()))
 for col,v in expected.items():assert gate[col]==v,(col,gate[col],v);checks+=1
 result=dict(status='PASS',checks=checks,source_daily_rows=len(raw),annual_rows=len(mean),monthly_rows=len(monthly),eligible_points=len(eligible),independence='Separate SQL key/calendar groups,Decimal native-flux integration andfull export reconstruction;no analysis-helper imports',limits='Source grid/date/coverage arithmetic,not source accuracy,station validation or parcel suitability')
 (ROOT/'results/independent_inputs.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))
if __name__=='__main__':main()
