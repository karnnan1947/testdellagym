import json
import logging
from datetime import datetime, time

import pytz
import requests

from odoo import api, fields, models

from .zkbio_sync_queue import MAX_RETRIES

_logger = logging.getLogger(__name__)

ENDPOINTS = {
    'ping': ('GET', '/api/v1/system/ping'),
    'sync': ('POST', '/api/v1/person/sync'),
    'suspend': ('POST', '/api/v1/person/disable'),
    'revoke': ('POST', '/api/v1/person/delete_access'),
    'transactions': ('GET', '/api/v1/acc/transactions/recent'),
}


class ZkbioApiService(models.AbstractModel):
    """REST client for ZKBio CVSecurity 6.0.0_R (Allied API).

    Every call is wrapped in try/except with a short timeout: a slow or offline
    turnstile server must never delay or crash POS payment / receipt printing.
    Failed calls go to zkbio.sync.queue and are retried by cron.
    """
    _name = 'zkbio.api.service'
    _description = 'ZKBio CVSecurity API Service'

    # ------------------------------------------------------------------
    # Low-level HTTP
    # ------------------------------------------------------------------
    @api.model
    def _get_config(self):
        icp = self.env['ir.config_parameter'].sudo()
        host = icp.get_str('dallah_gym_zkbio.server_ip').strip()
        port = icp.get_str('dallah_gym_zkbio.server_port').strip()
        base = host if host.startswith('http') else f"http://{host}"
        if port:
            base = f"{base}:{port}"
        return {
            'base_url': base if host else False,
            'token': icp.get_str('dallah_gym_zkbio.api_token'),
            'timeout': icp.get_int('dallah_gym_zkbio.timeout') or 5,
        }

    @api.model
    def _request(self, endpoint_key, payload=None, params=None):
        """Return (ok, json_or_error_message). Never raises."""
        cfg = self._get_config()
        if not cfg['base_url']:
            return False, self.env._("ZKBio server is not configured.")
        method, path = ENDPOINTS[endpoint_key]
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if cfg['token']:
            headers['Authorization'] = f"Bearer {cfg['token']}"
        try:
            response = requests.request(
                method, cfg['base_url'] + path, json=payload, params=params,
                headers=headers, timeout=cfg['timeout'])
        except requests.exceptions.RequestException as err:
            _logger.warning("ZKBio %s call failed: %s", endpoint_key, err)
            return False, str(err)
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}: {response.text[:500]}"
        try:
            body = response.json()
        except ValueError:
            body = {}
        if isinstance(body, dict) and body.get('code') not in (None, 0, '0', 200, '200'):
            return False, body.get('message') or json.dumps(body)[:500]
        return True, body

    @api.model
    def ping(self):
        ok, result = self._request('ping')
        icp = self.env['ir.config_parameter'].sudo()
        now_local = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        icp.set_str('dallah_gym_zkbio.last_ping', now_local.strftime('%d-%b-%Y %H:%M'))
        icp.set_bool('dallah_gym_zkbio.last_ping_ok', ok)
        if ok:
            return True, self.env._("🟢 Connected to ZKBio CVSecurity.")
        return False, self.env._("🔴 Connection failed: %s", result)

    # ------------------------------------------------------------------
    # Payloads
    # ------------------------------------------------------------------
    @api.model
    def _tz(self):
        return pytz.timezone(self.env.user.tz or 'Asia/Qatar')

    @api.model
    def _person_payload(self, partner, enabled=True):
        membership = partner.current_membership_id
        tz = self._tz()

        def fmt(day, t):
            return tz.localize(datetime.combine(day, t)).strftime('%Y-%m-%d %H:%M:%S') if day else False

        branches = partner.allowed_branch_ids or membership.allowed_branch_ids
        return {
            'pin': partner.member_id_code or str(partner.id),
            'name': partner.name,
            'national_id': partner.qid_number or '',
            'card_number': partner.zkbio_card_number or partner.qid_number or '',
            'start_time': fmt(membership.start_date, time.min),
            'end_time': fmt(membership.end_date, time(23, 59, 59)),
            'access_groups': [g for g in branches.mapped('zkbio_access_group_id') if g],
            'enabled': bool(enabled),
        }

    @api.model
    def _build_payload(self, action_type, partner):
        if action_type == 'sync':
            return self._person_payload(partner, enabled=partner.membership_state == 'active')
        return {'pin': partner.member_id_code or str(partner.id)}

    # ------------------------------------------------------------------
    # Business calls
    # ------------------------------------------------------------------
    @api.model
    def _execute(self, action_type, partner, enqueue=True, queue_item=None):
        """Call ZKBio; on failure optionally queue for retry. Returns (ok, error).

        A successful live call supersedes every older queued item of the member;
        a successful retry only supersedes items queued before it.
        """
        payload = self._build_payload(action_type, partner)
        ok, result = self._request(action_type, payload=payload)
        if ok:
            vals = {'zkbio_last_sync': fields.Datetime.now(), 'zkbio_synced': action_type == 'sync'}
            if action_type == 'sync' and isinstance(result, dict):
                person_id = (result.get('data') or {}).get('id') if isinstance(result.get('data'), dict) else None
                if person_id:
                    vals['zkbio_person_id'] = str(person_id)
            partner.sudo().write(vals)
            # A successful call supersedes older queued items of the member
            older = [('partner_id', '=', partner.id), ('state', '!=', 'done')]
            if queue_item:
                older.append(('id', '<', queue_item.id))
            self.env['zkbio.sync.queue'].sudo().search(older).write({'state': 'done', 'error_message': self.env._("Superseded by a later successful call.")})
            return True, False
        partner.sudo().write({'zkbio_synced': False})
        if enqueue:
            self.env['zkbio.sync.queue'].sudo().create({
                'partner_id': partner.id,
                'action_type': action_type,
                'payload_json': json.dumps(payload, default=str),
                'state': 'pending',
                'error_message': result,
                'last_attempt': fields.Datetime.now(),
            })
        return False, result

    @api.model
    def push_member_access(self, partner):
        """POST /api/v1/person/sync: register person, bind badge/QID, assign door access groups."""
        return self._execute('sync', partner)[0]

    @api.model
    def suspend_member_gates(self, partner):
        """POST /api/v1/person/disable (vacation freeze)."""
        return self._execute('suspend', partner)[0]

    @api.model
    def revoke_member_gates(self, partner):
        """POST /api/v1/person/delete_access (refund / cancellation)."""
        return self._execute('revoke', partner)[0]

    # ------------------------------------------------------------------
    # Gate scans import
    # ------------------------------------------------------------------
    @api.model
    def _parse_scan_time(self, value):
        if not value:
            return False
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=pytz.utc)
            return dt.replace(tzinfo=None)
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
            try:
                local = self._tz().localize(datetime.strptime(str(value)[:26].replace('Z', ''), fmt))
                return local.astimezone(pytz.utc).replace(tzinfo=None)
            except ValueError:
                continue
        return False

    @api.model
    def _match_branch(self, scan, branches):
        device = str(scan.get('device_name') or scan.get('dev_alias') or scan.get('device_sn') or '').lower()
        group = scan.get('access_group') or scan.get('acc_group_id')
        for branch in branches:
            if device and device in branch._zkbio_device_list():
                return branch
            if group and branch.zkbio_access_group_id == group:
                return branch
        return self.env['res.branch']

    @api.model
    def import_scans(self, scans):
        """Insert scan dicts into gym.member.checkin (dedup on transaction id and pin+timestamp)."""
        Checkin = self.env['gym.member.checkin'].sudo()
        Partner = self.env['res.partner'].sudo()
        branches = self.env['res.branch'].sudo().search([])
        created = Checkin.browse()
        seen = set()
        for scan in scans or []:
            ext_id = str(scan.get('id') or scan.get('transaction_id') or '')
            pin = scan.get('pin')
            when = self._parse_scan_time(scan.get('event_time') or scan.get('time'))
            if not pin or not when:
                continue
            key = ext_id or f"{pin}|{when}"
            if key in seen:
                continue
            seen.add(key)
            partner = Partner.search([('member_id_code', '=', pin)], limit=1)
            if ext_id and Checkin.search_count([('external_id', '=', ext_id)], limit=1):
                continue
            if not ext_id and Checkin.search_count([
                    ('partner_id', '=', partner.id), ('checkin_time', '=', when)], limit=1):
                continue
            result = str(scan.get('result') or scan.get('event_type') or 'granted').lower()
            granted = result in ('granted', 'success', '0', 'normal', 'true', '1', 'access granted')
            created |= Checkin.create({
                'partner_id': partner.id or False,
                'checkin_time': when,
                'branch_id': self._match_branch(scan, branches).id or False,
                'device_identifier': scan.get('door_name') or scan.get('device_name') or scan.get('device_sn'),
                'verification_mode': scan.get('verify_mode') or scan.get('verification_mode'),
                'access_result': 'granted' if granted else 'denied',
                'external_id': ext_id or False,
            })
        return created

    @api.model
    def fetch_realtime_gate_transactions(self):
        """GET /api/v1/acc/transactions/recent and import into gym.member.checkin."""
        ok, body = self._request('transactions')
        if not ok:
            _logger.info("ZKBio transactions not fetched: %s", body)
            return self.env['gym.member.checkin']
        scans = body.get('data', body) if isinstance(body, dict) else body
        if isinstance(scans, dict):
            scans = scans.get('items') or scans.get('records') or []
        return self.import_scans(scans if isinstance(scans, list) else [])

    # ------------------------------------------------------------------
    # Cron (every 10 minutes)
    # ------------------------------------------------------------------
    @api.model
    def _cron_process_zkbio_sync(self):
        queue = self.env['zkbio.sync.queue'].search([
            ('state', 'in', ('pending', 'failed')), ('retry_count', '<', MAX_RETRIES),
        ], order='create_date asc')
        queue._process()
        self.fetch_realtime_gate_transactions()
        return True
