"""
Transactional email for Eng-Mart.

Delivery goes through Django's SMTP backend, configured for SendGrid's relay in
``config.settings``. Two rules govern everything in this module:

1. **Email must never break a business action.** Every send is wrapped so that a
   failed or misconfigured mail server cannot roll back an order or an inquiry.
2. **Sending happens off the request thread**, so a slow SMTP handshake does not
   make the customer wait at checkout.
"""
import logging
import threading

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def _store_name():
    """Store name from SiteSettings, falling back to a sane default."""
    try:
        from apps.site_settings.models import SiteSettings
        return SiteSettings.load().name or 'Eng-Mart'
    except Exception:  # settings row missing, DB unavailable, etc.
        return 'Eng-Mart'


def _deliver(subject, body, to, html=None, reply_to=None):
    """Send one message. Swallows and logs every error by design."""
    recipients = [addr for addr in (to if isinstance(to, (list, tuple)) else [to]) if addr]
    if not recipients:
        return False
    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
            reply_to=[reply_to] if reply_to else None,
        )
        if html:
            message.attach_alternative(html, 'text/html')
        message.send(fail_silently=False)
        logger.info('Sent email "%s" to %s', subject, ', '.join(recipients))
        return True
    except Exception:
        # Never propagate — the caller's transaction matters more than the email.
        logger.exception('Failed to send email "%s" to %s', subject, ', '.join(recipients))
        return False


def send_async(subject, body, to, html=None, reply_to=None):
    """Queue a message on a daemon thread so the request returns immediately."""
    thread = threading.Thread(
        target=_deliver,
        args=(subject, body, to),
        kwargs={'html': html, 'reply_to': reply_to},
        daemon=True,
    )
    thread.start()
    return thread


# ─── Inquiries ────────────────────────────────────────────────

def send_inquiry_emails(inquiry):
    """Acknowledge the customer's inquiry and alert the sales inbox."""
    store = _store_name()
    product = inquiry.product_interest or 'General inquiry'

    # 1. Acknowledgement to the customer — replies go to the sales inbox
    send_async(
        reply_to=settings.REPLY_TO_EMAIL,
        subject=f'We received your inquiry — {store}',
        body=(
            f'Hi {inquiry.name},\n\n'
            f'Thank you for contacting {store}. We have received your inquiry '
            f'and our team will get back to you shortly.\n\n'
            f'Product of interest: {product}\n'
            f'Your message:\n{inquiry.message}\n\n'
            f'Regards,\n{store} Sales Team'
        ),
        to=inquiry.email,
    )

    # 2. Notification to the sales team (reply-to goes straight to the customer)
    send_async(
        subject=f'New inquiry from {inquiry.name} — {product}',
        body=(
            f'A new inquiry was submitted on the website.\n\n'
            f'Name:    {inquiry.name}\n'
            f'Company: {inquiry.company or "—"}\n'
            f'Email:   {inquiry.email}\n'
            f'Phone:   {inquiry.phone or "—"}\n'
            f'Product: {product}\n\n'
            f'Message:\n{inquiry.message}\n\n'
            f'Open the admin inbox: {settings.FRONTEND_URL}/admin/queries'
        ),
        to=settings.SALES_NOTIFICATION_EMAIL,
        reply_to=inquiry.email,
    )


# ─── Quotations (RFQ) ─────────────────────────────────────────

def _quote_lines(quotation):
    lines = []
    for item in quotation.items.all():
        label = item.product_name
        if item.cat_no:
            label += f' ({item.cat_no})'
        if item.quoted_price is not None:
            lines.append(f'  - {label} x{item.quantity} @ PKR {item.quoted_price:,.0f} = PKR {item.line_total:,.0f}')
        else:
            lines.append(f'  - {label} x{item.quantity} — price to be quoted')
    return '\n'.join(lines) or '  (no items listed)'


def send_quotation_request_emails(quotation):
    """Acknowledge a new quote request and alert the sales inbox."""
    store = _store_name()
    items = _quote_lines(quotation)

    # 1. Acknowledgement to the customer
    send_async(
        reply_to=settings.REPLY_TO_EMAIL,
        subject=f'Quote request {quotation.quote_number} received — {store}',
        body=(
            f'Hi {quotation.name},\n\n'
            f'Thank you for your quote request. Our sales team is preparing your '
            f'pricing and will send it shortly.\n\n'
            f'Reference: {quotation.quote_number}\n\n'
            f'Items requested:\n{items}\n\n'
            + (f'Your notes:\n{quotation.notes}\n\n' if quotation.notes else '')
            + f'Regards,\n{store} Sales Team'
        ),
        to=quotation.email,
    )

    # 2. Notification to the sales team
    send_async(
        subject=f'New quote request {quotation.quote_number} — {quotation.name}',
        body=(
            f'A new quote request was submitted on the website.\n\n'
            f'Reference: {quotation.quote_number}\n'
            f'Name:      {quotation.name}\n'
            f'Company:   {quotation.company or "—"}\n'
            f'Email:     {quotation.email}\n'
            f'Phone:     {quotation.phone or "—"}\n'
            f'Source:    {quotation.get_source_display()}\n\n'
            f'Items requested:\n{items}\n\n'
            + (f'Customer notes:\n{quotation.notes}\n\n' if quotation.notes else '')
            + f'Prepare the quote here: {settings.FRONTEND_URL}/admin/quotations'
        ),
        to=settings.SALES_NOTIFICATION_EMAIL,
        reply_to=quotation.email,
    )


