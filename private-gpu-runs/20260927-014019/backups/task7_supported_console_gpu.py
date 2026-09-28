#!/usr/bin/python3
"""Production physical-console live proof. Root dispatch only; no submit fallback."""
import fcntl,hashlib,json,os,subprocess,time,traceback
from pathlib import Path
from k1_protocol_gpu import Session,CANDIDATE,source_receipt,pids_by_name,sha
from kpharness.session import GameSession
from kpharness.physical_console import PhysicalConsoleDriver,ChannelConsoleProtocolPort,thaw_receipt
from kpharness.owned_x11 import OwnedX11Input
from kpharness.console_protocol import decode_bytes
import kpharness.console_protocol as protocol_module
import kpharness.physical_console as physical_module
import kpharness.owned_x11 as input_module
import kpharness.console_steps as steps_module
import kpharness.session as session_module
BASE=Path('/home/brunner56/kp-live-20260922')
class ObservedChannel:
    def __init__(self,ch,path):self.ch=ch;self.path=path
    def request(self,cmd,**fields):
        assert cmd=='devtools' and fields.get('protocol')=='kp.console.v1'
        assert fields.get('op') in ('status','outcome','output'),'Physical route cannot submit or mutate via wire'
        response=self.ch.request(cmd,**fields)
        with self.path.open('a') as out:out.write(json.dumps({'request':{'cmd':cmd,**fields},'response':response})+'\n')
        return response

