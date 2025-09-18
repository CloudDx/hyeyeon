import json, sys, time

def log_json(**kw):
    kw.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    print(json.dumps(kw, ensure_ascii=False), file=sys.stdout, flush=True)
