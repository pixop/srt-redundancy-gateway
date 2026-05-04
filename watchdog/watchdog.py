#!/usr/bin/env python3
import json
import logging
import os
import signal
import socket
import threading
import time
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
        self.stop_event = threading.Event()
        self.event_thread: Optional[threading.Thread] = None

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
        self.metric_active_input = Gauge("gateway_active_input", "Current active tsswitch input index")
        self.metric_last_switch_ts = Gauge("gateway_last_switch_unixtime", "Unix time of last successful switch command")
        self.metric_node_health = Gauge("watchdog_node_health", "Node stable health (1=healthy,0=not healthy)", ["node"])
        self.metric_good_streak = Gauge("watchdog_node_good_streak", "Consecutive successful checks", ["node"])
        self.metric_bad_streak = Gauge("watchdog_node_bad_streak", "Consecutive failed checks", ["node"])
        self.metric_health_checks = Counter(
            "watchdog_health_checks_total", "Total health checks by result", ["node", "result"]
        )
        self.metric_health_latency = Histogram("watchdog_health_check_latency_seconds", "Health check latency", ["node"])
        self.metric_switch_cmd = Counter(
            "watchdog_switch_commands_total", "Switch commands sent to tsswitch", ["target", "result"]
        )
        self.metric_switch_events = Counter("watchdog_switch_events_total", "Input switch events observed")
        self.metric_loop_errors = Counter("watchdog_loop_errors_total", "Main loop exceptions")

    def start(self) -> None:
        start_http_server(self.metrics_port, addr=self.metrics_host)
        self.metric_up.set(1)
        self.metric_active_input.set(self.current_active_input)

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
                self.run_cycle()
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
                self.metric_health_latency.labels(node=node.name).observe(latency)
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

            self.metric_node_health.labels(node=node.name).set(1 if node.stable_healthy else 0)
            self.metric_good_streak.labels(node=node.name).set(node.good_streak)
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
        with self._span("send_switch_command"):
            payload = f"{target_input}\n".encode("utf-8")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(payload, (self.remote_host, self.remote_port))
                sock.close()
                self.commanded_input = target_input
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
                self.logger.warning("event_parse_failed", extra={"extra_data": {"raw": raw}})
                continue

            new_input = self._extract_new_input(event)
            if new_input is not None:
                self.current_active_input = new_input
                self.metric_active_input.set(new_input)
                self.metric_switch_events.inc()
                self.logger.info("switch_event_observed", extra={"extra_data": {"event": event, "active_input": new_input}})
            else:
                self.logger.info("event_observed", extra={"extra_data": {"event": event}})

        sock.close()

    @staticmethod
    def _extract_new_input(event: dict) -> Optional[int]:
        if not isinstance(event, dict):
            return None
        candidates = ("new_input", "new", "input", "current_input", "current")
        for key in candidates:
            value = event.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

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
#!/usr/bin/env python3
import json
import os
import signal
import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests
from prometheus_client import Counter, Gauge, Histogram, start_http_server

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except Exception:  # pragma: no cover
    trace = None


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def log(level: str, message: str, **fields: object) -> None:
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level,
        "msg": message,
        **fields,
    }
    print(json.dumps(payload, sort_keys=True), flush=True)


@dataclass
class NodeState:
    name: str
    url: str
    healthy: bool = False
    stable_healthy: bool = False
    consecutive_good: int = 0
    consecutive_bad: int = 0


