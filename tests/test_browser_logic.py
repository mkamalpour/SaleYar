"""Read-only polling retries use actual frontend code, with no HTTP requests."""
import json
from pathlib import Path
import shutil
import subprocess
import pytest


@pytest.mark.parametrize("scenario", ["recover", "unauthorized", "cancelled", "bounded"])
def test_polling_retries_only_transient_reads(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Optional Node runtime unavailable for frontend unit checks")
    source = (Path(__file__).resolve().parents[1] / "ui/assets/owner.js").read_text(encoding="utf-8")
    function = source[source.index("async function readAnalysisStatus"):source.index("async function uploadAndAnalyze")]
    code = """
const assert = require('node:assert/strict');
const scenario = SCENARIO;
let calls=[], waits=[];
const signal={aborted:scenario==='cancelled'};
const t=(text)=>text; const status=()=>{};
const pause=async(ms)=>{waits.push(ms);};
const request=async(path,options,sig)=>{
 calls.push({path,options}); assert.equal(sig,signal);
 if(scenario==='recover' && calls.length===2) return {status:'done'};
 if(scenario==='unauthorized'){const e=new Error('Unauthorized');e.status=401;throw e;}
 throw new TypeError('simulated lost connection');
};
FUNCTION
(async()=>{
 if(scenario==='recover'){
  assert.equal((await readAnalysisStatus('existing/job',signal)).status,'done');
  assert.equal(calls.length,2);assert.equal(waits.length,1);
 }else{
  await assert.rejects(()=>readAnalysisStatus('existing/job',signal));
  assert.equal(calls.length,scenario==='bounded'?3:1);
  assert.equal(waits.length,scenario==='bounded'?2:0);
 }
 assert.ok(calls.every(c=>c.path==='/result/existing%2Fjob' && !c.options.method));
})().catch(e=>{console.error(e);process.exitCode=1;});
""".replace("SCENARIO", json.dumps(scenario)).replace("FUNCTION", function)
    result = subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
