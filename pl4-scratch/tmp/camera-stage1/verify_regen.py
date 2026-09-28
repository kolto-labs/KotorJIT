import json,subprocess,sys
old=json.loads(subprocess.check_output(["git","show",":data/addresses/k1_gog_103.json"]))
new=json.load(open("data/addresses/k1_gog_103.json"))
added=sorted(set(new["sites"])-set(old["sites"])); removed=sorted(set(old["sites"])-set(new["sites"]))
changed=sorted(k for k in set(old["sites"])&set(new["sites"]) if old["sites"][k]!=new["sites"][k])
top=sorted(k for k in set(old)|set(new) if k not in ("sites","summary") and old.get(k)!=new.get(k))
summ={k:(old["summary"][k],new["summary"][k]) for k in new["summary"] if old["summary"].get(k)!=new["summary"][k]}
print("added sites:",len(added)); [print("  +",k,{x:new["sites"][k].get(x) for x in ("kind","addr_hex","offset_hex","size","source","confidence")}) for k in added]
print("removed sites:",removed); print("changed existing sites:",changed)
print("changed top-level keys:",top,{k:(old.get(k),new.get(k)) for k in top})
print("summary deltas:",summ)
ok=not removed and not changed and set(top)<={"adjudicated_bindings"} and len(added)==20
print("VERDICT:", "only intended entries changed" if ok else "UNEXPECTED CHANGE"); sys.exit(0 if ok else 1)
