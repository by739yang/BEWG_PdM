import pandas as pd, numpy as np, os
from sklearn.preprocessing import StandardScaler
BASE=r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
FEATS=['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature','Thermocouple','Voltage','Volume Flow RateRMS']
def load(fp):
    df=pd.read_csv(fp,sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'): df[c]=pd.to_numeric(df[c],errors='coerce')
    return df
for fn in ['valve1/0.csv','valve1/5.csv','valve2/0.csv','other/2.csv']:
    df=load(os.path.join(BASE,*fn.split('/')))
    y=df['anomaly'].values.astype(int); X=df[FEATS].values.astype(float)
    k0=int(len(X)*0.2)
    segs={'ref[0:%d]'%k0:slice(0,k0),'normal[%d:570]'%k0:slice(k0,570),'anom[570:]':slice(570,None)}
    print('===',fn,'n',len(X))
    for name,sl in segs.items():
        Z=(X[sl]-np.median(X[:k0],0))/np.where((np.percentile(X[:k0],75,0)-np.percentile(X[:k0],25,0))==0,1e-9,(np.percentile(X[:k0],75,0)-np.percentile(X[:k0],25,0)))
        print('  ',name,'n=%d'%len(Z),'mean|z|=%.2f'%np.abs(Z).mean(),'max|z|=%.2f'%np.abs(Z).max(),
              'lab_anom=%.2f'%y[sl].mean() if len(y[sl]) else '')
    print('   per-feature mean z:', dict(zip(FEATS, np.round(np.abs(Z).mean(0),2))) if False else '')
