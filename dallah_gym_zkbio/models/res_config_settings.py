from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    zkbio_server_ip = fields.Char(
        string='Server Host / IP', config_parameter='dallah_gym_zkbio.server_ip', default='192.168.1.100')
    zkbio_server_port = fields.Char(
        string='Port', config_parameter='dallah_gym_zkbio.server_port', default='8098')
    zkbio_api_token = fields.Char(string='API Bearer Token', config_parameter='dallah_gym_zkbio.api_token')
    zkbio_timeout = fields.Integer(string='Timeout (s)', config_parameter='dallah_gym_zkbio.timeout', default=5)
    zkbio_webhook_secret = fields.Char(
        string='Webhook Secret Token', config_parameter='dallah_gym_zkbio.webhook_secret',
        help='Value expected in the X-ZKBio-Token header of /zkbio/webhook/event calls.')
    zkbio_connection_status = fields.Char(string='Connection Status', compute='_compute_zkbio_connection_status')
    zkbio_branch_ids = fields.Many2many('res.branch', string='Branch Gate Door Mapping',
                                        compute='_compute_zkbio_branch_ids')

    def _compute_zkbio_connection_status(self):
        icp = self.env['ir.config_parameter'].sudo()
        ok = icp.get_bool('dallah_gym_zkbio.last_ping_ok')
        last = icp.get_str('dallah_gym_zkbio.last_ping')
        if not last:
            status = self.env._("⚪ Never tested")
        elif ok:
            status = self.env._("🟢 Connected (Last Ping: %s)", last)
        else:
            status = self.env._("🔴 Not reachable (Last Ping: %s)", last)
        for rec in self:
            rec.zkbio_connection_status = status

    def _compute_zkbio_branch_ids(self):
        branches = self.env['res.branch'].search([])
        for rec in self:
            rec.zkbio_branch_ids = branches

    def action_test_zkbio_connection(self):
        self.ensure_one()
        self.execute()  # persist the values typed before testing
        ok, message = self.env['zkbio.api.service'].ping()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success' if ok else 'danger',
                'sticky': True,
                'title': self.env._("ZKBio CVSecurity"),
                'message': message,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_open_zkbio_branch_mapping(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': 'res.branch', 'name': self.env._("Branch Gate Door Mapping"),
            'view_mode': 'list,form',
            'views': [(self.env.ref('dallah_gym_zkbio.view_res_branch_zkbio_mapping_list').id, 'list'), (False, 'form')],
        }
