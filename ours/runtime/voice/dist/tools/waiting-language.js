function englishWaitingCandidate(raw) {
  const text = raw.trim().replace(/[’‘]/g, "'");
  if (/[?？"“”「」]|\b(?:if|suppose|unless|not|never|don't|do not|right now|immediately)\b/i.test(text)) return;
  const action = /^(?:then\s+)?(?:please\s+)?(?:put|place|move|push|open|close|return|turn|pick|grab)\b/i;
  const done = /^(?:(?:this|the current|current|the|that)\s+task\s+(?:is\s+)?(?:finishes|completes|finished|completed|done)|(?:this|that)(?:'s| is| has been)\s+(?:done|finished|completed)|you(?:'re| are)\s+(?:done|finished)|you\s+(?:finish|complete)\s+(?:this|the current)\s+task|(?:the\s+)?(?:bowl|cheese|wine bottle|drawer)\s+task\s+(?:is\s+)?(?:finished|completed|done))$/i;
  const prefix = /^(?:after|once|when)\s+(.+?)[,;.!]\s*(.+)$/i.exec(text);
  if (prefix) {
    const condition = prefix[1].trim(), candidate = prefix[2].trim();
    const physical = /^(?:the\s+)?(?:bowl|cheese|(?:wine\s+)?bottle|drawer|stove|plate)\s+(?:is|are|has been|have been)\s+.{0,100}$/i.test(condition) && /\b(?:down|on|in|inside|released|placed|open|opened|closed|shut|stable)\b/i.test(condition);
    if ((done.test(condition) || physical) && action.test(candidate)) return candidate.replace(/^then\s+/i, "");
  }
  const suffix = /^(.+?)\s+(?:when|once|after)\s+(.+?)[.!]*$/i.exec(text);
  if (suffix && done.test(suffix[2].trim()) && action.test(suffix[1])) return suffix[1].trim();
  const task = /^(?:after|once|when)\s+((?:this|the current|current) task\s+(?:is\s+)?(?:finishes|completes|finished|completed|done))\s+(.+)$/i.exec(text);
  if (task && done.test(task[1]) && action.test(task[2])) return task[2].trim();
  return;
}
export {
  englishWaitingCandidate
};