def send_quotation_ready_email(quotation):
    """Send the finished quote — with prices — to the customer."""
    store = _store_name()
    items = _quote_lines(quotation)
    validity = (
        f'This quote is valid until {quotation.valid_until:%d %B %Y}.\n\n'
        if quotation.valid_until else ''
    )

    send_async(
        reply_to=settings.REPLY_TO_EMAIL,
        subject=f'Your quotation {quotation.quote_number} — {store}',
        body=(
            f'Hi {quotation.name},\n\n'
            f'Please find your quotation below.\n\n'
            f'Reference: {quotation.quote_number}\n\n'
            f'{items}\n\n'
            f'Total: PKR {quotation.quoted_total:,.0f}\n\n'
            f'{validity}'
            f'To proceed, simply reply to this email and our team will confirm '
            f'availability and delivery.\n\n'
            f'Regards,\n{store} Sales Team'
        ),
        to=quotation.email,
    )


# ─── Orders ───────────────────────────────────────────────────

def _order_lines(order):
    lines = []
    for item in order.items.all():
        price = 'On request' if item.is_price_on_request else f'PKR {item.unit_price:,.0f}'
        label = item.product_name
        if item.cat_no:
            label += f' ({item.cat_no})'
        lines.append(f'  - {label} x{item.quantity} @ {price}')
    return '\n'.join(lines) or '  (no items)'


def send_payment_slip_notification(order):
    """Tell the sales team a bank-transfer receipt is waiting for verification."""
    store = _store_name()
    send_async(
        subject=f'Payment slip uploaded for {order.order_number} — PKR {order.total:,.0f}',
        body=(
            f'A customer uploaded proof of payment.\n\n'
            f'Order:     {order.order_number}\n'
            f'Customer:  {order.customer_name}\n'
            f'Email:     {order.customer_email}\n'
            f'Phone:     {order.customer_phone}\n'
            f'Amount:    PKR {order.total:,.0f}\n'
            f'Reference: {order.payment_reference or "—"}\n\n'
            f'Verify the receipt, then mark the order paid here:\n'
            f'{settings.FRONTEND_URL}/admin/orders'
        ),
        to=settings.SALES_NOTIFICATION_EMAIL,
        reply_to=order.customer_email,
    )


def send_inquiry_reply_email(inquiry, reply_text):
    """
    Send the shop's reply to the customer who raised the inquiry.

    The admin panel used to only flip the status to "replied" and pop an alert
    claiming the reply was sent — the text was thrown away and nothing left the
    building. This is what actually delivers it.
    """
    store = _store_name()
    send_async(
        reply_to=settings.REPLY_TO_EMAIL,
        subject=f'Re: your enquiry — {store}',
        body=(
            f'Hi {inquiry.name},\n\n'
            f'{reply_text}\n\n'
            f'------------------------------\n'
            f'Your original message:\n{inquiry.message}\n'
            f'------------------------------\n\n'
            f'Just reply to this email if you need anything else.\n\n'
            f'Regards,\n{store} Sales Team'
        ),
        html=(
            f'<p>Hi {inquiry.name},</p>'
            f'<div style="white-space:pre-wrap">{reply_text}</div>'
            f'<hr style="border:none;border-top:1px solid #E2E8F0;margin:18px 0">'
            f'<p style="color:#64748B;font-size:13px"><strong>Your original message:</strong><br>'
            f'<span style="white-space:pre-wrap">{inquiry.message}</span></p>'
            f'<p style="color:#64748B;font-size:13px">Just reply to this email if you need '
            f'anything else.</p>'
            f'<p>Regards,<br>{store} Sales Team</p>'
        ),
        to=inquiry.email,
    )


