"""Prometheus metrics configuration for the application.

This module sets up and configures Prometheus metrics for monitoring the application.
"""

from prometheus_client import Counter, Histogram, Gauge
from starlette_prometheus import metrics, PrometheusMiddleware

# Request metrics
http_requests_total = Counter("http_requests_total", "Total number of HTTP requests", ["method", "endpoint", "status"])

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds", ["method", "endpoint"]
)

# Database metrics
db_connections = Gauge("db_connections", "Number of active database connections")

# Custom business metrics
orders_processed = Counter("orders_processed_total", "Total number of orders processed")

llm_inference_duration_seconds = Histogram(
    "llm_inference_duration_seconds",
    "Time spent processing LLM inference",
    ["model"],
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0],
)


llm_stream_duration_seconds = Histogram(
    "llm_stream_duration_seconds",
    "Time spent processing LLM stream inference",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# Chatwoot integration metrics
chatwoot_webhooks_total = Counter(
    "chatwoot_webhooks_total", "Total number of Chatwoot webhooks received", ["event_type", "status"]
)

chatwoot_message_processing_duration_seconds = Histogram(
    "chatwoot_message_processing_duration_seconds",
    "Time spent processing Chatwoot messages",
    ["status"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

chatwoot_api_requests_total = Counter(
    "chatwoot_api_requests_total", "Total number of Chatwoot API requests", ["endpoint", "method", "status"]
)

chatwoot_api_request_duration_seconds = Histogram(
    "chatwoot_api_request_duration_seconds",
    "Duration of Chatwoot API requests",
    ["endpoint", "method"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

chatwoot_conversations_active = Gauge("chatwoot_conversations_active", "Number of active Chatwoot conversations")

chatwoot_messages_sent_total = Counter(
    "chatwoot_messages_sent_total", "Total number of messages sent to Chatwoot", ["status"]
)

chatwoot_webhook_validation_failures_total = Counter(
    "chatwoot_webhook_validation_failures_total",
    "Total number of Chatwoot webhook validation failures",
    ["failure_type"],
)


def setup_metrics(app):
    """Set up Prometheus metrics middleware and endpoints.

    Args:
        app: FastAPI application instance
    """
    # Add Prometheus middleware
    app.add_middleware(PrometheusMiddleware)

    # Add metrics endpoint
    app.add_route("/metrics", metrics)