class TSSwitchClient:
    def __init__(self, remote_host: str, remote_port: int):
        self._addr = (remote_host, remote_port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def set_input(self, index: int) -> None:
        payload = f"{index}\n".encode("utf-8")
        self._sock.sendto(payload, self._addr)


class EventListener(threading.Thread):
    def __init__(self, host: str, port: int, stop_event: threading.Event):
        super().__init__(daemon=True)
        self._host = host
        self._port = port
        self._stop_event = stop_event
        self._sock: Optional[socket.socket] = None
        self.last_active_input: Optional[int] = None
        self.last_event: Optional[dict] = None

    def run(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((self._host, self._port))
        self._sock.settimeout(0.5)
        log("INFO", "event listener started", host=self._host, port=self._port)
        while not self._stop_event.is_set():
            try:
                data, peer = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            text = data.decode("utf-8", errors="replace").strip()
            parsed = self._parse_event(text)
            if parsed is not None:
                self.last_active_input = parsed
                log("INFO", "received switch event", peer=f"{peer[0]}:{peer[1]}", active_input=parsed)
        log("INFO", "event listener stopped")

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()

    @staticmethod
    def _parse_event(text: str) -> Optional[int]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None

        # tsswitch event schemas may vary across versions, so parse defensively.
        for key in ("newinput", "new_input", "current_input", "input"):
            value = payload.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None


class Watchdog:
    def __init__(self):
        self.node_a = NodeState("a", os.getenv("WATCHDOG_NODE_A_URL", "http://127.0.0.1:18081/health"))
        self.node_b = NodeState("b", os.getenv("WATCHDOG_NODE_B_URL", "http://127.0.0.1:18082/health"))
        self.poll_interval = float(os.getenv("WATCHDOG_POLL_INTERVAL_SECONDS", "1.0"))
        self.timeout_seconds = float(os.getenv("WATCHDOG_HTTP_TIMEOUT_SECONDS", "1.5"))
        self.good_threshold = int(os.getenv("WATCHDOG_GOOD_THRESHOLD", "2"))
        self.bad_threshold = int(os.getenv("WATCHDOG_BAD_THRESHOLD", "3"))
        self.current_input = int(os.getenv("WATCHDOG_INITIAL_INPUT", "0"))

        remote_host = os.getenv("TSSWITCH_REMOTE_HOST", "127.0.0.1")
        remote_port = int(os.getenv("TSSWITCH_REMOTE_PORT", "4444"))
        self.switch_client = TSSwitchClient(remote_host, remote_port)

        self.stop_event = threading.Event()
        self.enable_event_listener = env_bool("WATCHDOG_ENABLE_EVENT_LISTENER", True)
        self.event_listener = None
        if self.enable_event_listener:
            event_host = os.getenv("WATCHDOG_EVENT_LISTEN_HOST", "0.0.0.0")
            event_port = int(os.getenv("WATCHDOG_EVENT_LISTEN_PORT", "4545"))
            self.event_listener = EventListener(event_host, event_port, self.stop_event)

        metrics_host = os.getenv("WATCHDOG_METRICS_HOST", "0.0.0.0")
        metrics_port = int(os.getenv("WATCHDOG_METRICS_PORT", "9108"))
        start_http_server(metrics_port, addr=metrics_host)
        log("INFO", "metrics server started", host=metrics_host, port=metrics_port)

        self._configure_tracing()
        self.tracer = trace.get_tracer(__name__) if trace else None

    def _configure_tracing(self) -> None:
        if not env_bool("OTEL_ENABLED", False):
            return
        if trace is None:
            log("WARN", "otel modules unavailable; tracing disabled")
            return

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
        insecure = env_bool("OTEL_EXPORTER_OTLP_INSECURE", True)
        service_name = os.getenv("OTEL_SERVICE_NAME", "srt-redundancy-watchdog")

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces", insecure=insecure)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        log("INFO", "otel tracing enabled", endpoint=endpoint, service_name=service_name)

    def start(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        if self.event_listener is not None:
            self.event_listener.start()

        log(
            "INFO",
            "watchdog started",
            poll_interval_seconds=self.poll_interval,
            timeout_seconds=self.timeout_seconds,
            good_threshold=self.good_threshold,
            bad_threshold=self.bad_threshold,
            initial_input=self.current_input,
        )
        ACTIVE_INPUT_GAUGE.set(self.current_input)

        while not self.stop_event.is_set():
            loop_start = time.time()
            self._check_node(self.node_a)
            self._check_node(self.node_b)
            self._decide()
            WATCHDOG_LOOP_SECONDS.observe(time.time() - loop_start)
            self.stop_event.wait(self.poll_interval)

        if self.event_listener is not None:
            self.event_listener.close()
        log("INFO", "watchdog stopped")

    def _handle_signal(self, signum: int, _frame: object) -> None:
        log("INFO", "termination signal received", signal=signum)
        self.stop_event.set()

    def _check_node(self, node: NodeState) -> None:
        span_ctx = self.tracer.start_as_current_span(f"health_check_{node.name}") if self.tracer else None
        if span_ctx is None:
            self._do_check(node)
            return
        with span_ctx as span:
            self._do_check(node, span)

    def _do_check(self, node: NodeState, span=None) -> None:
        start = time.time()
        status = "error"
        try:
            response = requests.get(node.url, timeout=self.timeout_seconds)
            node.healthy = 200 <= response.status_code < 400
            status = "ok" if node.healthy else "bad_status"
        except requests.Timeout:
            node.healthy = False
            status = "timeout"
            HEALTH_CHECK_FAILURES.labels(node=node.name, reason="timeout").inc()
        except Exception:
            node.healthy = False
            status = "error"
            HEALTH_CHECK_FAILURES.labels(node=node.name, reason="error").inc()

        latency = time.time() - start
        HEALTH_CHECK_DURATION.labels(node=node.name).observe(latency)
        NODE_HEALTH_GAUGE.labels(node=node.name).set(1 if node.healthy else 0)

        if node.healthy:
            node.consecutive_good += 1
            node.consecutive_bad = 0
            if node.consecutive_good >= self.good_threshold:
                node.stable_healthy = True
        else:
            node.consecutive_bad += 1
            node.consecutive_good = 0
            if node.consecutive_bad >= self.bad_threshold:
                node.stable_healthy = False

        NODE_STABLE_HEALTH_GAUGE.labels(node=node.name).set(1 if node.stable_healthy else 0)
        NODE_GOOD_STREAK_GAUGE.labels(node=node.name).set(node.consecutive_good)
        NODE_BAD_STREAK_GAUGE.labels(node=node.name).set(node.consecutive_bad)

        if span is not None:
            span.set_attribute("node.name", node.name)
            span.set_attribute("node.url", node.url)
            span.set_attribute("health.status", status)
            span.set_attribute("health.latency_seconds", latency)
            span.set_attribute("health.stable_healthy", node.stable_healthy)

        log(
            "DEBUG",
            "node polled",
            node=node.name,
            healthy=node.healthy,
            stable_healthy=node.stable_healthy,
            good_streak=node.consecutive_good,
            bad_streak=node.consecutive_bad,
            latency_ms=int(latency * 1000),
        )

    def _decide(self) -> None:
        desired_input = self.current_input
        reason = "hold"

        if self.node_a.stable_healthy:
            desired_input = 0
            reason = "prefer_a_healthy"
        elif (not self.node_a.stable_healthy) and self.node_b.stable_healthy:
            desired_input = 1
            reason = "a_unhealthy_b_healthy"

        DECISION_COUNTER.labels(reason=reason).inc()

        if desired_input == self.current_input:
            ACTIVE_INPUT_GAUGE.set(self.current_input)
            return

        span_ctx = self.tracer.start_as_current_span("switch_input") if self.tracer else None
        if span_ctx is None:
            self._apply_switch(desired_input, reason)
            return
        with span_ctx as span:
            span.set_attribute("from_input", self.current_input)
            span.set_attribute("to_input", desired_input)
            span.set_attribute("reason", reason)
            self._apply_switch(desired_input, reason)

    def _apply_switch(self, desired_input: int, reason: str) -> None:
        previous = self.current_input
        try:
            self.switch_client.set_input(desired_input)
        except Exception as exc:
            COMMAND_FAILURES.inc()
            log("ERROR", "failed to send switch command", error=str(exc), desired_input=desired_input)
            return

        self.current_input = desired_input
        ACTIVE_INPUT_GAUGE.set(self.current_input)
        SWITCH_COUNTER.labels(reason=reason).inc()
        LAST_SWITCH_UNIX.set(time.time())
        log("INFO", "switch command sent", previous_input=previous, current_input=self.current_input, reason=reason)

        if self.event_listener and self.event_listener.last_active_input is not None:
            EVENT_REPORTED_INPUT_GAUGE.set(self.event_listener.last_active_input)


ACTIVE_INPUT_GAUGE = Gauge("gateway_active_input", "Current active tsswitch input index")
EVENT_REPORTED_INPUT_GAUGE = Gauge(
    "gateway_event_reported_input",
    "Active input index reported via tsswitch event stream",
)
LAST_SWITCH_UNIX = Gauge("gateway_last_switch_unix_seconds", "Unix timestamp of last switch command")
NODE_HEALTH_GAUGE = Gauge("gateway_node_health", "Instant health check result (1=healthy)", ["node"])
NODE_STABLE_HEALTH_GAUGE = Gauge("gateway_node_stable_health", "Hysteresis-filtered node health", ["node"])
NODE_GOOD_STREAK_GAUGE = Gauge("gateway_node_good_streak", "Consecutive healthy poll count", ["node"])
NODE_BAD_STREAK_GAUGE = Gauge("gateway_node_bad_streak", "Consecutive unhealthy poll count", ["node"])
SWITCH_COUNTER = Counter("gateway_switch_total", "Number of switch commands sent", ["reason"])
COMMAND_FAILURES = Counter("gateway_switch_command_failures_total", "Switch command send failures")
DECISION_COUNTER = Counter("gateway_decision_total", "Decision loop outcomes", ["reason"])
HEALTH_CHECK_FAILURES = Counter(
    "gateway_health_check_failures_total", "Health check failures", ["node", "reason"]
)
HEALTH_CHECK_DURATION = Histogram(
    "gateway_health_check_duration_seconds",
    "Health check latency",
    ["node"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
WATCHDOG_LOOP_SECONDS = Histogram(
    "gateway_watchdog_loop_duration_seconds",
    "Watchdog loop execution duration",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)


def main() -> None:
    watchdog = Watchdog()
    watchdog.start()


if __name__ == "__main__":
    main()
