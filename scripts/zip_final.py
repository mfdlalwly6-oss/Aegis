import os, zipfile
root="/home/zr0/Aegis"; out="/home/zr0/aegis-final.zip"
skip_dirs={".git","__pycache__","node_modules",".venv",".pytest_cache"}
skip_files={".env",".env.local"}
n=0
if os.path.exists(out): os.remove(out)
with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
    for dp,dn,fn in os.walk(root):
        dn[:]=[d for d in dn if d not in skip_dirs]
        for f in fn:
            if f in skip_files or f.endswith(".pyc") or ".dbbak" in f: continue
            p=os.path.join(dp,f); z.write(p,os.path.relpath(p,root)); n+=1
print("FILES=%d SIZE=%d"%(n,os.path.getsize(out)))
