import sys; sys.path.insert(0,'.'); sys.path.insert(0,'../../backend')
import baseline_current as B
from dev_questions import DEV
from insightflow.orchestrator import Orchestrator
cur=None
only=set(sys.argv[1:])
for db,qid,fam,q,kind,sql in DEV:
    if only and qid not in only: continue
    if db!=cur: B.register(db); cur=db
    r=Orchestrator().ask(q)
    if kind!="clarify" and r.decision.action in("ANSWER","WARN"): continue
    print(qid,q,'->',r.decision.action,'|',r.decision.reason[:170],'|',(r.sql or '')[:110])
