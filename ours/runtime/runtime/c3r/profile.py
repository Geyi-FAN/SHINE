"""Explicit feature switches; never inherit an unrelated research experiment."""
import os

FLAGS = {
    'RULE_FIRST_VERIFIER_ENABLED': '1', 'CAP_REFERENCE_CONTRACT': '1',
    'CAP_STAGE_LIFECYCLE_GUARD': '1', 'CAP_RETURN_RELEASE_REVIEW': '1',
    'CAP_PROGRESS_V2': '1', 'CAP_CONDITION_V3': '1',
    'CAP_RECOVERY_POLICY_V4': '1', 'CAP_RECOVERY_REENTRY': '1',
    'CAP_VERTICAL_APPROACH': '1', 'CAP_VECTOR_GEOMETRY': '1',
    'CAP_VERIFIER_PREFLIGHT': '0', 'CAP_VERIFIER_PERIODIC_ONE': '0',
    'CAP_DRAWER_TARGET_SCOPE': '0', 'CAP_OPEN_NEGATIVE_PREFLIGHT': '0',
}

def configure():
    profile = os.environ.get('C3R_PROFILE', 'core')
    if profile not in ('core', 'recovery'):
        raise ValueError('C3R_PROFILE must be core or recovery')
    os.environ['C3R_PROFILE'] = profile
    values = dict(FLAGS, CAP_RECOVERY_ENABLED='1' if profile == 'recovery' else '0')
    os.environ.update(values)
    return dict(profile=profile, features=values)
