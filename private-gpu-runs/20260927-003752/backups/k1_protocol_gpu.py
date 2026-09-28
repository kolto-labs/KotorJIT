#!/usr/bin/python3
"""Private protocol acceptance. No shipped artifact changes; root launches."""
import base64,fcntl,hashlib,json,os,re,shutil,subprocess,sys,time,traceback
from pathlib import Path
BASE=Path('/home/brunner56/kp-live-20260922')
CANDIDATE=Path('/home/brunner56/kp-console-protocol-20260927')
ROOT=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
from live_preflight import OwnedSession,source_receipt,pids_by_name
from gpu_display import GPUDisplay
class Session(GPUDisplay,OwnedSession):
    def stage(self,resources=None):
        super().stage(resources)
        for p in (self.game_dir/'kotorphasor/scripts').glob('*.lua'):p.unlink()
        table=self.game_dir/'kotorphasor/addresses';shutil.rmtree(table);table.mkdir()
        shutil.copy2(CANDIDATE/'source/data/addresses/k1_gog_103.json',table/'k1_gog_103.json')
        (self.run_dir/'protocol-provenance.json').write_text(json.dumps({'artifacts':{n:sha(self.game_dir/n) for n in ('kphasor.dll','binkw32.dll')},'exe_sha256':sha(self.game_dir/'swkotor.exe'),'table_sha256':sha(table/'k1_gog_103.json')},indent=2))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def decimal(v):
    assert isinstance(v,str) and re.fullmatch(r'0|[1-9][0-9]*',v) and int(v)<2**64,v
    return int(v)
def decode(b):
    assert b['encoding']=='base64'
    v=base64.b64decode(b['data'],validate=True);assert len(v)==decimal(b['byte_length']);return v

