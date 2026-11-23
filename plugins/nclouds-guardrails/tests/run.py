import json, subprocess, os, shutil, sys, tempfile
G=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','hooks','guard.py')
HOME=tempfile.mkdtemp(prefix='guardrails-test-')
fails=0
def run(mode, data, sid='s1'):
    env=dict(os.environ, HOME=HOME); env.pop('CLAUDE_CODE_REMOTE',None)
    if isinstance(data,dict): data=dict(data, session_id=sid)
    r=subprocess.run([sys.executable,G,mode],input=json.dumps(data) if not isinstance(data,str) else data,capture_output=True,text=True,env=env)
    return r.returncode, r.stdout
def pre(tool, tin, sid='s1'): return run('pre', {'tool_name':tool,'tool_input':tin}, sid)
def expect(name, res, want):
    global fails
    rc,out=res
    got='deny' if '"deny"' in out else 'allow'
    ok=rc==0 and got==want[0] and (len(want)<2 or want[1] in out)
    if not ok: fails+=1
    print(('PASS' if ok else 'FAIL'), name, '->', got, ('' if ok else out[:300]))
# sends
expect('gmail send, no approval', pre('mcp__Gmail__send_message',{'to':'a@b.c'}), ('deny','typed approval'))
expect('gmail reply, no approval', pre('mcp__Gmail__reply',{}), ('deny','typed approval'))
expect('gmail draft', pre('mcp__Gmail__create_draft',{}), ('allow',))
expect('gmail read', pre('mcp__Gmail__search_threads',{'query':'x'}), ('allow',))
expect('slack send, no approval', pre('mcp__Slack__slack_send_message',{'channel_id':'C1','message':'hi'}), ('deny','typed approval'))
expect('slack draft', pre('mcp__Slack__slack_send_message_draft',{'channel_id':'C1','message':'hi'}), ('allow',))
run('prompt', {'prompt':"draft it but don't send it yet"})
expect('negated approval does not count', pre('mcp__Gmail__send_message',{}), ('deny','typed approval'))
run('prompt', {'prompt':"Looks good. Send it."})
expect('typed approval this turn', pre('mcp__Gmail__send_message',{}), ('allow',))
expect('approval covers slack too', pre('mcp__Slack__slack_send_message',{'channel_id':'C1','message':'x'}), ('allow',))
run('prompt', {'prompt':"thanks"})
expect('approval gone next turn', pre('mcp__Gmail__send_message',{}), ('deny','typed approval'))
expect('other session has no approval', pre('mcp__Gmail__send_message',{}, sid='s2'), ('deny','typed approval'))
# drive
C='mcp__Google_Drive__create_file'
expect('drive create, parent unread', pre(C, {'title':'SOW.docx','parentId':'1AbC'}), ('deny','1AbC'))
pre('mcp__Google_Drive__search_files', {'query':"parentId = '1AbC'"})
expect('drive create after listing', pre(C, {'title':'SOW.docx','parentId':'1AbC'}), ('allow',))
expect('drive create, no parent given', pre(C, {'title':'notes'}), ('allow',))
expect('drive update, file unread', pre('mcp__Google_Drive__update_file', {'fileId':'9Zz','title':'x'}), ('deny','9Zz'))
pre('mcp__Google_Drive__get_file_metadata', {'fileId':'9Zz'})
expect('drive update after read', pre('mcp__Google_Drive__update_file', {'fileId':'9Zz','title':'x'}), ('allow',))
expect('drive read never blocked', pre('mcp__Google_Drive__read_file_content', {'fileId':'new1'}), ('allow',))
expect('calendar untouched', pre('mcp__Google_Calendar__create_event', {'summary':'x'}), ('allow',))
# rocketlane
R='mcp__Rocketlane__create_task'
T={'rationale':'r','task_data':{'taskName':'A - B','project':{'projectId':4412}}}
expect('rocketlane create, project unread', pre(R, T), ('deny','4412'))
pre('mcp__Rocketlane__get_tasks', {'rationale':'r','params':{'includeFields':['taskName'],'filter':{'projectId':44123}}})
expect('rocketlane id is not a prefix match', pre(R, T), ('deny','4412'))
pre('mcp__Rocketlane__get_tasks', {'rationale':'r','params':{'includeFields':['taskName'],'filter':{'projectId':4412}}})
expect('rocketlane create after read', pre(R, T), ('allow',))
# everything else, and failure
expect('unrelated tool', pre('mcp__Krisp__search_meetings',{'q':'x'}), ('allow',))
expect('garbage stdin', run('pre','not json'), ('allow',))
expect('missing fields', run('pre',{}), ('allow',))
expect('tool_input wrong type', run('pre',{'tool_name':C,'tool_input':'x'}), ('allow',))
shutil.rmtree(HOME, ignore_errors=True)
print('FAILS', fails)
sys.exit(1 if fails else 0)
