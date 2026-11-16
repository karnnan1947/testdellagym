import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ZkbioWebhook(http.Controller):
    """Optional real-time listener: ZKBio pushes gate scans as plain JSON.

    Header ``X-ZKBio-Token`` must match the Webhook Secret Token set in Settings.
    Body: a scan object, a list of scans, or {"data": [...]}.
    """

    @http.route('/zkbio/webhook/event', type='http', auth='none', methods=['POST'], csrf=False, save_session=False)
    def zkbio_event(self, **kwargs):
        secret = request.env['ir.config_parameter'].sudo().get_str('dallah_gym_zkbio.webhook_secret')
        token = request.httprequest.headers.get('X-ZKBio-Token', '')
        if not secret or not hmac.compare_digest(secret, token):
            return request.make_json_response({'status': 'error', 'message': 'unauthorized'}, status=401)
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except ValueError:
            return request.make_json_response({'status': 'error', 'message': 'invalid json'}, status=400)
        scans = body.get('data', [body]) if isinstance(body, dict) else body
        if isinstance(scans, dict):
            scans = [scans]
        created = request.env['zkbio.api.service'].sudo().import_scans(scans if isinstance(scans, list) else [])
        return request.make_json_response({'status': 'ok', 'imported': len(created)})