def main():
    assert os.environ.get('KP_PRIVATE_CONTROLLER_RUN') and os.environ.get('KP_PRIVATE_HARNESS_SNAPSHOT'),'Frozen snapshot and owned wrapper required'
    run=Path(os.environ['KP_PRIVATE_CONTROLLER_RUN'])
    artifacts=json.loads((CANDIDATE/'build-artifacts.json').read_text());assert set(artifacts)=={'kphasor.dll','binkw32.dll'}
    for n,h in artifacts.items():assert sha(CANDIDATE/'build'/n)==h
    for n in ('swkotor.exe','swkotor2.exe','kotor2'):
        if pids_by_name(n):raise RuntimeError('Existing game process: '+n)
    assert Session.capture_owned_game_window is GameSession.capture_owned_game_window,'Must use production capture unchanged'
    loaded={Path(m.__file__).name:sha(Path(m.__file__)) for m in (protocol_module,physical_module,input_module,steps_module,session_module)}
    (run/'production-module-hashes.json').write_text(json.dumps(loaded,indent=2))
    os.environ['KOTOR1_DIR']='/home/brunner56/krayt/tmp/k1_harness'
    lock=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock')
    result={'ok':False,'artifacts':artifacts,'production_modules':loaded};code=2
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=source_receipt();(run/'source-before.json').write_text(json.dumps(before,indent=2))
        session=Session('k1',build_dir=str(CANDIDATE/'build'),staged=str(run/'supported-k1-stage'),wineprefix=str(run/'supported-k1-prefix'),reset_saves=True,boot_timeout=120,screen=(1024,768),log=print)
        try:
            ch=session.boot()
            for n,h in artifacts.items():assert sha(session.game_dir/n)==h
            ch.request('load_save',dir='000001 - AUTOSAVE',timeout=120)
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                state=ch.request('state');status=ch.request('status')
                if state.get('phase')=='gameplay' and state.get('phase_detail',{}).get('main_menu')==0 and status.get('vm_bound'):break
                time.sleep(.25)
            else:raise RuntimeError('Gameplay/menu0/VM readiness not established')
            window=session.capture_owned_game_window()
            pid=int(subprocess.check_output(['xdotool','getwindowpid',window],env=session.env,text=True,timeout=5).strip())
            geometry=subprocess.check_output(['xdotool','getwindowgeometry','--shell',window],env=session.env,text=True,timeout=5)
            assert pid in session.game_pids() and pid==session._capture_window_pid
            result['owned_window']={'window':window,'pid':pid,'geometry':geometry,'display':session.env['DISPLAY'],'display_owner_pid':session.xvfb.pid,'owned_game_pids':session.game_pids()}
            port=ChannelConsoleProtocolPort(ObservedChannel(ch,run/'supported-wire.jsonl'))
            input_port=OwnedX11Input.from_session(session)
            driver=PhysicalConsoleDriver(port,input_port.console_entry())
            baseline=port.status();assert baseline['status']=='Found'
            source='return "supported-physical",nil,false,42'
            receipt=driver.execute(source,timeout=30,input_evidence=(source,),result_evidence=('supported-physical','nil','false','42'))
            after_input=port.status(runtime=receipt.identity.runtime)
            assert after_input['status']=='Found' and after_input['open'] is True
            assert baseline['runtime']==receipt.identity.runtime==after_input['runtime'] and baseline['session']==receipt.identity.session==after_input['session']
            assert receipt.identity.submitted==baseline['submitted']
            assert int(receipt.request)==int(baseline['submitted'])+1 and after_input['submitted']==receipt.request
            delta=int(after_input['input_calls'])-int(baseline['input_calls']);assert delta>0
            outcome=thaw_receipt(receipt.outcome);values=outcome['values']
            assert outcome['state']=='Succeeded' and outcome['request']==receipt.request and outcome['session']==receipt.identity.session and outcome['return_count']=='4' and not outcome['returns_truncated']
            assert len(values)==4 and values[0]['type']=='String' and decode_bytes(values[0]['bytes'])==b'supported-physical'
            assert values[1:]==[{'type':'Nil'},{'type':'Boolean','value':False},{'type':'Number','kind':'Finite','value':42}]
            lines=thaw_receipt(receipt.lines);out=port.output(receipt.identity.runtime,receipt.identity.session,receipt.identity.last_line)
            assert out['status']=='Found' and int(out['dropped_through'])<=int(receipt.identity.last_line)
            input_rows=[x for x in lines if decode_bytes(x['kind'])==b'input'];result_rows=[x for x in lines if decode_bytes(x['kind'])==b'result']
            assert input_rows and result_rows and set(x['sequence'] for x in input_rows).isdisjoint(x['sequence'] for x in result_rows)
            assert all(x['session']==receipt.identity.session and x['request']==receipt.request for x in lines)
            assert len({x['sequence'] for x in lines})==len(lines)
            assert session.capture_owned_game_window()==window
            subprocess.run(['ffmpeg','-nostdin','-y','-f','x11grab','-window_id',window,'-i',session.env['DISPLAY'],'-frames:v','1',str(run/'supported-console.png')],env=session.env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,timeout=15)
            result.update(ok=True,baseline=baseline,after_input=after_input,input_calls_delta=delta,identity=receipt.identity.__dict__,request=receipt.request,outcome=outcome,lines=lines,output=out,screenshot_sha256=sha(run/'supported-console.png'),game_state=state)
            code=0
        except Exception as e:
            result.update(error=f'{type(e).__name__}: {e}',failure_code=getattr(e,'code',None),last=thaw_receipt(getattr(e,'last',None)))
            if getattr(e,'baseline',None):result['failure_baseline']=e.baseline.__dict__
            traceback.print_exc()
        finally:
            owned=session.game_pids();display_pid=session.xvfb.pid if session.xvfb else None
            session.teardown()
            after=source_receipt();result['originals_unchanged']=before==after
            (run/'source-after.json').write_text(json.dumps(after,indent=2))
            remaining=session.game_pids();result['owned_game_pids_before_teardown']=owned;result['remaining_owned_game_pids']=remaining
            result['display_parent_reaped']=session.xvfb is None or session.xvfb.poll() is not None
            result['display_owner_pid']=display_pid
            if before!=after or remaining or not result['display_parent_reaped']:result['ok']=False;code=3
            (run/'supported-result.json').write_text(json.dumps(result,indent=2))
        raise SystemExit(code)
if __name__=='__main__':main()
