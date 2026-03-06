import base64
import logging
import smtplib
from dataclasses import dataclass
from datetime import timedelta
from email.message import EmailMessage

import httpx
from sqlmodel import Session, select

from app.config import settings
from app.models import AlertDelivery, AlertSubscription, Client, Event
from app.utils import now_utc

logger = logging.getLogger(__name__)


class DeliveryConfigurationError(Exception):
    pass


class RetryableDeliveryError(Exception):
    pass


@dataclass
class AlertDispatchResult:
    processed_count: int
    delivered_count: int
    retry_count: int
    blocked_count: int
    failed_count: int


def _is_region_match(subscription: AlertSubscription, event: Event) -> bool:
    if not subscription.regions:
        return True
    event_blob = " ".join(event.geos + [event.title, event.description]).lower()
    return any(region.lower() in event_blob for region in subscription.regions)


def _is_industry_match(subscription: AlertSubscription, client: Client) -> bool:
    if not subscription.industries:
        return True
    return client.industry in subscription.industries


def _build_message(event: Event) -> str:
    return (
        f"[TradeShield] {event.type} | severity={event.severity:.2f} | "
        f"{event.title[:140]} | detected={event.detected_at.isoformat()}"
    )


def _build_payload(client: Client, event: Event) -> dict:
    return {
        "event_id": event.id,
        "client_id": client.id,
        "type": event.type,
        "severity": event.severity,
        "title": event.title,
        "detected_at": event.detected_at.isoformat(),
        "evidence": event.evidence,
    }


def queue_alerts_for_event(session: Session, event: Event) -> int:
    subscriptions = session.exec(
        select(AlertSubscription).where(AlertSubscription.active.is_(True), AlertSubscription.min_severity <= event.severity)
    ).all()
    queued = 0

    for subscription in subscriptions:
        client = session.get(Client, subscription.client_id)
        if not client:
            continue
        if not _is_region_match(subscription, event):
            continue
        if not _is_industry_match(subscription, client):
            continue

        existing = session.exec(
            select(AlertDelivery).where(
                AlertDelivery.subscription_id == subscription.id,
                AlertDelivery.event_id == event.id,
            )
        ).first()
        if existing:
            continue

        session.add(
            AlertDelivery(
                client_id=client.id,
                subscription_id=subscription.id,
                event_id=event.id,
                channel=subscription.channel,
                target=subscription.target,
                status="queued",
                message=_build_message(event),
                next_attempt_at=now_utc(),
                channel_response={"queued": True},
            )
        )
        queued += 1

    session.commit()
    return queued


def _raise_for_http_status(response: httpx.Response, body_excerpt: str) -> None:
    if response.status_code < 300:
        return
    if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
        raise RetryableDeliveryError(f"http_{response.status_code}: {body_excerpt}")
    raise DeliveryConfigurationError(f"http_{response.status_code}: {body_excerpt}")


def _send_email(target: str, subject: str, message: str) -> dict:
    if not (settings.smtp_host and settings.smtp_from_email):
        raise DeliveryConfigurationError("SMTP is not configured")

    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = settings.smtp_from_email
    email["To"] = target
    email.set_content(message)

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=settings.request_timeout_seconds) as server:
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(email)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.request_timeout_seconds) as server:
                if settings.smtp_use_starttls:
                    server.starttls()
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(email)
    except OSError as exc:
        raise RetryableDeliveryError(str(exc)) from exc

    return {"detail": "Email accepted by SMTP server"}


