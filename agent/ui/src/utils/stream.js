/**
 * AGRA Agent — SSE Stream Handler
 * Reusable server-sent events connector with reconnection.
 */

/**
 * Connect to an SSE endpoint using fetch (POST body support).
 *
 * @param {string} url       - The SSE endpoint URL
 * @param {object} body      - JSON body to POST
 * @param {function} onToken - Called with each token/data event
 * @param {function} onDone  - Called when stream completes (receives final data)
 * @param {function} onError - Called on error
 * @returns {{ abort: () => void }} - Controller to abort the stream
 */
export function connectStream(url, body, onToken, onDone, onError) {
  const controller = new AbortController();
  const { signal } = controller;

  const token = localStorage.getItem('agra_token') || '';

  const run = async () => {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
        signal,
      });

      if (!response.ok) {
        const errText = await response.text();
        let errMsg;
        try {
          const errJson = JSON.parse(errText);
          errMsg = errJson.detail || errJson.error || errText;
        } catch {
          errMsg = errText;
        }
        throw new Error(`HTTP ${response.status}: ${errMsg}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        // Keep incomplete last line in buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          const jsonStr = trimmed.slice(6);
          if (jsonStr === '[DONE]') {
            onDone?.({});
            return;
          }

          try {
            const data = JSON.parse(jsonStr);

            if (data.error) {
              onError?.(new Error(data.error));
              if (data.done) {
                onDone?.(data);
                return;
              }
              continue;
            }

            if (data.done) {
              // Final event — pass complete data to onDone
              onDone?.(data);
              return;
            }

            // Regular token/data event
            onToken?.(data);
          } catch (e) {
            // Skip unparseable lines
            console.warn('SSE parse error:', e, jsonStr);
          }
        }
      }

      // Stream ended without explicit done event
      onDone?.({});
    } catch (err) {
      if (err.name === 'AbortError') return; // User cancelled
      console.error('SSE stream error:', err);
      onError?.(err);
    }
  };

  run();

  return {
    abort: () => {
      controller.abort();
    },
  };
}

/**
 * Connect to a GET-based SSE endpoint using EventSource.
 *
 * @param {string} url        - The SSE endpoint URL (with query params)
 * @param {function} onEvent  - Called with each event data
 * @param {function} onError  - Called on error
 * @returns {{ close: () => void }} - Controller to close the connection
 */
export function connectEventSource(url, onEvent, onError) {
  const eventSource = new EventSource(url);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onEvent?.(data);
    } catch {
      onEvent?.(event.data);
    }
  };

  eventSource.onerror = (err) => {
    console.error('EventSource error:', err);
    onError?.(err);
    eventSource.close();
  };

  return {
    close: () => {
      eventSource.close();
    },
  };
}
