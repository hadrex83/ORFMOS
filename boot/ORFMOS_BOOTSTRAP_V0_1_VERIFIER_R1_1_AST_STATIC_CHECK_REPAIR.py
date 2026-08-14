# ORFMOS DURABLE BOOT ANCHOR v0.1 — VERIFIER R1
import ast, hashlib, io, json, urllib.request
from pathlib import Path

SCHEMA="ORFMOS_DURABLE_BOOT_ANCHOR_V0_1_VERIFIER_R1_1_AST_STATIC_CHECK_REPAIR"
EXPECTED_BOOTSTRAP_NAME="ORFMOS_BOOTSTRAP_V0_1.py"
EXPECTED_BOOTSTRAP_SHA="bd96b01a06545633a98ccd68290db919d399a424ef32b0f9c4c57a1ddb98deb9"
EXPECTED_BOOTSTRAP_BYTES=10356
EXPECTED_SELECTOR_NAME="ORFMOS_ACTIVE_BOOT.json"
EXPECTED_SELECTOR_SHA="6aa31d60e0105bd7bfa0b82c26fb46ec8cc3f9d0e1bdb3ac33e02429429761b4"
EXPECTED_SELECTOR_BYTES=1002
EXPECTED_MANIFEST_SHA="18c74294439d84de07893fb029bdf154e38b8e9cd931e2a25965645ea8cc8895"
EXPECTED_MANIFEST_BYTES=2629
EXPECTED_SELECTOR_URL="https://raw.githubusercontent.com/hadrex83/ORFMOS/main/boot/ORFMOS_ACTIVE_BOOT.json"

def _resolve(name, sha):
    reg=globals().get("__ORFMOS_PREFLIGHT_STAGE_REGISTRY__")
    if isinstance(reg,dict):
        rec=reg.get(sha)
        if isinstance(rec,dict):
            p=Path(str(rec.get("path") or ""))
            if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha:
                return p,"PREFLIGHT_STAGE_REGISTRY"
        for rec in reg.values():
            if isinstance(rec,dict) and str(rec.get("sha256") or "").lower()==sha:
                p=Path(str(rec.get("path") or ""))
                if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha:
                    return p,"PREFLIGHT_STAGE_REGISTRY_SCAN"
    for root in (Path("/content/orfmos/preflight/stage"),Path("/content"),Path("."),Path("/mnt/data")):
        if root.is_dir():
            for p in list(root.glob(sha+"__*"))+[root/name]:
                if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha:
                    return p,str(root)
    raise RuntimeError("VERIFY_ARTIFACT_NOT_RESOLVED:"+name)

bp,bres=_resolve(EXPECTED_BOOTSTRAP_NAME,EXPECTED_BOOTSTRAP_SHA)
sp,sres=_resolve(EXPECTED_SELECTOR_NAME,EXPECTED_SELECTOR_SHA)
braw=bp.read_bytes()
sraw=sp.read_bytes()
source=braw.decode("utf-8")
source_tree=ast.parse(source, filename=str(bp))
imported_names=set()
write_primitives=[]
for node in ast.walk(source_tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            imported_names.add(alias.name)
    elif isinstance(node, ast.ImportFrom):
        imported_names.add(node.module or "")
    elif isinstance(node, ast.Call):
        func=node.func
        name=""
        if isinstance(func, ast.Name):
            name=func.id
        elif isinstance(func, ast.Attribute):
            parts=[]
            cur=func
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr);cur=cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            name=".".join(reversed(parts))
        if name in {"open","pathlib.Path.write_text","pathlib.Path.write_bytes","os.remove","os.unlink","os.rename","os.replace"}:
            write_primitives.append(name)
selector=json.loads(sraw.decode("utf-8"))

# Synthetic immutable BIOS target used to exercise the full fetch -> verify-all -> execute flow.
m1=b'globals()["__BOOT_TEST_M1__"]="OK"\n'
m2=b'globals()["__BOOT_TEST_M2__"]=globals().get("__BOOT_TEST_M1__")+"+OK"\n'
base="https://raw.githubusercontent.com/hadrex83/ORFMOS/main/test-fixture/"
manifest_url=base+"manifest.json"
test_manifest={
 "schema":"ORF_BIOS_MODULE_MANIFEST_V0_1",
 "bios_version":"TEST-0.1",
 "revision":"VERIFIER_FIXTURE",
 "execution_model":"ORDERED_SHARED_GLOBALS",
 "module_count":2,
 "modules":[
  {"bytes":len(m1),"file_name":"010.py","module_id":"TEST_010","order":10,"path":"modules/010.py","sha256":hashlib.sha256(m1).hexdigest()},
  {"bytes":len(m2),"file_name":"020.py","module_id":"TEST_020","order":20,"path":"modules/020.py","sha256":hashlib.sha256(m2).hexdigest()},
 ]
}
manifest_raw=(json.dumps(test_manifest,separators=(",",":"))+"\n").encode()
test_selector={
 "schema":"ORFMOS_ACTIVE_BOOT_SELECTOR_V0_1",
 "state":"ACTIVE",
 "selector_generation":999,
 "authority":"MUTABLE_SELECTOR_TO_IMMUTABLE_MANIFEST",
 "provider":"GITHUB_RAW",
 "repository":"hadrex83/ORFMOS",
 "branch":"main",
 "manifest":{
  "path":"test-fixture/manifest.json",
  "url":manifest_url,
  "bytes":len(manifest_raw),
  "sha256":hashlib.sha256(manifest_raw).hexdigest(),
  "bios_version":"TEST-0.1",
  "revision":"VERIFIER_FIXTURE",
  "publication_state":"IMMUTABLE",
 },
}
test_selector_raw=(json.dumps(test_selector,separators=(",",":"))+"\n").encode()

