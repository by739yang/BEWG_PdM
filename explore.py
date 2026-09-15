import pandas as pd, glob, os
base = r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
p = os.path.join(base,'valve1','0.csv')
df = pd.read_csv(p)
print('shape', df.shape)
print('cols', list(df.columns))
print(df.head(3).to_string())
print('dt diff:', df['datetime'].iloc[1], df['datetime'].iloc[0])
print('anomaly counts:', df['anomaly'].value_counts().to_dict() if 'anomaly' in df else 'NA')
af = pd.read_csv(os.path.join(base,'anomaly-free','anomaly-free.csv'))
print('anomaly-free shape', af.shape, 'cols', list(af.columns))
print('af anomaly counts', af['anomaly'].value_counts().to_dict() if 'anomaly' in af else 'NA')
for f in sorted(glob.glob(os.path.join(base,'*','*.csv')))[:35]:
    d = pd.read_csv(f, usecols=lambda c: True, nrows=5)
print('total files ok')
sizes = {f: len(pd.read_csv(f)) for f in glob.glob(os.path.join(base,'*','*.csv'))}
print('rows per file sample:', list(sizes.items())[:5])
