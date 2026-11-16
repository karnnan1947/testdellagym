from odoo import fields, models


class GymMemberCheckin(models.Model):
    """Member turnstile gate scans. Kept completely separate from hr.attendance."""
    _name = 'gym.member.checkin'
    _description = 'Member Turnstile Check-in'
    _order = 'checkin_time desc, id desc'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one('res.partner', string='Member', index=True, ondelete='cascade')
    checkin_time = fields.Datetime(string='Timestamp', required=True, index=True)
    branch_id = fields.Many2one('res.branch', string='Branch', index=True)
    device_identifier = fields.Char(string='Gate / Device')
    verification_mode = fields.Char(string='Verification Mode', help='Face, Palm, Card...')
    access_result = fields.Selection(
        [('granted', 'Access Granted'), ('denied', 'Access Denied')],
        string='Access Result', required=True, default='granted')
    external_id = fields.Char(string='External Transaction ID', index=True, copy=False)

    _external_id_uniq = models.Constraint(
        'unique(external_id)', 'This gate transaction was already imported.')
