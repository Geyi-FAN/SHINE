import { openRecoveringQwenRealtimeSession } from '../realtime/recovering-session.js';
import { analyzeQwenRealtimeImage } from '../realtime/visual-analysis.js';
import { synthesizeNotificationSpeech } from '../realtime/notification-speech.js';
// Preserve the established event/receipt/recovery contract; no second state machine.
export const qwenAdapter = Object.freeze({
    id: 'qwen-realtime',
    openDialogue: openRecoveringQwenRealtimeSession,
    analyzeImage: analyzeQwenRealtimeImage,
    synthesizeSpeech: synthesizeNotificationSpeech,
});
