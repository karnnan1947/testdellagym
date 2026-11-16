from odoo import fields, models


class GymMembershipFreezeLog(models.Model):
    _name = 'gym.membership.freeze.log'
    _description = 'Membership Vacation Freeze Log'
    _order = 'freeze_start_date desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Member', required=True, index=True)
    membership_id = fields.Many2one('gym.membership', string='Membership', required=True, ondelete='cascade', index=True)
    freeze_start_date = fields.Date(string='Freeze Start', required=True)
    freeze_end_date = fields.Date(string='Freeze End', required=True)
    freeze_days = fields.Integer(string='Frozen Days')
    reason = fields.Text(string='Reason')
    state = fields.Selection([('running', 'Running'), ('done', 'Done')], string='Status', default='running')
    processed_by = fields.Many2one('res.users', string='Processed By', default=lambda self: self.env.user)
