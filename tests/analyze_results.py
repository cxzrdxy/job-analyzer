"""分析批量压测结果."""
import json

data = json.load(open('tests/output/batch30/batch_detail.json', encoding='utf-8'))

print('=' * 60)
print('失败明细')
print('=' * 60)
failed = [d for d in data if d['status'] == 'failed']
for d in failed:
    print(f"  {d['case_id']}: {d['error']}")

print()
print('=' * 60)
print('最佳匹配 top 5')
print('=' * 60)
passed = [d for d in data if d['status'] == 'passed' and d['overall_score'] is not None]
for d in sorted(passed, key=lambda x: -x['overall_score'])[:5]:
    print(f"  {d['resume_id']:<14} -> {d['job_title']:<32}: {d['overall_score']}")

print()
print('=' * 60)
print('同岗位匹配全部')
print('=' * 60)
same = [d for d in data if d['is_same_field'] and d['status'] == 'passed']
for d in sorted(same, key=lambda x: -x['overall_score']):
    print(f"  {d['resume_id']:<14} -> {d['job_title']:<32}: {d['overall_score']}")

print()
print('=' * 60)
print('后端简历 vs 不同 JD 类目平均分')
print('=' * 60)
from collections import defaultdict
backend_groups = defaultdict(list)
for d in passed:
    if d['resume_id'].startswith('backend'):
        backend_groups[d['job_category']].append(d['overall_score'])

for cat, scores in sorted(backend_groups.items(), key=lambda x: -sum(x[1])/len(x[1])):
    print(f"  vs {cat:<22}: avg={sum(scores)/len(scores):.1f}, n={len(scores)}")