def send_password_reset_email(user, uid, token):
    """Email a single-use password reset link."""
    store = _store_name()
    link = f'{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}'
    name = user.first_name or user.username

    send_async(
        reply_to=settings.REPLY_TO_EMAIL,
        subject=f'Reset your {store} password',
        body=(
            f'Hi {name},\n\n'
            f'We received a request to reset the password for your {store} account.\n\n'
            f'Click the link below to choose a new password:\n\n{link}\n\n'
            f'This link can only be used once and expires shortly.\n\n'
            f'If you did not ask for this, you can ignore this email — your '
            f'password will not change.\n\n'
            f'Regards,\n{store} Team'
        ),
        html=(
            f'<p>Hi {name},</p>'
            f'<p>We received a request to reset the password for your {store} account.</p>'
            f'<p><a href="{link}" style="display:inline-block;background:#2563EB;color:#fff;'
            f'padding:12px 22px;border-radius:8px;font-weight:700;text-decoration:none">'
            f'Choose a new password</a></p>'
            f'<p style="color:#64748B;font-size:13px">Or paste this into your browser:<br>'
            f'<a href="{link}">{link}</a></p>'
            f'<p style="color:#64748B;font-size:13px">This link can only be used once and '
            f'expires shortly. If you did not ask for this, you can ignore this email — '
            f'your password will not change.</p>'
            f'<p>Regards,<br>{store} Team</p>'
        ),
        to=user.email,
    )


def send_order_status_email(order, cancelled_by_customer=False, return_requested=False):
    """
    Tell the shop when a customer cancels or asks to return an order.

    Without this the change lives only in the database and the team keeps
    preparing an order the customer has already cancelled.
    """
    store = _store_name()
    if cancelled_by_customer:
        what, action = 'cancelled', 'cancelled this order'
    elif return_requested:
        what, action = 'return requested for', 'requested a return for this order'
    else:
        what, action = 'updated', 'updated this order'

    # 1. Alert the sales inbox — this is the one that matters operationally.
    send_async(
        subject=f'Customer {what} order {order.order_number} — {store}',
        body=(
            f'{order.customer_name} has {action}.\n\n'
            f'Order number: {order.order_number}\n'
            f'Customer: {order.customer_name}\n'
            f'Phone: {order.customer_phone}\n'
            f'Email: {order.customer_email}\n'
            f'Order total: PKR {order.total:,.0f}\n\n'
            f'Items:\n{_order_lines(order)}\n\n'
            f'Open the admin panel to review it.'
        ),
        to=settings.SALES_NOTIFICATION_EMAIL,
        reply_to=order.customer_email or None,
    )

    # 2. Acknowledge to the customer so they know it registered.
    if order.customer_email:
        send_async(
            reply_to=settings.REPLY_TO_EMAIL,
            subject=f'Order {order.order_number} — {what} — {store}',
            body=(
                f'Hi {order.customer_name},\n\n'
                f'We have received your request and your order {order.order_number} '
                f'is now marked as "{order.get_status_display()}".\n\n'
                f'If this was not you, or you would like to discuss it, just reply '
                f'to this email.\n\n'
                f'Regards,\n{store} Sales Team'
            ),
            to=order.customer_email,
        )


def send_order_emails(order):
    """Confirm the order to the customer and alert the sales inbox."""
    store = _store_name()
    items = _order_lines(order)
    totals = (
        f'Subtotal: PKR {order.subtotal:,.0f}\n'
        f'Discount: PKR {order.discount_amount:,.0f}\n'
        f'Total:    PKR {order.total:,.0f}'
    )

    # 1. Confirmation to the customer — replies go to the sales inbox
    send_async(
        reply_to=settings.REPLY_TO_EMAIL,
        subject=f'Order {order.order_number} confirmed — {store}',
        body=(
            f'Hi {order.customer_name},\n\n'
            f'Thank you for your order with {store}. We have received it and '
            f'our team will contact you to confirm delivery details.\n\n'
            f'Order number: {order.order_number}\n'
            f'Payment method: {order.get_payment_method_display()}\n\n'
            f'Items:\n{items}\n\n{totals}\n\n'
            f'Delivery address:\n{order.shipping_address}\n\n'
            f'Regards,\n{store} Sales Team'
        ),
        to=order.customer_email,
    )

    # 2. Notification to the sales team
    send_async(
        subject=f'New order {order.order_number} — PKR {order.total:,.0f}',
        body=(
            f'A new order was placed on the website.\n\n'
            f'Order:   {order.order_number}\n'
            f'Name:    {order.customer_name}\n'
            f'Company: {order.company_name or "—"}\n'
            f'Email:   {order.customer_email}\n'
            f'Phone:   {order.customer_phone}\n'
            f'Payment: {order.get_payment_method_display()}\n\n'
            f'Items:\n{items}\n\n{totals}\n\n'
            f'Address:\n{order.shipping_address}\n'
            f'City: {order.city or "—"}\n\n'
            f'Manage it here: {settings.FRONTEND_URL}/admin/orders'
        ),
        to=settings.SALES_NOTIFICATION_EMAIL,
        reply_to=order.customer_email,
    )
