import pandas as pd, numpy as np, os
BASE=r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
FEATS=['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature','Thermocouple','Voltage','Volume Flow RateRMS']
def load(fp):
    df=pd.read_csv(fp,sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'): df[c]=pd.to_numeric(df[c],errors='coerce')
    return df
def rscale(X):
    med=np.median(X,0); iqr=np.percentile(X,75,0)-np.percentile(X,25,0); sd=X.std(0)
    return med, np.where(iqr>1e-9, iqr, np.where(sd>1e-9, sd, 1.0))
for fn in ['valve1/0.csv','valve1/5.csv']:
    df=load(os.path.join(BASE,*fn.split('/'))); X=df[FEATS].values.astype(float); y=df['anomaly'].values.astype(int)
    n=len(X); k0=int(n*0.2)
    med,sc=rscale(X[:k0]); Z=(X-med)/sc
    print('===',fn)
    for i,f in enumerate(FEATS):
        print('   %-20s ref_med=%10.3f ref_iqr=%10.3f  z(ref)=%.2f z(norm_tail)=%.2f z(anom)=%.2f' % (
            f, np.median(X[:k0,i]), sc[i], np.abs(Z[:k0,i]).mean(), np.abs(Z[k0:570,i]).mean(), np.abs(Z[570:,i]).mean()))
