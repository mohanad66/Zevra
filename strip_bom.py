path = r'D:\Programming\Zevra\frontend\nginx.conf'
d = open(path,'rb').read()
if d[:3]==b'\xef\xbb\xbf':
    d = d[3:]
    open(path,'wb').write(d)
    print('bom_removed')
else:
    print('no_bom')
