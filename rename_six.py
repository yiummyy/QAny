import re

filepath = r'c:\Q\Projects\QAny\QAny产研总结手册.md'

with open(filepath, 'r', encoding='utf-8') as f:
    raw = f.read()

# Rename 10.x -> 6.x under 六 chapter
# Target only within six: between # 六、评测体系 and # 七、成本管理
six_start = raw.index('# 六、评测体系')
seven_start = raw.index('# 七、成本管理')
before = raw[:six_start]
six_chunk = raw[six_start:seven_start]
after = raw[seven_start:]

renames = [
    ('### 10.1 Golden Examples', '### 6.1 Golden Examples'),
    ('### 10.2 评测框架', '### 6.2 评测框架'),
    ('### 10.3 离线评测指标', '### 6.3 离线评测指标'),
    ('### 10.4 在线评估体系', '### 6.4 在线评估体系'),
    ('### 10.5 评估工程设施', '### 6.5 评估工程设施'),
]

for old, new in renames:
    six_chunk = six_chunk.replace(old, new)

raw = before + six_chunk + after

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(raw)

print('Done')
