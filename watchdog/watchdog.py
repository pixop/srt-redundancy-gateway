#!/usr/bin/env python3
import json
import logging
import os
import signal
import socket
import threading
import time
from collections import deque
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram, start_http_server

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except Exception:  # pragma: no cover
    trace = None


def env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class NodeState:
    name: str
    url: str
    good_streak: int = 0
    bad_streak: int = 0
    stable_healthy: bool = False
    stable_unhealthy: bool = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        extra = getattr(record, "extra_data", None)
        if isinstance(extra, dict):
            payload.update(extra)

        if trace is not None:
            span = trace.get_current_span()
            ctx = span.get_span_context() if span else None
            if ctx and ctx.is_valid:
                payload["trace_id"] = f"{ctx.trace_id:032x}"
                payload["span_id"] = f"{ctx.span_id:016x}"

        return json.dumps(payload, separators=(",", ":"))


class Watchdog:
    def __init__(self) -> None:
        self.mode = env_str("WATCHDOG_MODE", "controller")
        self.enable_health_polling = env_bool("WATCHDOG_ENABLE_HEALTH_POLLING", self.mode != "event_observer")
        self.enable_switch_commands = env_bool("WATCHDOG_ENABLE_SWITCH_COMMANDS", self.mode != "event_observer")
        self.enable_waiting_inference = env_bool(
            "WATCHDOG_ENABLE_WAITING_INFERENCE",
            self.mode == "event_observer",
        )
        self.waiting_flap_window_sec = env_float("WATCHDOG_WAITING_FLAP_WINDOW_SEC", 8.0)
        self.waiting_flap_threshold = env_int("WATCHDOG_WAITING_FLAP_THRESHOLD", 3)

        self.node_a = NodeState("a", env_str("NODE_A_HEALTH_URL", "http://127.0.0.1:18081/health"))
        self.node_b = NodeState("b", env_str("NODE_B_HEALTH_URL", "http://127.0.0.1:18082/health"))

        self.poll_interval = env_float("WATCHDOG_POLL_INTERVAL_SEC", 1.0)
        self.timeout = env_float("WATCHDOG_HEALTH_TIMEOUT_SEC", 1.5)
        self.good_threshold = env_int("WATCHDOG_GOOD_THRESHOLD", 3)
        self.bad_threshold = env_int("WATCHDOG_BAD_THRESHOLD", 3)

        self.remote_host = env_str("TSSWITCH_REMOTE_HOST", "127.0.0.1")
        self.remote_port = env_int("TSSWITCH_REMOTE_PORT", 4444)

        self.event_host = env_str("WATCHDOG_EVENT_LISTEN_HOST", "0.0.0.0")
        self.event_port = env_int("WATCHDOG_EVENT_LISTEN_PORT", 5556)

        self.metrics_host = env_str("WATCHDOG_METRICS_HOST", "0.0.0.0")
        self.metrics_port = env_int("WATCHDOG_METRICS_PORT", 9108)

        self.current_active_input = env_int("WATCHDOG_INITIAL_ACTIVE_INPUT", 0)
        self.commanded_input = self.current_active_input
        self.last_switch_event_ts = time.time()
        self.recent_switches: deque[tuple[float, int]] = deque(maxlen=128)
        self.stop_event = threading.Event()
        self.event_thread: Optional[threading.Thread] = None
        self.started_monotonic = time.monotonic()

        self.logger = logging.getLogger("watchdog")
        self._configure_logging()
        self._configure_otel()
        self.tracer = trace.get_tracer("srt-redundancy-watchdog") if trace is not None else None

        self._init_metrics()

    def _configure_logging(self) -> None:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        self.logger.handlers = [handler]
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

    def _configure_otel(self) -> None:
        if trace is None:
            self.logger.warning("OpenTelemetry packages not available", extra={"extra_data": {"otel_enabled": False}})
            return

        enabled = env_bool("OTEL_ENABLED", True)
        if not enabled:
            return

        endpoint = env_str("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
        service_name = env_str("OTEL_SERVICE_NAME", "srt-redundancy-watchdog")
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

    def _init_metrics(self) -> None:
        self.metric_up = Gauge("watchdog_up", "Watchdog process running state")
        self.metric_uptime_seconds = Gauge("watchdog_uptime_seconds", "Seconds since watchdog process start")
        self.metric_active_input = Gauge("gateway_active_input", "Current active tsswitch input index")
        self.metric_last_switch_ts = Gauge("gateway_last_switch_unixtime", "Unix time of last successful switch command")

        if self.enable_health_polling:
            self.metric_node_health = Gauge("watchdog_node_health", "Node stable health (1=healthy,0=not healthy)", ["node"])
            self.metric_good_streak = Gauge("watchdog_node_good_streak", "Consecutive successful checks", ["node"])
            self.metric_bad_streak = Gauge("watchdog_node_bad_streak", "Consecutive failed checks", ["node"])
            self.metric_health_checks = Counter(
                "watchdog_health_checks_total", "Total health checks by result", ["node", "result"]
            )
            self.metric_health_latency = Histogram("watchdog_health_check_latency_seconds", "Health check latency", ["node"])
        else:
            self.metric_node_health = None
            self.metric_good_streak = None
            self.metric_bad_streak = None
            self.metric_health_checks = None
            self.metric_health_latency = None

        if self.enable_switch_commands:
            self.metric_switch_cmd = Counter(
                "watchdog_switch_commands_total", "Switch commands sent to tsswitch", ["target", "result"]
            )
        else:
            self.metric_switch_cmd = None

        self.metric_switch_events = Counter("watchdog_switch_events_total", "Input switch events observed")
        self.metric_events_total = Counter("watchdog_events_total", "Total JSON events received from tsswitch")
        self.metric_event_type_total = Counter(
            "watchdog_event_type_total",
            "Total JSON events by extracted event type",
            ["event_type"],
        )
        self.metric_event_parse_failures = Counter("watchdog_event_parse_failures_total", "Malformed/unparseable event payloads")
        self.metric_last_event_ts = Gauge("watchdog_last_event_unixtime", "Unix time of the last received tsswitch event")
        self.metric_waiting_for_input = Gauge(
            "gateway_waiting_for_input",
            "Whether tsswitch appears to be waiting for a valid input (1=yes,0=no)",
        )
        self.metric_loop_errors = Counter("watchdog_loop_errors_total", "Main loop exceptions")

    def start(self) -> None:
        start_http_server(self.metrics_port, addr=self.metrics_host)
        self.metric_up.set(1)
        self.metric_uptime_seconds.set(time.monotonic() - self.started_monotonic)
        self.metric_active_input.set(self.current_active_input)
        self.metric_waiting_for_input.set(0)

        self.logger.info(
            "watchdog_starting",
            extra={
                "extra_data": {
                    "node_a_url": self.node_a.url,
                    "node_b_url": self.node_b.url,
                    "remote_host": self.remote_host,
                    "remote_port": self.remote_port,
                    "event_host": self.event_host,
                    "event_port": self.event_port,
                    "metrics_host": self.metrics_host,
                    "metrics_port": self.metrics_port,
                    "mode": self.mode,
                    "enable_health_polling": self.enable_health_polling,
                    "enable_switch_commands": self.enable_switch_commands,
                    "enable_waiting_inference": self.enable_waiting_inference,
                    "waiting_flap_window_sec": self.waiting_flap_window_sec,
                    "waiting_flap_threshold": self.waiting_flap_threshold,
                    "poll_interval_sec": self.poll_interval,
                    "health_timeout_sec": self.timeout,
                    "good_threshold": self.good_threshold,
                    "bad_threshold": self.bad_threshold,
                    "initial_active_input": self.current_active_input,
                }
            },
        )

        self.event_thread = threading.Thread(target=self._event_listener_loop, daemon=True)
        self.event_thread.start()

        while not self.stop_event.is_set():
            try:
                self.metric_uptime_seconds.set(time.monotonic() - self.started_monotonic)
                if self.enable_health_polling:
                    self.run_cycle()
                self._refresh_waiting_inference()
            except Exception as exc:  # pragma: no cover
                self.metric_loop_errors.inc()
                self.logger.exception("main_loop_error", extra={"extra_data": {"error": str(exc)}})
            self.stop_event.wait(self.poll_interval)

        self.metric_up.set(0)
        self.logger.info("watchdog_stopped")

    def stop(self) -> None:
        self.stop_event.set()

    def run_cycle(self) -> None:
        with self._span("watchdog_cycle"):
            a_ok = self._check_node(self.node_a)
            b_ok = self._check_node(self.node_b)
            desired = self._decide_desired_input()

            self.logger.info(
                "decision_evaluated",
                extra={
                    "extra_data": {
                        "node_a_ok": a_ok,
                        "node_b_ok": b_ok,
                        "node_a_stable_healthy": self.node_a.stable_healthy,
                        "node_a_stable_unhealthy": self.node_a.stable_unhealthy,
                        "node_b_stable_healthy": self.node_b.stable_healthy,
                        "node_b_stable_unhealthy": self.node_b.stable_unhealthy,
                        "commanded_input": self.commanded_input,
                        "active_input": self.current_active_input,
                        "desired_input": desired,
                    }
                },
            )

            if desired != self.commanded_input:
                self._send_switch_command(desired)

    def _check_node(self, node: NodeState) -> bool:
        with self._span(f"health_check_{node.name}"):
            started = time.monotonic()
            ok = False
            result = "error"
            try:
                req = urllib.request.Request(node.url, method="GET")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    ok = 200 <= resp.status < 300
                    result = "ok" if ok else "bad_status"
            except urllib.error.HTTPError:
                result = "bad_status"
            except urllib.error.URLError:
                result = "timeout_or_network"
            except TimeoutError:
                result = "timeout_or_network"
            finally:
                latency = time.monotonic() - started
                if self.metric_health_latency is not None:
                    self.metric_health_latency.labels(node=node.name).observe(latency)
                if self.metric_health_checks is not None:
                    self.metric_health_checks.labels(node=node.name, result=result).inc()

            if ok:
                node.good_streak += 1
                node.bad_streak = 0
            else:
                node.bad_streak += 1
                node.good_streak = 0

            if node.good_streak >= self.good_threshold:
                node.stable_healthy = True
                node.stable_unhealthy = False
            if node.bad_streak >= self.bad_threshold:
                node.stable_unhealthy = True
                node.stable_healthy = False

            if self.metric_node_health is not None:
                self.metric_node_health.labels(node=node.name).set(1 if node.stable_healthy else 0)
            if self.metric_good_streak is not None:
                self.metric_good_streak.labels(node=node.name).set(node.good_streak)
            if self.metric_bad_streak is not None:
                self.metric_bad_streak.labels(node=node.name).set(node.bad_streak)

            self.logger.info(
                "health_polled",
                extra={
                    "extra_data": {
                        "node": node.name,
                        "url": node.url,
                        "ok": ok,
                        "result": result,
                        "latency_ms": round(latency * 1000, 2),
                        "good_streak": node.good_streak,
                        "bad_streak": node.bad_streak,
                        "stable_healthy": node.stable_healthy,
                        "stable_unhealthy": node.stable_unhealthy,
                    }
                },
            )

            return ok

    def _decide_desired_input(self) -> int:
        # Policy:
        # - Prefer node A whenever it is stably healthy.
        # - Only use node B when node A is stably unhealthy and node B is healthy.
        desired = self.commanded_input
        if self.node_a.stable_healthy:
            desired = 0
        elif self.node_a.stable_unhealthy and self.node_b.stable_healthy:
            desired = 1
        return desired

    def _send_switch_command(self, target_input: int) -> None:
        if not self.enable_switch_commands:
            self.logger.info(
                "switch_command_skipped",
                extra={"extra_data": {"reason": "switch_commands_disabled", "target_input": target_input}},
            )
            return
        with self._span("send_switch_command"):
            payload = f"{target_input}\n".encode("utf-8")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(payload, (self.remote_host, self.remote_port))
                sock.close()
                self.commanded_input = target_input
                if self.metric_switch_cmd is not None:
                    self.metric_switch_cmd.labels(target=str(target_input), result="ok").inc()
                self.metric_last_switch_ts.set(time.time())
                self.logger.info(
                    "switch_command_sent",
                    extra={
                        "extra_data": {
                            "target_input": target_input,
                            "remote_host": self.remote_host,
                            "remote_port": self.remote_port,
                        }
                    },
                )
            except Exception as exc:
                if self.metric_switch_cmd is not None:
                    self.metric_switch_cmd.labels(target=str(target_input), result="error").inc()
                self.logger.error(
                    "switch_command_failed",
                    extra={"extra_data": {"target_input": target_input, "error": str(exc)}},
                )

    def _event_listener_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.event_host, self.event_port))
        sock.settimeout(1.0)
        self.logger.info(
            "event_listener_started",
            extra={"extra_data": {"event_host": self.event_host, "event_port": self.event_port}},
        )

        while not self.stop_event.is_set():
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except Exception as exc:  # pragma: no cover
                self.logger.error("event_listener_error", extra={"extra_data": {"error": str(exc)}})
                continue

            raw = data.decode("utf-8", errors="replace")
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                self.metric_event_parse_failures.inc()
                self.logger.warning("event_parse_failed", extra={"extra_data": {"raw": raw}})
                continue

            self.metric_events_total.inc()
            self.metric_last_event_ts.set(time.time())
            event_type = self._extract_event_type(event)
            self.metric_event_type_total.labels(event_type=event_type).inc()

            new_input = self._extract_new_input(event)
            if new_input is not None:
                previous_input = self.current_active_input
                self.current_active_input = new_input
                self.last_switch_event_ts = time.time()
                self.metric_active_input.set(new_input)
                if previous_input != new_input:
                    self.recent_switches.append((time.time(), new_input))
                self.metric_switch_events.inc()
                self.logger.info(
                    "switch_event_observed",
                    extra={
                        "extra_data": {
                            "event_type": event_type,
                            "event": event,
                            "active_input": new_input,
                            "flapping_waiting": self._is_flapping_waiting(),
                        }
                    },
                )
            else:
                self.logger.info("event_observed", extra={"extra_data": {"event_type": event_type, "event": event}})

        sock.close()

    def _refresh_waiting_inference(self) -> None:
        if not self.enable_waiting_inference:
            return
        flapping = self._is_flapping_waiting()
        waiting_now = flapping
        self.metric_waiting_for_input.set(1 if waiting_now else 0)

    def _is_flapping_waiting(self) -> bool:
        now = time.time()
        while self.recent_switches and (now - self.recent_switches[0][0]) > self.waiting_flap_window_sec:
            self.recent_switches.popleft()
        if len(self.recent_switches) < self.waiting_flap_threshold:
            return False
        inputs = {item[1] for item in self.recent_switches}
        return len(inputs) >= 2

    @staticmethod
    def _extract_new_input(event: dict) -> Optional[int]:
        # Authoritative tsswitch --event-udp schema (from TSDuck source):
        # {
        #   "event": "newinput",
        #   "previous-input": <int>,
        #   "new-input": <int>,
        #   ...
        # }
        if not isinstance(event, dict):
            return None
        value = event.get("new-input")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None

    @staticmethod
    def _extract_event_type(event: object) -> str:
        if isinstance(event, dict):
            value = event.get("event")
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return "unknown"

    def _span(self, name: str):
        if self.tracer is None:
            return _NullContext()
        return self.tracer.start_as_current_span(name)


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, _exc_type, _exc, _tb):
        return False


def main() -> None:
    watchdog = Watchdog()

    def _handle_signal(_signum, _frame):
        watchdog.logger.info("shutdown_signal_received")
        watchdog.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    watchdog.start()


if __name__ == "__main__":
    main()
