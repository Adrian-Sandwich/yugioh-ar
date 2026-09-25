"""Isolated stdio MCP handshake; closes only the child process it starts."""
import json
import queue
import subprocess
import threading
from pathlib import Path

exe = 'C:/Users/Adrian/AppData/Local/Programs/codebase-memory-mcp/codebase-memory-mcp.exe'
out = Path(__file__).resolve().parent / 'qa/cbm-diagnostic'
out.mkdir(parents=True, exist_ok=True)
messages = queue.Queue()
with (out/'stderr.log').open('w', encoding='utf-8') as stderr:
    process = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=stderr, text=True, encoding='utf-8',
                               creationflags=subprocess.CREATE_NO_WINDOW)
    def read():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except json.JSONDecodeError:
                messages.put({'unexpected_stdout': line[:300]})
        messages.put({'closed': process.poll()})
    threading.Thread(target=read, daemon=True).start()
    def send(payload):
        process.stdin.write(json.dumps(payload)+'\n')
        process.stdin.flush()
    def response(identifier):
        for _ in range(30):
            value = messages.get(timeout=30)
            if value.get('id') == identifier:
                return value
            if 'closed' in value or 'unexpected_stdout' in value:
                raise RuntimeError(value)
        raise RuntimeError('Too many unrelated messages')
    try:
        send({'jsonrpc':'2.0', 'id':1, 'method':'initialize', 'params':{
            'protocolVersion':'2024-11-05', 'capabilities':{},
            'clientInfo':{'name':'local-diagnostic','version':'1'}}})
        initialized = response(1)
        assert 'result' in initialized, initialized
        send({'jsonrpc':'2.0','method':'notifications/initialized'})
        send({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{
            'name':'list_projects','arguments':{'limit':10}}})
        projects = response(2)
        assert 'result' in projects and not projects['result'].get('isError'), projects
        result = {'status':'passed','initialize':initialized,'list_projects':projects}
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