class _Resp:
    def __init__(self,url,raw):
        self.url=url;self.raw=raw;self.status=200
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def geturl(self): return self.url
    def read(self,n=-1): return self.raw if n is None or n < 0 else self.raw[:n]

mapping={
 EXPECTED_SELECTOR_URL:test_selector_raw,
 manifest_url:manifest_raw,
 base+"modules/010.py":m1,
 base+"modules/020.py":m2,
}
original_urlopen=urllib.request.urlopen
def _mock_urlopen(req,timeout=None):
    url=str(getattr(req,"full_url",req))
    if url not in mapping: raise RuntimeError("MOCK_URL_NOT_FOUND:"+url)
    return _Resp(url,mapping[url])

ns={"__name__":"__main__"}
urllib.request.urlopen=_mock_urlopen
try:
    exec(compile(braw,str(bp),"exec"),ns,ns)
finally:
    urllib.request.urlopen=original_urlopen

boot_record=ns.get("__ORFMOS_DURABLE_BOOT_ANCHOR__") or {}

checks={
 "bootstrap_sha_verified":hashlib.sha256(braw).hexdigest()==EXPECTED_BOOTSTRAP_SHA,
 "bootstrap_bytes_verified":len(braw)==EXPECTED_BOOTSTRAP_BYTES,
 "selector_sha_verified":hashlib.sha256(sraw).hexdigest()==EXPECTED_SELECTOR_SHA,
 "selector_bytes_verified":len(sraw)==EXPECTED_SELECTOR_BYTES,
 "bootstrap_compiles":compile(braw,str(bp),"exec") is not None,
 "fixed_selector_url":f'ORFMOS_BOOTSTRAP_SELECTOR_URL = "{EXPECTED_SELECTOR_URL}"' in source,
 "allowed_host_scoped":'ORFMOS_BOOTSTRAP_ALLOWED_HOST = "raw.githubusercontent.com"' in source,
 "allowed_repository_scoped":'ORFMOS_BOOTSTRAP_ALLOWED_REPOSITORY = "hadrex83/ORFMOS"' in source,
 "verify_all_before_execute_declared":"Phase 1 — read and verify every selected module before executing any module." in source,
 "exact_exec_semantics":'exec(compile(raw, item["url"], "exec"), globals(), globals())' in source,
 "no_subprocess":not any(name=="subprocess" or name.startswith("subprocess.") for name in imported_names),
 "no_filesystem_write":len(write_primitives)==0,
 "selector_schema":selector.get("schema")=="ORFMOS_ACTIVE_BOOT_SELECTOR_V0_1",
 "selector_active":selector.get("state")=="ACTIVE",
 "selector_provider_github_raw":selector.get("provider")=="GITHUB_RAW",
 "selector_manifest_immutable":(selector.get("manifest") or {}).get("publication_state")=="IMMUTABLE",
 "selector_manifest_sha":(selector.get("manifest") or {}).get("sha256")==EXPECTED_MANIFEST_SHA,
 "selector_manifest_bytes":(selector.get("manifest") or {}).get("bytes")==EXPECTED_MANIFEST_BYTES,
 "selector_execution_model":(selector.get("policy") or {}).get("execution_model")=="ORDERED_SHARED_GLOBALS",
 "mock_boot_complete":boot_record.get("state")=="COMPLETE",
 "mock_modules_verified":boot_record.get("module_count")==2,
 "mock_ordered_shared_globals":ns.get("__BOOT_TEST_M1__")=="OK" and ns.get("__BOOT_TEST_M2__")=="OK+OK",
 "mock_write_authority_none":boot_record.get("write_authority")=="NONE",
}
state="PASS" if all(checks.values()) else "FAIL"
report={
 "schema":SCHEMA,
 "state":state,
 "bootstrap":{"path":str(bp),"bytes":len(braw),"sha256":EXPECTED_BOOTSTRAP_SHA,"resolution":bres},
 "selector":{"path":str(sp),"bytes":len(sraw),"sha256":EXPECTED_SELECTOR_SHA,"resolution":sres},
 "selected_manifest":{"bytes":EXPECTED_MANIFEST_BYTES,"sha256":EXPECTED_MANIFEST_SHA},
 "mock_boot":boot_record,
 "checks":checks,
}
report_sha=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
report["report_sha256"]=report_sha
globals()["ORFMOS_DURABLE_BOOT_ANCHOR_V0_1_R1_1_VERIFICATION_REPORT"]=report

print("="*116)
print("ORFMOS DURABLE BOOT ANCHOR v0.1 — VERIFIER R1.1 AST STATIC CHECK REPAIR")
print("="*116)
print("Probe                    :",state)
print("Bootstrap SHA256         :",EXPECTED_BOOTSTRAP_SHA)
print("Selector SHA256          :",EXPECTED_SELECTOR_SHA)
print("Selected manifest SHA256 :",EXPECTED_MANIFEST_SHA)
print("Mock cold boot           :",boot_record.get("state"))
print("Execution model          :",boot_record.get("execution_model"))
print("Write authority          :",boot_record.get("write_authority"))
print("-"*116)
for k,v in checks.items():
    print(f"{k:<64}: {'PASS' if v else 'FAIL'}")
print("Report SHA256            :",report_sha)
print("="*116)
