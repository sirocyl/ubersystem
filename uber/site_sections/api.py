import re
from datetime import datetime
from inspect import getargspec, getmembers, ismethod

import cherrypy
import pytz
import stripe
from pockets import unwrap
from pockets.autolog import log
from sqlalchemy.orm import subqueryload

from uber.config import c
from uber.decorators import ajax, all_renderable, not_site_mappable, public, site_mappable
from uber.errors import HTTPRedirect
from uber.models import AdminAccount, ApiToken
from uber.utils import Charge, check


@all_renderable()
class Root:
    @site_mappable
    def index(self, session, show_revoked=False, message='', **params):
        admin_account = session.current_admin_account()
        api_tokens = session.query(ApiToken)
        if not admin_account.is_admin:
            api_tokens = api_tokens.filter_by(admin_account_id=admin_account.id)
        if not show_revoked:
            api_tokens = api_tokens.filter(ApiToken.revoked_time == None)  # noqa: E711
        api_tokens = api_tokens.options(
            subqueryload(ApiToken.admin_account)
            .subqueryload(AdminAccount.attendee)) \
            .order_by(ApiToken.issued_time).all()
        return {
            'message': message,
            'admin_account': admin_account,
            'api_tokens': api_tokens,
            'show_revoked': show_revoked,
        }

    def reference(self, session):
        from uber.server import jsonrpc_services as jsonrpc
        newlines = re.compile(r'(^|[^\n])\n([^\n]|$)')
        admin_account = session.current_admin_account()
        services = []
        for name in sorted(jsonrpc.keys()):
            service = jsonrpc[name]
            methods = []
            for method_name, method in getmembers(service, ismethod):
                if not method_name.startswith('_'):
                    method = unwrap(method)
                    doc = method.__doc__ or ''
                    args = getargspec(method).args
                    if 'self' in args:
                        args.remove('self')
                    access = getattr(method, 'required_access', set())
                    required_access = sorted([opt[4:].title() for opt in access])
                    methods.append({
                        'name': method_name,
                        'doc': newlines.sub(r'\1 \2', doc).strip(),
                        'args': args,
                        'required_access': required_access
                    })
            doc = service.__doc__ or ''
            services.append({
                'name': name,
                'doc': newlines.sub(r'\1 \2', doc).strip(),
                'methods': methods
            })

        return {
            'services': services,
            'admin_account': admin_account
        }

    @ajax
    def create_api_token(self, session, **params):
        if cherrypy.request.method == 'POST':
            params['admin_account_id'] = cherrypy.session.get('account_id')
            api_token = session.api_token(params)
            message = check(api_token)
            if not message:
                session.add(api_token)
                session.commit()
                return {'result': api_token.id}
            else:
                session.rollback()
                return {'error': message}
        else:
            return {'error': 'POST required'}

    def revoke_api_token(self, session, id=None):
        if not id or not cherrypy.request.method == 'POST':
            raise HTTPRedirect('index')

        api_token = session.api_token(id)
        api_token.revoked_time = datetime.now(pytz.UTC)
        raise HTTPRedirect(
            'index?message={}', 'Successfully revoked API token')

    @public
    @not_site_mappable
    def stripe_webhook_handler(self):
        if not cherrypy.request or not cherrypy.request.body:
            cherrypy.response.status = 400
            return "Request required"
        sig_header = cherrypy.request.headers.get('Stripe-Signature', '')
        payload = cherrypy.request.body.read()
        event = None

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, c.STRIPE_ENDPOINT_SECRET
            )
        except ValueError as e:
            cherrypy.response.status = 400
            return "Invalid payload: " + payload
        except stripe.error.SignatureVerificationError as e:
            cherrypy.response.status = 400
            return "Invalid signature: " + sig_header

        if not event:
            cherrypy.response.status = 400
            return "No event"

        if event and event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            matching_txns = Charge.mark_paid_from_stripe_id(payment_intent['id'])
            if not matching_txns:
                cherrypy.response.status = 400
                return "No matching Stripe transaction"
            cherrypy.response.status = 200
            return "Payment marked complete for payment intent ID " + payment_intent['id']
