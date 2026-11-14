import json
from pathlib import Path

def load_execution_policy(path=None):
    path=Path(path) if path else Path(__file__).with_name('configs')/'continue_v1.json'
    value=json.loads(path.read_text())
    a,b=value['preparation_budget_numerator'],value['preparation_budget_denominator']
    if not isinstance(a,int) or not isinstance(b,int) or not 0<a<b:
        raise ValueError('Preparation budget must leave a positive target budget')
    if set(value['stage_max_steps'])!={'return','close','open_top','grasp'}:
        raise ValueError('Unknown execution stage caps')
    if any(type(n) is not int or n<=0 for n in value['stage_max_steps'].values()):
        raise ValueError('Stage caps must be positive control-step counts')
    return value
