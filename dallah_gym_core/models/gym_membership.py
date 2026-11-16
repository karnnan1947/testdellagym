import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class GymMembership(models.Model):
    _name = 'gym.membership'
    _description = 'Gym Membership Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='/')
    partner_id = fields.Many2one('res.partner', string='Member', required=True, index=True, tracking=True)
    product_id = fields.Many2one(
        'product.product', string='Plan', required=True, tracking=True,
        domain=[('is_gym_membership', '=', True)])
    membership_type = fields.Selection(related='product_id.membership_type', store=True)
    branch_id = fields.Many2one('res.branch', string='Sales Branch', index=True)
    allowed_branch_ids = fields.Many2many(
        'res.branch', 'gym_membership_branch_rel', 'membership_id', 'branch_id',
        string='Allowed Gate Branches')
    start_date = fields.Date(string='Start Date', required=True, default=fields.Date.context_today, tracking=True)
    end_date = fields.Date(
        string='End Date', compute='_compute_end_date', store=True, readonly=False, tracking=True)
    state = fields.Selection(
        [('active', 'Active'), ('frozen', 'Frozen'), ('expired', 'Expired'), ('cancelled', 'Cancelled')],
        string='Status', default='active', required=True, tracking=True, index=True)
    is_frozen = fields.Boolean(string='Frozen', copy=False)
    amount_paid = fields.Monetary(string='Amount Paid', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    coach_id = fields.Many2one('hr.employee', string='Assigned Coach', domain=[('is_coach', '=', True)])
    pt_slot_hour = fields.Float(string='Time Slot')
    sale_line_id = fields.Many2one('sale.order.line', string='Sales Order Line', copy=False, index='btree_not_null')
    pos_order_line_id = fields.Integer(string='POS Order Line ID', copy=False, index='btree_not_null')
    invoice_id = fields.Many2one('account.move', string='Invoice', copy=False)
    refund_move_id = fields.Many2one('account.move', string='Credit Note', copy=False)
    freeze_log_ids = fields.One2many('gym.membership.freeze.log', 'membership_id', string='Freeze History')
    pt_session_ids = fields.One2many('gym.pt.session', 'membership_id', string='PT Sessions')
    days_remaining = fields.Integer(string='Days Left', compute='_compute_days_remaining')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('gym.membership') or '/'
        return super().create(vals_list)

    @api.depends('start_date', 'product_id')
    def _compute_end_date(self):
        for rec in self:
            if rec.start_date and rec.product_id:
                rec.end_date = rec._end_date_for(rec.product_id, rec.start_date)
            elif not rec.end_date:
                rec.end_date = False

    @api.model
    def _end_date_for(self, product, start_date):
        """start + duration - 1 day (e.g. 2026-10-22 + 1 month -> 2026-11-21)."""
        tmpl = product.product_tmpl_id if product._name == 'product.product' else product
        value = tmpl.membership_duration_val or 0
        unit = tmpl.membership_duration_unit or 'months'
        if not value:
            return start_date
        delta = relativedelta(**{unit: value})
        return start_date + delta - timedelta(days=1)

    def _compute_days_remaining(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.days_remaining = max((rec.end_date - today).days, 0) if rec.end_date else 0

    # ------------------------------------------------------------------
    # Biometric hooks (implemented by dallah_gym_zkbio)
    # ------------------------------------------------------------------
    def _gym_gate_push(self):
        """Grant / update turnstile access. Overridden by dallah_gym_zkbio."""
        return True

    def _gym_gate_suspend(self):
        """Suspend turnstile access (freeze). Overridden by dallah_gym_zkbio."""
        return True

    def _gym_gate_revoke(self):
        """Revoke turnstile access (refund / cancellation). Overridden by dallah_gym_zkbio."""
        return True

    # ------------------------------------------------------------------
    # Crons
    # ------------------------------------------------------------------
    @api.model
    def _cron_restore_frozen_memberships(self):
        """Daily 00:05: restore memberships whose freeze period ended, re-enable turnstiles.

        Also moves memberships past their end date to 'expired'.
        """
        today = fields.Date.context_today(self)
        frozen = self.search([('state', '=', 'frozen')])
        to_restore = self.browse()
        for membership in frozen:
            running = membership.freeze_log_ids.filtered(lambda l: l.state == 'running')
            if running and all(log.freeze_end_date < today for log in running):
                running.write({'state': 'done'})
                to_restore |= membership
        if to_restore:
            to_restore.write({'state': 'active', 'is_frozen': False})
            for membership in to_restore:
                membership.message_post(body=self.env._("Freeze ended, membership restored."))
                membership._gym_gate_push()
        # Expired contracts: turnstile end_time already stops access, no revoke call needed
        expired = self.search([('state', '=', 'active'), ('end_date', '<', today)])
        if expired:
            expired.write({'state': 'expired'})
        return True

    @api.model
    def _cron_send_expiry_reminders(self):
        """Daily 08:00: e-mail members whose days left == plan reminder lead."""
        template = self.env.ref('dallah_gym_core.mail_template_gym_renewal_reminder', raise_if_not_found=False)
        if not template:
            return False
        today = fields.Date.context_today(self)
        for membership in self.search([('state', '=', 'active'), ('end_date', '>=', today)]):
            lead = membership.product_id.reminder_days_before
            if lead and (membership.end_date - today).days == lead and membership.partner_id.email:
                template.send_mail(membership.id, force_send=False)
        return True
