/** A literal current-user object slot, not a physical-state invariant or plan. */
export function explicitObjectSelection(text) {
    const match = /^\s*keep\s+((?:the\s+)?(?:cream cheese|wine bottle|cheese|bottle|bowl|plate))\s+as\s+(?:the\s+)?(?:object|item)\s*[,;.!]\s*(?:but\s+)?((?:please\s+)?(?:put|place|move)\s+(it|(?:the\s+)?(?:cream cheese|wine bottle|cheese|bottle|bowl|plate))\s+(?:on top of|onto|on|into|inside|in|to)\b[\s\S]+)$/i.exec(text);
    if (!match)
        return undefined;
    const canonical = noun => noun.toLowerCase().replace(/^the\s+/, '').replace(/^wine bottle$/, 'bottle').replace(/^cream cheese$/, 'cheese');
    if (match[3].toLowerCase() !== 'it' && canonical(match[3]) !== canonical(match[1]))
        return undefined;
    return { objectText: match[1], groundingText: match[2].replace(/\b((?:put|place|move)\s+)it\b/i, (_whole, verb) => verb + match[1]) };
}
