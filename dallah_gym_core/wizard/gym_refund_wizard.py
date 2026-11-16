from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round


class GymMembershipRefundWizard(models.TransientModel):
    _name = 'gym.membership.refund.wizard'
    _description = 'Pro-Rata Cancellation & Refund Wizard'

    membership_id = fields.Many2one('gym.membership', string='Membership', required=True)
    partner_id = fields.Many2one(related='membership_id.partner_id')
    currency_id = fields.Many2one(related='membership_id.currency_id')
    cancellation_date = fields.Date(string='Cancellation Date', required=True, default=fields.Date.context_today)
    amount_paid = fields.Monetary(string='Amount Paid', currency_field='currency_id',
                                  compute='_compute_refund', store=True, readonly=False)
    total_plan_days = fields.Integer(string='Total Plan Days', compute='_compute_refund', store=True)
    days_consumed = fields.Integer(string='Days Consumed', compute='_compute_refund', store=True)
    daily_rate = fields.Monetary(string='Daily Rate', currency_field='currency_id', compute='_compute_refund', store=True)
    calculated_refund_amount = fields.Monetary(
        string='Refund Amount', currency_field='currency_id', compute='_compute_refund', store=True)
    reason = fields.Text(string='Reason')

    @api.depends('membership_id', 'cancellation_date', 'amount_paid')
    def _compute_refund(self):
        for wiz in self:
            membership = wiz.membership_id
            if not wiz.amount_paid and membership:
                wiz.amount_paid = membership.amount_paid
            frozen_days = sum(membership.freeze_log_ids.mapped('freeze_days'))
            if membership.start_date and membership.end_date:
                total = (membership.end_date - membership.start_date).days + 1 - frozen_days
            else:
                total = 0
            consumed = 0
            if membership.start_date and wiz.cancellation_date:
                consumed = (wiz.cancellation_date - membership.start_date).days + 1
                consumed -= sum(
                    (min(log.freeze_end_date, wiz.cancellation_date) - log.freeze_start_date).days + 1
                    for log in membership.freeze_log_ids if log.freeze_start_date <= wiz.cancellation_date)
            total = max(total, 0)
            consumed = min(max(consumed, 0), total)
            rate = (wiz.amount_paid / total) if total else 0.0
            wiz.total_plan_days = total
            wiz.days_consumed = consumed
            wiz.daily_rate = rate
            wiz.calculated_refund_amount = max(
                float_round(wiz.amount_paid - rate * consumed, precision_digits=2), 0.0)

    def _get_source_invoice(self):
        membership = self.membership_id
        if membership.invoice_id:
            return membership.invoice_id
        if membership.sale_line_id:
            return membership.sale_line_id.invoice_lines.move_id.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted')[:1]
        return self.env['account.move']

    def action_execute_refund(self):
        self.ensure_one()
        membership = self.membership_id
        if membership.state not in ('active', 'frozen'):
            raise UserError(self.env._("Only active or frozen memberships can be refunded."))
        invoice = self._get_source_invoice()
        line_vals = {
            'product_id': membership.product_id.id,
            'name': self.env._("Pro-rata refund %(ref)s (%(consumed)s / %(total)s days consumed)",
                               ref=membership.name, consumed=self.days_consumed, total=self.total_plan_days),
            'quantity': 1,
            'price_unit': self.calculated_refund_amount,
        }
        if invoice:
            src_line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == membership.product_id)[:1]
            if src_line:
                line_vals['tax_ids'] = [(6, 0, src_line.tax_ids.ids)]
                line_vals['account_id'] = src_line.account_id.id
        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': membership.partner_id.id,
            'invoice_date': self.cancellation_date,
            'reversed_entry_id': invoice.id or False,
            'ref': self.env._("Pro-rata refund of %s", membership.name),
            'invoice_line_ids': [(0, 0, line_vals)],
        })
        membership.write({'state': 'cancelled', 'refund_move_id': credit_note.id})
        membership.pt_session_ids.filtered(
            lambda s: s.state == 'scheduled' and s.session_date >= self.cancellation_date
        ).write({'state': 'cancelled'})
        membership.message_post(body=self.env._(
            "Membership cancelled on %(date)s. Refund %(amount)s %(cur)s. Reason: %(reason)s",
            date=self.cancellation_date, amount=self.calculated_refund_amount,
            cur=membership.currency_id.name, reason=self.reason or '-'))
        membership._gym_gate_revoke()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': credit_note.id,
            'view_mode': 'form', 'target': 'current',
        }
