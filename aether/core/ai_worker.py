"""AIWorker — background thread that runs AIService.chat off the main loop.

Phase B1 (async tick loop):

    Main thread                          |  Worker thread
    -------------------------------------|-----------------------------------
    widget.submit(message)               |
       → AIWorker.submit() [non-blocking]|  → service.chat(message, session)
       → returns immediately             |     · builds context / agent loop
    main loop keeps ticking @30 Hz       |     · publishes ai.* events through
    Application.tick → EventBus.flush()  |       the thread-safe EventBus
    delivers ai.* on the main thread     |     · never touches QWidget / Qt

Contract:
  - submit() never blocks the caller; the 30 Hz tick is never held on AI.
  - A single worker thread consumes tasks serially (no concurrent chat runs
    within the worker).
  - Cross-thread delivery happens via queued EventBus events; all UI updates
    are marshaled to the main thread by EventBus.flush() inside the tick.
    No QWidget is ever created or mutated off the main thread.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Optional

from aether.core.profiler import profiler

logger = logging.getLogger("Aether.AIWorker")


class AIWorker:
    """Serial background executor for AIService.chat.

    Owns exactly one worker thread. ``submit()`` enqueues a chat request and
    returns immediately; the worker calls ``runner`` (bound to
    AIService.chat) off the main loop. Results are delivered to subscribers
    through the ai.* events AIService publishes on the EventBus.
    """

    def __init__(self, runner: Callable[..., Any], *, name: str = "ai-worker") -> None:
        self._runner = runner
        self._name = name
        self._queue: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._enqueued = 0
        self._completed = 0
        self._lock = threading.Lock()

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._thread = threading.Thread(
                target=self._run,
                name=self._name,
                daemon=True,
            )
            self._thread.start()
        logger.info("AI worker started (thread=%s)", self._name)

    def stop(self, timeout: float = 2.0) -> None:
        with self._lock:
            started = self._started
            thread = self._thread
            if not started:
                return
            self._stop_event.set()
            self._started = False
        try:
            self._queue.put(None)  # wake the worker so it can exit
        except Exception:  # pragma: no cover - defensive
            pass
        if thread is not None:
            thread.join(timeout)
        logger.info(
            "AI worker stopped (enqueued=%d completed=%d)",
            self._enqueued, self._completed,
        )

    # ── Public API ─────────────────────────────────────────────────

    def submit(self, message: str, session_id: str = "default") -> None:
        """Enqueue a chat request. Returns immediately; never blocks.

        The reply is delivered later via the ``ai.response.ready`` event
        published by AIService.chat on the worker thread.
        """
        self._enqueued += 1
        self._report_depth()
        self._queue.put((message, session_id))

    @property
    def running(self) -> bool:
        thread = self._thread
        return self._started and thread is not None and thread.is_alive()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def enqueued(self) -> int:
        return self._enqueued

    @property
    def completed(self) -> int:
        return self._completed

    # ── Worker loop ─────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_event.is_set():
            task = self._queue.get()
            if task is None:
                break
            message, session_id = task
            t0 = time.perf_counter()
            try:
                self._runner(message, session_id=session_id)
            except Exception:
                logger.exception("AI worker chat failed")
            finally:
                profiler.end("ai.chat", t0)
                self._completed += 1
                self._report_depth()
                self._queue.task_done()

    def _report_depth(self) -> None:
        profiler.set_queue("ai_worker", depth=self._queue.qsize())
