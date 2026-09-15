import pandas as pd, numpy as np, glob, os
BASE=r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
rows=[]
for f in sorted(glob.glob(os.path.join(BASE,'*','*.csv'))):
    df=pd.read_csv(f,sep=';'); df.columns=[c.strip() for c in df.columns]
    if 'anomaly' not in df.columns:
        rows.append(dict(file=os.path.relpath(f,BASE), n=len(df), anom_frac=None, first_anom=None, first_cp=None, cols=','.join(df.columns)[:60])); continue
    y=pd.to_numeric(df['anomaly'],errors='coerce').values
    cp=pd.to_numeric(df['changepoint'],errors='coerce').values if 'changepoint' in df.columns else np.zeros(len(y))
    first=int(np.argmax(y==1)) if (y==1).any() else -1
    rows.append(dict(file=os.path.relpath(f,BASE), n=len(y), anom_frac=round(float(np.nanmean(y)),3),
                     first_anom=first, first_cp=int(np.argmax(cp==1)) if (cp==1).any() else -1, cols=''))
d=pd.DataFrame(rows)
print(d.to_string(index=False))