def main():
    assert os.environ.get('KP_PRIVATE_CONTROLLER_RUN'),'Use private_k1_protocol_controller.py'
    artifacts=json.loads((CANDIDATE/'build-artifacts.json').read_text());assert set(artifacts)=={'kphasor.dll','binkw32.dll'}
    for n,h in artifacts.items():assert sha(CANDIDATE/'build'/n)==h,n
    for n in ('swkotor.exe','swkotor2.exe','kotor2'):
        if pids_by_name(n):raise RuntimeError('Existing game process: '+n)
    os.environ['KOTOR1_DIR']='/home/brunner56/krayt/tmp/k1_harness'
    run=Path(os.environ['KP_PRIVATE_CONTROLLER_RUN']);code=2;result={'ok':False,'artifacts':artifacts}
    lock=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock')
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=source_receipt();(run/'source-before.json').write_text(json.dumps(before,indent=2))
        session=Session('k1',build_dir=str(CANDIDATE/'build'),staged=str(run/'k1-protocol-stage'),wineprefix=str(run/'k1-protocol-prefix'),reset_saves=True,boot_timeout=120,screen=(1024,768),log=print)
        try:
            ch=session.boot()
            for n,h in artifacts.items():assert sha(session.game_dir/n)==h
            ch.request('load_save',dir='000001 - AUTOSAVE',timeout=120)
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                world=ch.request('state');status=ch.request('status')
                if world.get('phase')=='gameplay' and world.get('phase_detail',{}).get('main_menu')==0 and status.get('vm_bound'):break
                time.sleep(.25)
            else:raise RuntimeError('Game did not reach gameplay/menu0/vmbound')
            result['world']=world
            def wire(op,**fields):
                response=ch.request('devtools',protocol='kp.console.v1',op=op,**fields)
                with (run/'protocol-wire.jsonl').open('a') as f:f.write(json.dumps({'op':op,'fields':fields,'result':response})+'\n')
                assert response['protocol']=='kp.console.v1'
                return response
            initial=wire('status');assert initial['status']=='Found'
            runtime=initial['runtime'];identity=initial['session'];assert runtime and decimal(identity)>0
            for n in ('submitted','completed','queued','last_line','dropped_lines','input_calls'):decimal(initial[n])
            def call(op,**fields):
                response=wire(op,runtime=runtime,session=identity,**fields)
                assert response['runtime']==runtime
                return response
            def outcome(request):
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    response=call('outcome',request=request);assert response['status']=='Found',response
                    o=response['outcome'];assert o['session']==identity and o['request']==request
                    for n in ('request','session','return_count','first_line','last_line'):decimal(o[n])
                    if o['state'] in ('Succeeded','Failed','Cancelled'):return o
                    time.sleep(.1)
                raise RuntimeError('Exact outcome timed out; never replayed')
            def submit(lua):
                reply=call('submit',code=lua);assert reply['status']=='None' and reply['session']==identity
                assert decimal(reply['request'])>0
                return outcome(reply['request'])
            # Legacy request and output retain numeric IDs/readable strings.
            legacy=ch.request('devtools',op='status');assert isinstance(legacy['submitted'],int) and 'protocol' not in legacy
            old=ch.request('devtools',op='submit',code='40+2');assert isinstance(old['request'],int)
            legacy_exact=outcome(str(old['request']));assert legacy_exact['values']==[{'type':'Number','kind':'Finite','value':42}]
            old_output=ch.request('devtools',op='output');assert any(x['request']==old['request'] and x['kind']=='result' and x['text']=='number: 42' for x in old_output['lines'])
            typed=submit('return nil,false,string.char(0,255,65),-1/math.huge,math.huge,-math.huge,0/0')
            assert typed['state']=='Succeeded' and typed['return_count']=='7' and not typed['returns_truncated']
            v=typed['values'];assert len(v)==7 and v[0]=={'type':'Nil'} and v[1]=={'type':'Boolean','value':False}
            assert v[2]['type']=='String' and decode(v[2]['bytes'])==b'\x00\xffA' and v[2]['original_bytes']=='3' and not v[2]['truncated']
            for item,kind in zip(v[3:],['NegativeZero','PositiveInfinity','NegativeInfinity','NaN']):assert item=={'type':'Number','kind':kind},item
            no_returns=submit('do end');assert no_returns['state']=='Succeeded' and no_returns['return_count']=='0' and no_returns['values']==[]
            failed=submit("error('protocol-error')");assert failed['state']=='Failed' and failed['error']['code'] and b'protocol-error' in decode(failed['error']['text'])
            recovered=submit('6*7');assert recovered['values']==[{'type':'Number','kind':'Finite','value':42}]
            assert call('cancel',request=recovered['request'])['status']=='AlreadyTerminal'
            baseline=call('status');counter=baseline['submitted']
            assert wire('submit',runtime=runtime+'stale',session=identity,code="error('must not run')")['status']=='StaleRuntime'
            assert wire('submit',runtime=runtime,session=str(decimal(identity)+1),code="error('must not run')")['status']=='StaleSession'
            assert call('outcome',request='9007199254740993')['status']=='Unavailable'
            assert call('status')['submitted']==counter
            completion=call('complete',prefix='math.sq');assert completion['status']=='Found' and b'math.sqrt' in [decode(x) for x in completion['names']]
            # Real F12 keyboard submission, correlated using versioned identity/outcome.
            tree=subprocess.check_output(['xwininfo','-root','-tree'],env=session.env,text=True)
            (run/'capture-windows.txt').write_text(tree)
            windows=re.findall(r'(0x[0-9a-fA-F]+) \"([^\"]*)\".*?(\d+)x(\d+)\+',tree)
            windows=[w for w in windows if w[1] and int(w[2])>=800 and int(w[3])>=600];assert windows
            window=max(windows,key=lambda w:int(w[2])*int(w[3]))[0]
            def key(*args):subprocess.run(['xdotool',*args],env=session.env,check=True,timeout=10)
            before_key=call('status');assert before_key['session']==identity
            key('windowfocus','--sync',window)
            if not before_key['open']:key('key','F12')
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                if call('status')['open']:break
                time.sleep(.1)
            else:raise RuntimeError('Physical F12 did not open')
            key('key','ctrl+a');key('type','--clearmodifiers','--delay','2','--','return "physical-v1",nil,false');key('key','Return')
            expected=str(decimal(before_key['submitted'])+1)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                now=call('status');assert now['session']==identity
                if decimal(now['submitted'])>=int(expected):break
                time.sleep(.1)
            else:raise RuntimeError('No physical submission')
            assert now['submitted']==expected
            physical=outcome(expected);assert physical['state']=='Succeeded' and physical['return_count']=='3'
            pv=physical['values'];assert decode(pv[0]['bytes'])==b'physical-v1' and pv[1]=={'type':'Nil'} and pv[2]=={'type':'Boolean','value':False}
            output=call('output',after_sequence=before_key['last_line']);assert output['status']=='Found'
            assert decimal(output['dropped_through'])<=decimal(before_key['last_line'])
            lines=[x for x in output['lines'] if x['session']==identity and x['request']==expected];assert lines
            for line in lines:decimal(line['sequence']);decode(line['text']);decode(line['kind'])
            assert any(decode(x['kind'])==b'input' for x in lines)
            assert any(decode(x['kind'])==b'result' for x in lines)
            subprocess.run(['ffmpeg','-nostdin','-y','-f','x11grab','-window_id',window,'-i',session.env['DISPLAY'],'-frames:v','1',str(run/'protocol-console.png')],env=session.env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,timeout=15)
            result.update(ok=True,typed=typed,no_returns=no_returns,error=failed,recovery=recovered,physical=physical,legacy=legacy_exact,runtime=runtime,session=identity,cancellation_scope='AlreadyTerminal only; no native running-cancel preemption claim');code=0
        except Exception as e:result['error_detail']=str(e);traceback.print_exc()
        finally:
            session.teardown();after=source_receipt();result['source_unchanged']=before==after
            (run/'source-after.json').write_text(json.dumps(after,indent=2))
            if before!=after:result['ok']=False;code=3
            (run/'protocol-result.json').write_text(json.dumps(result,indent=2))
        raise SystemExit(code)
if __name__=='__main__':main()
