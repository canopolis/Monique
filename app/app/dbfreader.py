import struct, datetime, os
def read_fpt(path):
    if not os.path.exists(path): return None
    data=open(path,'rb').read()
    bs=struct.unpack('>H',data[6:8])[0] or 64
    return data,bs
def read_dbf(path, enc='cp1252'):
    f=open(path,'rb').read()
    ver=f[0]; n=struct.unpack('<I',f[4:8])[0]; hl=struct.unpack('<H',f[8:10])[0]; rl=struct.unpack('<H',f[10:12])[0]
    fields=[];pos=32;off=1
    while f[pos]!=0x0D and pos<hl:
        name=f[pos:pos+11].split(b'\0')[0].decode('ascii','replace'); t=chr(f[pos+11]); ln=f[pos+16]; dec=f[pos+17]
        fields.append((name,t,ln,dec,off)); off+=ln; pos+=32
    memo=None
    base=os.path.splitext(path)[0]
    for ext in ('.fpt','.FPT'):
        if os.path.exists(base+ext): memo=read_fpt(base+ext)
    rows=[]
    for i in range(n):
        r=f[hl+i*rl: hl+(i+1)*rl]
        if len(r)<rl: break
        deleted = r[0:1]==b'*'
        d={'_deleted':deleted}
        for name,t,ln,dec,o in fields:
            raw=r[o:o+ln]
            try:
                if t in 'CV': v=raw.decode(enc,'replace').rstrip(' \x00')
                elif t in 'NF':
                    s=raw.decode('ascii','replace').strip().replace('\x00','')
                    v=float(s) if s and s not in('.','-') and '*' not in s else 0.0
                elif t=='D':
                    s=raw.decode('ascii','replace').strip()
                    v=datetime.date(int(s[:4]),int(s[4:6]),int(s[6:8])) if s and s.strip('0') and len(s)==8 else None
                elif t=='L': v= raw in (b'T',b't',b'Y',b'y')
                elif t=='I': v=struct.unpack('<i',raw)[0]
                elif t=='Y': v=struct.unpack('<q',raw)[0]/10000.0
                elif t=='B':
                    v=struct.unpack('<d',raw)[0] if ln==8 else 0
                elif t=='T':
                    jd,ms=struct.unpack('<ii',raw)
                    v=(datetime.date.fromordinal(jd-1721425) if jd>0 else None)
                elif t in 'MGW':
                    blk=struct.unpack('<i',raw)[0] if ln==4 else int(raw.strip() or 0)
                    v=''
                    if memo and blk>0:
                        data,bs=memo; p=blk*bs
                        if p+8<=len(data):
                            L=struct.unpack('>I',data[p+4:p+8])[0]
                            v=data[p+8:p+8+L].decode(enc,'replace')
                else: v=raw
            except Exception as e: v=None
            d[name.lower()]=v
        rows.append(d)
    return fields,rows
