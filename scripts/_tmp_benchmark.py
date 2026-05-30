"""Benchmark: simulate Kilo request with new reduced config."""
import requests, os, time, json

os.chdir('/Users/mkoziol/projects/bet')

# Build system prompt as Kilo would (global + agent-specific instructions + prompt)
system_parts = []
for f in [
    '.github/instructions/agent-execution-protocol.instructions.md',
    '.kilocode/rules/tool-names.md',
    '.github/instructions/betting-artifacts.instructions.md',
    '.kilo/prompts/bet-orchestrator.md',
]:
    system_parts.append(open(f).read())

system = '\n---\n'.join(system_parts)

# Simulate 25 tools (Kilo sends all MCP + built-in tools)
tools = []
# SQLite MCP (6 tools)
for name, desc in [('sqlite_read_query','Execute read-only SQL query'),('sqlite_write_query','Execute write SQL'),('sqlite_list_tables','List all tables'),('sqlite_describe_table','Describe table schema'),('sqlite_create_table','Create table'),('sqlite_append_insight','Append insight')]:
    tools.append({'type':'function','function':{'name':name,'description':desc,'parameters':{'type':'object','properties':{'query':{'type':'string','description':'SQL query or table name'}}}}})
# Sequential thinking (1 tool)
tools.append({'type':'function','function':{'name':'sequentialthinking_sequentialthinking','description':'A tool for dynamic and reflective problem-solving through sequential thinking.','parameters':{'type':'object','properties':{'thought':{'type':'string','description':'Your current thinking step'},'thoughtNumber':{'type':'integer','description':'Current thought number'},'totalThoughts':{'type':'integer','description':'Estimated total'},'nextThoughtNeeded':{'type':'boolean','description':'Whether another thought step is needed'}},'required':['thought','thoughtNumber','totalThoughts','nextThoughtNeeded']}}})
# Brave search (5 tools)
for name, desc in [('brave_web_search','Search the web using Brave Search'),('brave_news_search','Search news articles'),('brave_image_search','Search images'),('brave_video_search','Search videos'),('brave_local_search','Search local businesses')]:
    tools.append({'type':'function','function':{'name':name,'description':desc,'parameters':{'type':'object','properties':{'query':{'type':'string','description':'Search query'},'count':{'type':'integer','description':'Number of results'}}}}})
# Built-in Kilo tools (13 tools)
builtins = [
    ('read','Read file contents',{'path':{'type':'string'},'startLine':{'type':'integer'},'endLine':{'type':'integer'}}),
    ('write','Write content to file',{'path':{'type':'string'},'content':{'type':'string'}}),
    ('edit','Edit file with search/replace',{'path':{'type':'string'},'search':{'type':'string'},'replace':{'type':'string'}}),
    ('bash','Execute shell command',{'command':{'type':'string'},'timeout':{'type':'integer'}}),
    ('glob','Search files by pattern',{'pattern':{'type':'string'},'path':{'type':'string'}}),
    ('grep','Search file contents',{'pattern':{'type':'string'},'path':{'type':'string'},'isRegex':{'type':'boolean'}}),
    ('webfetch','Fetch URL content',{'url':{'type':'string'},'selector':{'type':'string'}}),
    ('task','Delegate to another agent',{'agent':{'type':'string'},'message':{'type':'string'}}),
    ('todowrite','Write todo items',{'items':{'type':'array'}}),
    ('todoretrieve','Get todo list',{}),
    ('kilo_local_recall','Recall from memory',{'query':{'type':'string'}}),
    ('kilo_local_store','Store to memory',{'key':{'type':'string'},'value':{'type':'string'}}),
    ('websearch','Web search (alias)',{'query':{'type':'string'},'count':{'type':'integer'}}),
]
for name, desc, props in builtins:
    tools.append({'type':'function','function':{'name':name,'description':desc,'parameters':{'type':'object','properties':props}}})

print(f'System prompt: {len(system):,} chars')
print(f'Tools: {len(tools)}')
print(f'Estimated tokens (chars/1.5): ~{len(system)*2//3:,}')
print()

payload = {
    'model': 'default',
    'messages': [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': "Check today's database readiness. Use sequentialthinking to plan what tables to check, then query sqlite for: (1) fixture count for today, (2) team_form row count. Report findings."}
    ],
    'tools': tools,
    'max_tokens': 50,
    'temperature': 0.3,
    'stream': False
}

print(f'Sending request...')
t0 = time.time()
r = requests.post('http://localhost:8000/v1/chat/completions', json=payload, timeout=300)
elapsed = time.time() - t0

if r.status_code == 200:
    data = r.json()
    pt = data['usage']['prompt_tokens']
    ct = data['usage']['completion_tokens']
    print(f'✓ Prompt tokens: {pt:,}')
    print(f'✓ Completion tokens: {ct}')
    print(f'✓ Total time: {elapsed:.1f}s')
    print(f'✓ Prefill speed: {pt/elapsed:.0f} tok/s')
    print(f'✓ Content: {data["choices"][0]["message"].get("content","")[:200]}')
    tc = data["choices"][0]["message"].get("tool_calls")
    if tc:
        print(f'✓ Tool calls: {[t["function"]["name"] for t in tc]}')
else:
    print(f'✗ Error {r.status_code}: {r.text[:500]}')
