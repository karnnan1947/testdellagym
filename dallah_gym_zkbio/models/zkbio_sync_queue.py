import json

from odoo import api, fields, models

MAX_RETRIES = 5


class ZkbioSyncQueue(models.Model):
    """Retry queue: if ZKBio is unreachable, the POS / sale never blocks; the call is retried by cron."""
    _name = 'zkbio.sync.queue'
    _description = 'ZKBio Sync Retry Queue'
    _order = 'create_date desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Member', required=True, index=True, ondelete='cascade')
    action_type = fields.Selection(
        [('sync', 'Sync Access'), ('suspend', 'Suspend'), ('revoke', 'Revoke')],
        string='Action', required=True, default='sync')
    payload_json = fields.Text(string='Payload')
    state = fields.Selection(
        [('pending', 'Pending'), ('done', 'Done'), ('failed', 'Failed')],
        string='Status', default='pending', required=True, index=True)
    retry_count = fields.Integer(string='Retries', default=0)
    error_message = fields.Text(string='Last Error')
    last_attempt = fields.Datetime(string='Last Attempt')

    def _payload(self):
        self.ensure_one()
        try:
            return json.loads(self.payload_json or '{}')
        except ValueError:
            return {}

    def action_retry_now(self):
        """Manual 'Retry Now' (ignores the retry ceiling)."""
        self._process(force=True)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success' if all(q.state == 'done' for q in self) else 'warning',
                'message': self.env._("%(done)s of %(total)s queued sync(s) succeeded.",
                                      done=len(self.filtered(lambda q: q.state == 'done')), total=len(self)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _process(self, force=False):
        Service = self.env['zkbio.api.service']
        for item in self.sorted('id'):
            if item.state == 'done' or (not force and item.retry_count >= MAX_RETRIES):
                continue
            # Always rebuild sync payloads from the partner's current state (dates may have changed)
            ok, error = Service._execute(item.action_type, item.partner_id, enqueue=False, queue_item=item)
            vals = {'last_attempt': fields.Datetime.now(), 'retry_count': item.retry_count + 1}
            if ok:
                vals.update(state='done', error_message=False)
            else:
                vals.update(state='failed', error_message=error)
            item.write(vals)
