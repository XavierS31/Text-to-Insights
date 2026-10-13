import pandas as pd
import json

d1 = pd.read_csv('converted.csv')
d1.columns = d1.columns.str.strip()

d2 = pd.read_csv('other.csv')
d2.columns = d2.columns.str.strip()

d1.reset_index(drop=True, inplace=True)
d2.reset_index(drop=True, inplace=True)

max_len = max(len(d1), len(d2))
d1 = d1.reindex(range(max_len))
d2 = d2.reindex(range(max_len))

d3 = pd.concat([d1, d2], axis=1)

cols = [c for c in d3.columns if not c.startswith('file_path')]
d3 = d3[cols]

out_file = 'merged_output.jsonl'

with open(out_file, 'w', encoding='utf-8') as f:
    for i, row in d3.iterrows():
        d4 = row.to_dict()
        last_col = d3.columns[-1]
        d5 = d4.pop(last_col, None)
        d6 = d4
        line = json.dumps({
            "input": d5,
            "output": d6
        }, ensure_ascii=False)
        f.write(line + '\n')
