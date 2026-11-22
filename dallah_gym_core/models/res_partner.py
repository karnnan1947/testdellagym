from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_gym_member = fields.Boolean(string='Is Gym Member', index=True)
    member_id_code = fields.Char(string='Member Code', index=True, copy=False, readonly=True)
    qid_number = fields.Char(string='QID / National ID', index=True)
    current_membership_id = fields.Many2one('gym.membership', string='Active Plan', copy=False)
    membership_state = fields.Selection(
        [('none', 'None'), ('active', 'Active'), ('frozen', 'Frozen'),
         ('expired', 'Expired'), ('cancelled', 'Cancelled')],
        string='Membership Status', compute='_compute_membership_state', store=True, index=True)
    membership_start_date = fields.Date(
        string='Membership Start', related='current_membership_id.start_date', store=True)
    membership_end_date = fields.Date(
        string='Expires', related='current_membership_id.end_date', store=True)
    days_remaining = fields.Integer(string='Days Left', compute='_compute_days_remaining')
    allowed_branch_ids = fields.Many2many(
        'res.branch', 'res_partner_gym_branch_rel', 'partner_id', 'branch_id',
        string='Allowed Branches')
    zkbio_person_id = fields.Char(string='ZKBio Person ID', copy=False)
    zkbio_synced = fields.Boolean(string='ZKBio Synced', copy=False)
    zkbio_last_sync = fields.Datetime(string='ZKBio Last Sync', copy=False)
    gym_membership_ids = fields.One2many('gym.membership', 'partner_id', string='Memberships')
    freeze_log_ids = fields.One2many('gym.membership.freeze.log', 'partner_id', string='Freeze History')
    checkin_ids = fields.One2many('gym.member.checkin', 'partner_id', string='Gate Check-ins')
    pt_session_ids = fields.One2many('gym.pt.session', 'partner_id', string='PT Sessions')

    _member_id_code_uniq = models.Constraint('unique(member_id_code)', 'Member code must be unique.')

    @api.depends('current_membership_id', 'current_membership_id.state')
    def _compute_membership_state(self):
        for partner in self:
            partner.membership_state = partner.current_membership_id.state or 'none'

    def _gym_remaining_access_memberships(self, exclude=None):
        """Other memberships of the member that still give gate access (active, not excluded)."""
        self.ensure_one()
        return self.gym_membership_ids.filtered(
            lambda m: m.state == 'active' and m not in (exclude or self.env['gym.membership']))

    def _gym_repoint_current_membership(self, exclude=None):
        """Make the best remaining active membership the member's current one.

        Gate access is per member (one ZKBio person), so it must follow the member's
        remaining plans, not the single plan that was just refunded / frozen / expired.
        Gym-access plans win over PT/class, then the one ending last.
        Returns that membership (empty recordset when none is left).
        """
        self.ensure_one()
        remaining = self._gym_remaining_access_memberships(exclude)
        if not remaining:
            return remaining
        best = remaining.sorted(lambda m: (m.membership_type == 'gym', m.end_date or m.start_date))[-1]
        if self.current_membership_id != best:
            self.current_membership_id = best
        return best

    def _compute_days_remaining(self):
        today = fields.Date.context_today(self)
        for partner in self:
            end = partner.membership_end_date
            partner.days_remaining = max((end - today).days, 0) if end and partner.membership_state == 'active' else 0

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners.filtered(lambda p: p.is_gym_member and not p.member_id_code)._assign_member_code()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if vals.get('is_gym_member'):
            self.filtered(lambda p: p.is_gym_member and not p.member_id_code)._assign_member_code()
        return res

    def _assign_member_code(self):
        for partner in self:
            partner.member_id_code = self.env['ir.sequence'].next_by_code('gym.member.code')

    def _compute_display_name(self):
        super()._compute_display_name()
        for partner in self:
            if partner.member_id_code and self.env.context.get('show_member_code', True):
                partner.display_name = f"{partner.display_name} ({partner.member_id_code})"

    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        if value and operator in ('ilike', '=ilike', 'like', '=') and domain is not NotImplemented:
            domain = Domain.OR([
                Domain(domain),
                Domain('member_id_code', operator, value),
                Domain('qid_number', operator, value),
            ])
        return domain

    # ------------------------------------------------------------------
    # Member profile actions
    # ------------------------------------------------------------------
    def action_push_to_zkbio(self):
        """Admin override: push current branch turnstile access without re-invoicing."""
        self.ensure_one()
        if not self.current_membership_id:
            raise UserError(self.env._("This member has no membership to push."))
        self.current_membership_id.allowed_branch_ids = self.allowed_branch_ids
        self.current_membership_id._gym_gate_push()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'info', 'message': self.env._("Turnstile access update sent to ZKBio.")},
        }

    def action_open_freeze_wizard(self):
        self.ensure_one()
        if self.current_membership_id.state != 'active':
            raise UserError(self.env._("Only active memberships can be frozen."))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'gym.membership.freeze.wizard',
            'view_mode': 'form', 'target': 'new', 'name': self.env._("Freeze Membership"),
            'context': {'default_membership_id': self.current_membership_id.id},
        }

    def action_open_refund_wizard(self):
        self.ensure_one()
        if self.current_membership_id.state not in ('active', 'frozen'):
            raise UserError(self.env._("Only active or frozen memberships can be refunded."))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'gym.membership.refund.wizard',
            'view_mode': 'form', 'target': 'new', 'name': self.env._("Pro-Rata Refund"),
            'context': {'default_membership_id': self.current_membership_id.id},
        }

    def action_view_pt_sessions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dallah_gym_core.action_gym_pt_session')
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action
