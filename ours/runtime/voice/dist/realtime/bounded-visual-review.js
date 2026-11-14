/** One bounded review. Do not duplicate an already-submitted inference POST. */
export async function requestBoundedReview(url, init, options) {
    if (options.signal?.aborted) throw new Error('visual_review_aborted');
    const remaining=options.deadline-Date.now();
    if (remaining<=0) throw new Error('visual_review_deadline');
    const controller=new AbortController();
    const abort=()=>controller.abort();
    options.signal?.addEventListener('abort',abort,{once:true});
    const timer=setTimeout(abort,Math.min(options.timeoutMs??remaining,remaining));
    try {
        const response=await fetch(url,{...init,signal:controller.signal});
        if (!response.ok) throw new Error('robot_visual_review_http_'+response.status);
        return await response.json();
    } finally {
        clearTimeout(timer);options.signal?.removeEventListener('abort',abort);
    }
}
