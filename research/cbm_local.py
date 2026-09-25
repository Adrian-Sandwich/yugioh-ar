"""Call the installed Codebase Memory CLI with JSON preserved on Windows."""
import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('tool', choices=['list_projects', 'index_repository', 'index_status',
    'get_architecture', 'search_graph', 'trace_path', 'check_index_coverage', 'get_code_snippet'])
parser.add_argument('arguments', type=Path)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
payload = json.loads(args.arguments.read_text(encoding='utf-8'))
exe = 'C:/Users/Adrian/AppData/Local/Programs/codebase-memory-mcp/codebase-memory-mcp.exe'
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open('w', encoding='utf-8') as output:
    result = subprocess.run([exe, 'cli', '--json', args.tool, '--args-file', str(args.arguments.resolve())],
        stdout=output, creationflags=subprocess.CREATE_NO_WINDOW)
print(f'Exit {result.returncode}; response: {args.output}')
raise SystemExit(result.returncode)
