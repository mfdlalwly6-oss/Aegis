import os, sys, zipfile

root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
# Output must live OUTSIDE the walked tree, or the growing zip gets re-walked
# and the archive balloons until the disk fills. Default: sibling of root.
out = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(root), "aegis-final.zip"))
skip_dirs = {".git", "__pycache__", "node_modules", ".venv", ".pytest_cache"}
skip_files = {".env", ".env.local", "aegis-final.zip"}
n = 0
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in skip_dirs]
        for f in fn:
            if f in skip_files or f.endswith(".pyc") or ".dbbak" in f or f.endswith(".db") or f.endswith(".zip"):
                continue
            p = os.path.join(dp, f)
            z.write(p, os.path.relpath(p, root))
            n += 1
print("FILES=%d SIZE=%d" % (n, os.path.getsize(out)))
