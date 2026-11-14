"""Controller-side terminal release guard, independent of scoring results."""


def stable_final_release(rows, steps=40):
    window=list(rows)[-steps:]
    return (len(window)==steps and all(not r['target_contact'] for r in window)
            and all(r['support_contact'] for r in window))
