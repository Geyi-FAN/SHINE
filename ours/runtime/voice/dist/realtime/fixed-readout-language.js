/** Fixed receipts must be read in their own language, never translated. */
export function fixedReadoutLanguage(announcement, fallback) {
    if (!announcement)
        return fallback;
    if (/\p{Script=Han}/u.test(announcement))
        return 'zh-CN';
    if (/[A-Za-z]/u.test(announcement))
        return 'en';
    return fallback;
}