def _send_twilio_whatsapp(target: str, message: str) -> dict:
    if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_whatsapp_from):
        raise DeliveryConfigurationError("Twilio WhatsApp is not configured")

    account_sid = settings.twilio_account_sid
    auth_token = settings.twilio_auth_token
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("utf-8")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = {
        "From": settings.twilio_whatsapp_from,
        "To": target,
        "Body": message,
    }

    try:
        response = httpx.post(
            url,
            data=payload,
            headers={"Authorization": f"Basic {auth}"},
            timeout=settings.request_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise RetryableDeliveryError(str(exc)) from exc

    body_excerpt = response.text[:400]
    _raise_for_http_status(response, body_excerpt)
    return {"status_code": response.status_code, "body": body_excerpt}


def _send_webhook(target: str, payload: dict) -> dict:
    try:
        response = httpx.post(target, json=payload, timeout=settings.request_timeout_seconds)
    except httpx.HTTPError as exc:
        raise RetryableDeliveryError(str(exc)) from exc

    body_excerpt = response.text[:400]
    _raise_for_http_status(response, body_excerpt)
    return {"status_code": response.status_code, "body": body_excerpt}


def _deliver(delivery: AlertDelivery, subscription: AlertSubscription, client: Client, event: Event) -> dict:
    message = delivery.message or _build_message(event)
    if subscription.channel == "email":
        return _send_email(subscription.target, f"TradeShield alert: {event.title[:120]}", message)
    if subscription.channel == "whatsapp":
        return _send_twilio_whatsapp(subscription.target, message)
    if subscription.channel == "webhook":
        return _send_webhook(subscription.target, _build_payload(client, event))
    return {"detail": "Available in dashboard inbox"}


def process_pending_alerts(session: Session, limit: int | None = None) -> AlertDispatchResult:
    batch_limit = limit or settings.alert_batch_size
    current_time = now_utc()
    deliveries = session.exec(
        select(AlertDelivery)
        .where(
            AlertDelivery.status.in_(["queued", "retry_scheduled"]),
            AlertDelivery.next_attempt_at <= current_time,
        )
        .order_by(AlertDelivery.created_at.asc())
        .limit(batch_limit)
    ).all()

    processed = delivered = retry = blocked = failed = 0
    for delivery in deliveries:
        processed += 1
        subscription = session.get(AlertSubscription, delivery.subscription_id)
        event = session.get(Event, delivery.event_id)
        client = session.get(Client, delivery.client_id)

        delivery.status = "processing"
        delivery.attempt_count += 1
        delivery.updated_at = now_utc()
        session.add(delivery)
        session.commit()

        if not subscription or not subscription.active:
            delivery.status = "blocked"
            delivery.last_error = "Subscription is missing or inactive"
            delivery.channel_response = {"detail": delivery.last_error}
            delivery.updated_at = now_utc()
            blocked += 1
            session.add(delivery)
            session.commit()
            continue
        if not event or not client:
            delivery.status = "failed"
            delivery.last_error = "Delivery dependencies are missing"
            delivery.channel_response = {"detail": delivery.last_error}
            delivery.updated_at = now_utc()
            failed += 1
            session.add(delivery)
            session.commit()
            continue

        try:
            response_payload = _deliver(delivery, subscription, client, event)
            delivery.status = "delivered"
            delivery.delivered_at = now_utc()
            delivery.last_error = None
            delivery.channel_response = response_payload
            delivered += 1
        except DeliveryConfigurationError as exc:
            logger.warning("Alert delivery blocked: %s", exc)
            delivery.status = "blocked"
            delivery.last_error = str(exc)
            delivery.channel_response = {"detail": str(exc)}
            blocked += 1
        except RetryableDeliveryError as exc:
            logger.warning("Alert delivery retry scheduled: %s", exc)
            if delivery.attempt_count >= settings.alert_max_attempts:
                delivery.status = "failed"
                delivery.last_error = str(exc)
                delivery.channel_response = {"detail": str(exc)}
                failed += 1
            else:
                delivery.status = "retry_scheduled"
                backoff = settings.alert_retry_backoff_seconds * (2 ** (delivery.attempt_count - 1))
                delivery.next_attempt_at = now_utc() + timedelta(seconds=backoff)
                delivery.last_error = str(exc)
                delivery.channel_response = {"detail": str(exc), "next_attempt_at": delivery.next_attempt_at.isoformat()}
                retry += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected alert delivery failure")
            if delivery.attempt_count >= settings.alert_max_attempts:
                delivery.status = "failed"
                delivery.last_error = str(exc)
                delivery.channel_response = {"detail": str(exc)}
                failed += 1
            else:
                delivery.status = "retry_scheduled"
                backoff = settings.alert_retry_backoff_seconds * (2 ** (delivery.attempt_count - 1))
                delivery.next_attempt_at = now_utc() + timedelta(seconds=backoff)
                delivery.last_error = str(exc)
                delivery.channel_response = {"detail": str(exc), "next_attempt_at": delivery.next_attempt_at.isoformat()}
                retry += 1

        delivery.updated_at = now_utc()
        session.add(delivery)
        session.commit()

    return AlertDispatchResult(
        processed_count=processed,
        delivered_count=delivered,
        retry_count=retry,
        blocked_count=blocked,
        failed_count=failed,
    )
