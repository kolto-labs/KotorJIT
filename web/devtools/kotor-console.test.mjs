import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('evaluate preserves identity, String bytes and output correlation', async () => {
  const calls = [];
  const replies = [
    { protocol:'kp.console.v1', runtime:'r', status:'Found', session:'18446744073709551615', submitted:'4', last_line:'9' },
    { protocol:'kp.console.v1', runtime:'r', status:'None', session:'18446744073709551615', request:'18446744073709551615' },
    { protocol:'kp.console.v1', runtime:'r', status:'Found', outcome:{session:'18446744073709551615', request:'18446744073709551615', state:'Succeeded', values:[{type:'String', bytes:{encoding:'base64', data:'AP8A', byte_length:'3'}, original_bytes:'3', truncated:false}], error:null} },
    { protocol:'kp.console.v1', runtime:'r', status:'Found', session:'18446744073709551615', dropped_through:'9', lines:[{session:'18446744073709551615', request:'18446744073709551615', text:{encoding:'base64', data:'AP8A', byte_length:'3'}}, {session:'r-other', request:'18446744073709551615', text:{encoding:'base64', data:'AA==', byte_length:'1'}}] }
  ];
  globalThis.sessionStorage = {setItem(){}, getItem(){return 'token'}};
  globalThis.document = {querySelector(){return null}};
  globalThis.fetch = async (_url, init) => { calls.push(JSON.parse(init.body)); return {ok:true, async json(){return replies.shift()}}; };
  const source = await readFile(new URL('./kotor-console.mjs', import.meta.url), 'utf8');
  const mod = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  const result = await mod.evaluate('return 1');
  assert.equal(result.state, 'Succeeded');
  assert.deepEqual([...result.values[0].bytes], [0,255,0]);
  assert.equal(result.output.length, 1);
  assert.deepEqual(calls.map(x => x.op), ['status','submit','outcome','output']);
  assert.equal(calls[1].session, '18446744073709551615');
  assert.equal(calls[3].after_sequence, '9');
});

test('stale outcome rejects without replay', async () => {
  let n = 0;
  globalThis.sessionStorage = {setItem(){}, getItem(){return 'token'}};
  globalThis.document = {querySelector(){return null}};
  globalThis.fetch = async (_url, init) => { n++; const body = JSON.parse(init.body); const result = body.op === 'status' ? {protocol:'kp.console.v1',runtime:'r',status:'Found',session:'2',submitted:'0',last_line:'0'} : body.op === 'submit' ? {protocol:'kp.console.v1',runtime:'r',status:'None',session:'2',request:'1'} : {protocol:'kp.console.v1',runtime:'r',status:'StaleSession'}; return {ok:true,async json(){return result}}; };
  const source = await readFile(new URL('./kotor-console.mjs', import.meta.url), 'utf8');
  const mod = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  await assert.rejects(mod.evaluate('return 1'), /StaleSession/); assert.equal(n, 3);
});

test('wrong outcome identity and hung fetch are failures without replay', async () => {
  globalThis.sessionStorage = {setItem(){}, getItem(){return 'token'}};
  globalThis.document = {querySelector(){return null}};
  let calls = 0;
  globalThis.fetch = async (_url, init) => { calls++; const body = JSON.parse(init.body); const result = body.op === 'status' ? {protocol:'kp.console.v1',runtime:'r',status:'Found',session:'3',submitted:'0',last_line:'0'} : body.op === 'submit' ? {protocol:'kp.console.v1',runtime:'r',status:'None',session:'3',request:'9'} : {protocol:'kp.console.v1',runtime:'r',status:'Found',outcome:{session:'3',request:'8',state:'Succeeded',values:[],error:null}}; return {ok:true,async json(){return result}}; };
  const source = await readFile(new URL('./kotor-console.mjs', import.meta.url), 'utf8');
  const mod = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  await assert.rejects(mod.evaluate('return 1'), /request/); assert.equal(calls, 3);

  globalThis.fetch = (_url, init) => new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted'))));
  const mod2 = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  await assert.rejects(mod2.evaluate('return 1', {timeout: 10}), /aborted/);
});

test('Requested stays pending and failed errors retain native bytes', async () => {
  globalThis.sessionStorage = {setItem(){}, getItem(){return 'token'}};
  globalThis.document = {querySelector(){return null}};
  let outcomePoll = 0;
  let firstPoll;
  const polled = new Promise(resolve => { firstPoll = resolve; });
  globalThis.fetch = async (_url, init) => {
    const body = JSON.parse(init.body);
    let result;
    if (body.op === 'status') result = {protocol:'kp.console.v1',runtime:'r2',status:'Found',session:'4',submitted:'0',last_line:'0'};
    else if (body.op === 'submit') result = {protocol:'kp.console.v1',runtime:'r2',status:'None',session:'4',request:'4'};
    else if (body.op === 'cancel') result = {protocol:'kp.console.v1',runtime:'r2',status:'Requested'};
    else if (body.op === 'outcome') { firstPoll(); result = outcomePoll++ === 0 ? {protocol:'kp.console.v1',runtime:'r2',status:'Found',outcome:{session:'4',request:'4',state:'Running',values:[],error:null}} : {protocol:'kp.console.v1',runtime:'r2',status:'Found',outcome:{session:'4',request:'4',state:'Failed',values:[],error:{code:'lua_runtime',text:{encoding:'base64',data:'AP8=',byte_length:'2'},truncated:false}}}; }
    else result = {protocol:'kp.console.v1',runtime:'r2',status:'Found',session:'4',dropped_through:'0',lines:[]};
    return {ok:true,async json(){return result}};
  };
  const source = await readFile(new URL('./kotor-console.mjs', import.meta.url), 'utf8');
  const mod = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  let terminal = false;
  const pending = mod.evaluate('bad()', {poll:50}).then(result => { terminal=true; return result; });
  await polled;
  const cancellation = await mod.cancel({runtime:'r2',session:'4',request:'4'});
  assert.equal(cancellation.status, 'Requested');
  assert.equal(terminal, false);
  const result = await pending;
  assert.equal(result.state, 'Failed'); assert.equal(result.error.text.data, 'AP8='); assert.equal(outcomePoll, 2);
});


