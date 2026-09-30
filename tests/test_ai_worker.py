"""Tests for AIWorker — the Phase B1 async AI worker thread.

Verifies that ai.chat execution runs off the main loop without blocking the
caller, is capacity-limited to a single serial worker, and shuts down cleanly.
"""

from __future__ import annotations

import threading
import time

import pytest

from aether.ai.provider import EchoProvider
from aether.ai.service import AIService
from aether.core.ai_worker import AIWorker
from aether.core.event_bus_v2 import EventBus


def test_submit_is_nonblocking_when_runner_blocks() -> None:
    started = threading.Event()

    def slow_chat(message: str, session_id: str = "default") -> None:
        started.set()
        time.sleep(0.5)

    worker = AIWorker(slow_chat)
    worker.start()

    try:
        t0 = time.perf_counter()
        worker.submit("hello")
        submit_ms = (time.perf_counter() - t0) * 1000.0
        # submit() must not block on the running chat.
        assert submit_ms < 100.0
        assert started.wait(2.0) is True
    finally:
        worker.stop()


def test_worker_calls_service_chat_and_completes() -> None:
    service = AIService(provider=EchoProvider())
    worker = AIWorker(service.chat)
    worker.start()

    try:
        worker.submit("hello worker", session_id="default")
        deadline = time.perf_counter() + 2.0
        while worker.completed < 1 and time.perf_counter() < deadline:
            time.sleep(0.01)
        assert worker.completed == 1
        # The service recorded the turn (user + assistant).
        history = service.history("default")
        assert len(history) == 2
        assert history[0].content == "hello worker"
    finally:
        worker.stop()


def test_worker_processes_tasks_serially() -> None:
    order: list[int] = []
    lock = threading.Lock()

    def runner(message: str, session_id: str = "default") -> None:
        with lock:
            order.append(int(message))
        time.sleep(0.02)

    worker = AIWorker(runner)
    worker.start()

    try:
        for i in range(5):
            worker.submit(str(i))
        deadline = time.perf_counter() + 2.0
        while worker.completed < 5 and time.perf_counter() < deadline:
            time.sleep(0.01)
        assert worker.completed == 5
        assert order == [0, 1, 2, 3, 4]  # FIFO, serial
    finally:
        worker.stop()


def test_worker_publishes_ai_response_event() -> None:
    event_bus = EventBus(queued=False)
    service = AIService(provider=EchoProvider(), event_bus=event_bus)
    worker = AIWorker(service.chat)
    worker.start()

    try:
        worker.submit("event check", session_id="default")
        deadline = time.perf_counter() + 2.0
        while worker.completed < 1 and time.perf_counter() < deadline:
            time.sleep(0.01)
        stats = event_bus.get_event_stats()
        assert stats["ai.response.ready"]["published"] >= 1
        assert stats["ai.thinking.started"]["published"] >= 1
    finally:
        worker.stop()


def test_stop_joins_thread() -> None:
    started = threading.Event()

    def blocking(message: str, session_id: str = "default") -> None:
        started.set()
        time.sleep(10.0)  # longer than stop timeout

    worker = AIWorker(blocking)
    worker.start()
    assert worker.running is True

    worker.submit("x")
    assert started.wait(2.0) is True

    t0 = time.perf_counter()
    worker.stop(timeout=0.5)
    worker.stop(timeout=0.5)  # idempotent / double-stop safe
    assert time.perf_counter() - t0 < 5.0


def test_pending_tracks_queued_tasks() -> None:
    started = threading.Event()

    def slow(message: str, session_id: str = "default") -> None:
        started.set()
        time.sleep(0.3)

    worker = AIWorker(slow)
    worker.start()
    try:
        worker.submit("one")
        assert started.wait(2.0) is True
        worker.submit("two")
        worker.submit("three")
        assert worker.pending >= 2
    finally:
        worker.stop()
