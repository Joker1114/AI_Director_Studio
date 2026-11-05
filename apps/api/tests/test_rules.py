from app.contracts import SpatialConstraint, StateFact
from app.services.spatial import validate_rules


def r(kind,subject,relation,value,target=''):
    return SpatialConstraint(type=kind,subject=subject,relation=relation,value=value,target=target)


def test_locked_side_conflict_and_bad_scale():
    output=validate_rules([
        r('screen_side','公交站','screen_side','right'),
        r('screen_side','公交站','screen_side','left'),
        r('scale','男人','height_fraction','1.4'),
        r('contact','男人.右手','grips','保持接触'),
    ],[])
    assert {x['code'] for x in output}=={'SC01','SC05','SC06'}


def test_transition_checks():
    output=validate_rules(
        [r('screen_side','公交站','screen_side','left')],
        [StateFact(subject='女孩',attribute='pose',value='standing')],
        [StateFact(subject='女孩',attribute='pose',value='sitting')],
        [r('screen_side','公交站','screen_side','right')],
        transition='eyeline_match'
    )
    assert {x['code'] for x in output}=={'SC02','SC04'}
    assert validate_rules([], [StateFact(subject='女孩',attribute='pose',value='standing')],
                          [StateFact(subject='女孩',attribute='pose',value='sitting')], transition='time_jump')==[]
