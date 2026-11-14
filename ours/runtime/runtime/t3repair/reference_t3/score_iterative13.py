from score_t3 import evaluate as switch_eval
from score_stop_controls import evaluate as control_eval
def evaluate(directory,spec,rules):
    return control_eval(directory,spec,rules) if spec['category']=='stop_controls' else switch_eval(directory,spec,rules)
