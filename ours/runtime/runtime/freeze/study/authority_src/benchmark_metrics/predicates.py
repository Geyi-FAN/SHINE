"""Pure physical predicates. No temporal state, file access or task-ID exceptions."""
import math

def distance(a, b):
    if len(a) != 3 or len(b) != 3: raise ValueError('Expected 3D coordinates')
    if not all(math.isfinite(x) for x in list(a) + list(b)): raise ValueError('Non-finite position')
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))

def drawer_gap(q):
    if isinstance(q,bool) or not math.isfinite(q): raise ValueError('Non-finite joint coordinate')
    return max(0.0, -q)

def region_contains(evidence, margins):
    """Frozen LIBERO uses strict local bounds and optional parent contact.

    local_position must be the original body origin transformed by the native
    site's matrix, not a visual centroid. Parent contact is not implied by support.
    """
    p, lo, hi = (evidence[k] for k in ('local_position', 'lower', 'upper'))
    if any(len(v) != 3 for v in (p, lo, hi, margins)): raise ValueError('Expected 3D bounds')
    if not all(math.isfinite(v) for row in (p,lo,hi,margins) for v in row): raise ValueError('Non-finite geometry')
    inside = all(l-m < x < h+m for x,l,h,m in zip(p,lo,hi,margins))
    return inside and (not evidence['parent_contact_required'] or evidence['parent_contact'])

def all_last(values, count):
    return len(values) >= count and all(values[-count:])

def stable(positions, diameter):
    return max(distance(a,b) for a in positions for b in positions) <= diameter
