from odoo import api, fields, models
from odoo.exceptions import UserError


class GymMembershipFreezeWizard(models.TransientModel):
    _name = 'gym.membership.freeze.wizard'
    _description = 'Membership Vacation Freeze Wizard'

    membership_id = fields.Many2one('gym.membership', string='Membership', required=True)
    partner_id = fields.Many2one(related='membership_id.partner_id')
    current_end_date = fields.Date(related='membership_id.end_date', string='Current Expiry')
    freeze_start_date = fields.Date(string='Freeze Start', required=True, default=fields.Date.context_today)
    freeze_end_date = fields.Date(string='Freeze End', required=True)
    freeze_days = fields.Integer(string='Frozen Days', compute='_compute_freeze_days')
    new_end_date = fields.Date(string='New Expiry', compute='_compute_freeze_days')
    reason = fields.Text(string='Reason')

    @api.depends('freeze_start_date', 'freeze_end_date', 'membership_id.end_date')
    def _compute_freeze_days(self):
        for wiz in self:
            if wiz.freeze_start_date and wiz.freeze_end_date and wiz.freeze_end_date >= wiz.freeze_start_date:
                wiz.freeze_days = (wiz.freeze_end_date - wiz.freeze_start_date).days + 1
            else:
                wiz.freeze_days = 0
            wiz.new_end_date = wiz.membership_id.end_date and fields.Date.add(
                wiz.membership_id.end_date, days=wiz.freeze_days)

    def action_confirm_freeze(self):
        self.ensure_one()
        membership = self.membership_id
        if membership.state != 'active':
            raise UserError(self.env._("Only active memberships can be frozen."))
        if self.freeze_days <= 0:
            raise UserError(self.env._("Freeze end date must be on or after the start date."))
        self.env['gym.membership.freeze.log'].create({
            'partner_id': membership.partner_id.id,
            'membership_id': membership.id,
            'freeze_start_date': self.freeze_start_date,
            'freeze_end_date': self.freeze_end_date,
            'freeze_days': self.freeze_days,
            'reason': self.reason,
        })
        membership.write({
            'end_date': fields.Date.add(membership.end_date, days=self.freeze_days),
            'is_frozen': True,
            'state': 'frozen',
        })
        membership.message_post(body=self.env._(
            "Membership frozen from %(start)s to %(end)s (%(days)s days). New expiry: %(expiry)s.",
            start=self.freeze_start_date, end=self.freeze_end_date, days=self.freeze_days,
            expiry=membership.end_date))
        membership._gym_gate_suspend()
        return {'type': 'ir.actions.act_window_close'}