test('every response stays in the accepted runtime and output must be Found', async () => {
  const source = await readFile(new URL('./kotor-console.mjs', import.meta.url), 'utf8');
  for (const [op, change] of [
    ['submit', {runtime:'another-runtime'}],
    ['outcome', {runtime:'another-runtime'}],
    ['output', {runtime:'another-runtime',status:'StaleRuntime'}],
    ['output', {status:'Unavailable'}],
    ['output', {session:'99'}],
    ['outcome', {status:'Unavailable'}],
  ]) {
    globalThis.document = {querySelector(){return null}};
    globalThis.sessionStorage = {setItem(){},getItem(){return 'token'}};
    let submits = 0;
    globalThis.fetch = async (_url, init) => {
      const body=JSON.parse(init.body);
      const replies={
        status:{status:'Found',session:'1',last_line:'0'},
        submit:{status:'None',session:'1',request:'2'},
        outcome:{status:'Found',outcome:{session:'1',request:'2',state:'Succeeded',values:[]}},
        output:{status:'Found',session:'1',dropped_through:'0',lines:[]},
      };
      if(body.op==='submit') submits++;
      const result={protocol:'kp.console.v1',runtime:'r',...replies[body.op],...(body.op===op?change:{})};
      return {ok:true,async json(){return result}};
    };
    const mod=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
    await assert.rejects(mod.evaluate('1+1'), undefined, `${op} ${JSON.stringify(change)}`);
    assert.equal(submits,1);
  }
});


test('numeric, zero, noncanonical and overflowing identities are refused before submit', async () => {
  globalThis.document={querySelector(){return null}};
  globalThis.sessionStorage={setItem(){},getItem(){return 'token'}};
  const source=await readFile(new URL('./kotor-console.mjs',import.meta.url),'utf8');
  const mod=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
  for (const session of [9007199254740992, '0', '01', '18446744073709551616']) {
    let calls=0;
    globalThis.fetch=async()=>{calls++;return {ok:true,async json(){return {protocol:'kp.console.v1',runtime:'r',status:'Found',session,last_line:'0'}}}};
    await assert.rejects(mod.evaluate('mutate()'),/canonical/);
    assert.equal(calls,1);
  }
  await assert.rejects(mod.cancel(9007199254740992),/handle/);
});

test('1+1 returns the native typed Number 2', async () => {
  globalThis.document={querySelector(){return null}};
  globalThis.sessionStorage={setItem(){},getItem(){return 'token'}};
  globalThis.fetch=async(_url,init)=>{
    const op=JSON.parse(init.body).op;
    const replies={status:{status:'Found',session:'1',last_line:'0'},submit:{status:'None',session:'1',request:'1'},outcome:{status:'Found',outcome:{session:'1',request:'1',state:'Succeeded',values:[{type:'Number',kind:'Finite',value:2}],return_count:'1',returns_truncated:false}},output:{status:'Found',session:'1',lines:[],dropped_through:'0'}};
    return {ok:true,async json(){return {protocol:'kp.console.v1',runtime:'r',...replies[op]}}};
  };
  const source=await readFile(new URL('./kotor-console.mjs',import.meta.url),'utf8');
  const mod=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
  const result=await mod.evaluate('1+1');
  assert.deepEqual(result.values,[{type:'Number',kind:'Finite',value:2}]);
  assert.equal(result.return_count,'1');
  assert.equal(result.returns_truncated,false);
});

test('cancel retains the accepted request owner across baseline changes', async () => {
  globalThis.document={querySelector(){return null}};
  globalThis.sessionStorage={setItem(){},getItem(){return 'token'}};
  let currentSession='1';
  const cancels=[];
  globalThis.fetch=async(_url,init)=>{
    const body=JSON.parse(init.body);
    if(body.op==='cancel') cancels.push(body);
    const replies={status:{status:'Found',session:currentSession,last_line:'0'},submit:{status:'None',session:currentSession,request:'1'},outcome:{status:'Found',outcome:{session:currentSession,request:'1',state:'Succeeded',values:[]}},output:{status:'Found',session:currentSession,lines:[],dropped_through:'0'},complete:{status:'Found',names:[]},cancel:{status:'AlreadyTerminal'}};
    return {ok:true,async json(){return {protocol:'kp.console.v1',runtime:'r',...replies[body.op]}}};
  };
  const source=await readFile(new URL('./kotor-console.mjs',import.meta.url),'utf8');
  const mod=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64')+'#cancel-owner');
  const first=await mod.evaluate('1');
  currentSession='2';
  await mod.complete('kp.');
  await mod.cancel(first);
  assert.equal(cancels[0].session,'1');
  await mod.evaluate('2');
  await assert.rejects(mod.cancel('1'),/handle/);
  await mod.cancel(first);
  assert.equal(cancels[1].session,'1');
  assert.equal(cancels[1].request,'1');
  assert.equal(cancels.length,2);
});
