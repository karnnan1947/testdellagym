import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .gym_pt_session import EVENING_HOURS, MORNING_HOURS, format_hour

_logger = logging.getLogger(__name__)


class GymMembershipService(models.AbstractModel):
    """Shared engine called identically by Sales Orders and the POS."""
    _name = 'gym.membership.service'
    _description = 'Gym Membership Service'

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------
    @api.model
    def compute_end_date(self, product_id, start_date):
        product = product_id if isinstance(product_id, models.BaseModel) else \
            self.env['product.product'].browse(product_id)
        start = fields.Date.to_date(start_date)
        if not product or not start:
            return False
        return self.env['gym.membership']._end_date_for(product, start)

    @api.model
    def compute_end_dates(self, product_ids, start_date):
        """Batch helper for the POS modal: {product_id: 'YYYY-MM-DD'}."""
        return {
            pid: fields.Date.to_string(self.compute_end_date(pid, start_date))
            for pid in product_ids
        }

    # ------------------------------------------------------------------
    # Coach slots
    # ------------------------------------------------------------------
    @api.model
    def _coach_working_hours(self, coach, branch, weekday):
        shifts = coach.coach_shift_ids.filtered(
            lambda s: s.day_of_week == str(weekday) and (not branch or s.branch_id == branch))
        return shifts

    @api.model
    def _plan_session_dates(self, coach, branch, start_date, total_sessions, hour, end_date=False):
        """Next `total_sessions` coach working days from start_date (skipping off-days)."""
        dates = []
        if not total_sessions:
            return dates
        horizon = max(coach.booking_horizon_days or 30, 1)
        last_day = end_date or (start_date + timedelta(days=horizon - 1))
        day = start_date
        while day <= last_day and len(dates) < total_sessions:
            if not coach.coach_shift_ids:
                dates.append(day)
            else:
                shifts = self._coach_working_hours(coach, branch, day.weekday())
                if any(s.start_hour <= hour and hour + 1 <= s.end_hour for s in shifts):
                    dates.append(day)
            day += timedelta(days=1)
        return dates

    @api.model
    def _candidate_hours(self, coach, branch):
        if not coach or not coach.coach_shift_ids:
            return {'morning': list(MORNING_HOURS), 'evening': list(EVENING_HOURS)}
        hours = set()
        for shift in coach.coach_shift_ids.filtered(lambda s: not branch or s.branch_id == branch):
            h = shift.start_hour
            while h + 1 <= shift.end_hour:
                hours.add(h)
                h += 1
        return {
            'morning': sorted(h for h in hours if h < 14),
            'evening': sorted(h for h in hours if h >= 14),
        }

    @api.model
    def get_branch_coach_slots(self, branch_id, coach_id, start_date, total_sessions, end_date=False):
        """Coaches of the branch + morning/evening slots with conflict booleans."""
        branch = self.env['res.branch'].browse(branch_id) if branch_id else self.env['res.branch']
        coach_domain = [('is_coach', '=', True)]
        if branch:
            coach_domain.append(('allowed_branch_ids', 'in', branch.ids))
        # sudo: cashiers (no HR rights, branch-restricted) must see every booking of the coach
        coaches = self.env['hr.employee'].sudo().search(coach_domain)
        result = {
            'coaches': [{'id': c.id, 'name': c.name} for c in coaches],
            'morning': [],
            'evening': [],
        }
        coach = self.env['hr.employee'].sudo().browse(coach_id) if coach_id else self.env['hr.employee']
        start = fields.Date.to_date(start_date) if start_date else fields.Date.context_today(self)
        end = fields.Date.to_date(end_date) if end_date else False
        if not coach:
            return result
        Session = self.env['gym.pt.session'].sudo()
        for shift_key, hours in self._candidate_hours(coach, branch).items():
            for hour in hours:
                dates = self._plan_session_dates(coach, branch, start, total_sessions or 1, hour, end)
                booked = bool(dates) and bool(Session.search_count([
                    ('coach_id', '=', coach.id),
                    ('session_date', 'in', dates),
                    ('state', '!=', 'cancelled'),
                    ('start_hour', '<', hour + 1),
                    ('end_hour', '>', hour),
                ], limit=1))
                result[shift_key].append({
                    'hour': hour,
                    'label': f"{format_hour(hour)} - {format_hour(hour + 1)}",
                    'short_label': f"{int(hour) % 12 or 12:02d}-{int(hour + 1) % 12 or 12:02d}",
                    'booked': booked or not dates,
                })
        return result

    # ------------------------------------------------------------------
    # Finalize a sale (Sales Order confirmation or POS payment)
    # ------------------------------------------------------------------
    @api.model
    def finalize_membership_sale(self, partner, product, start_date, allowed_branches=None,
                                 branch=None, coach=None, slot_hour=0.0, amount_paid=0.0,
                                 sale_line=None, pos_line_id=False, invoice=None):
        """Create gym.membership, generate PT sessions, update member, trigger gate sync."""
        Membership = self.env['gym.membership']
        branch = branch or self.env['res.branch']
        allowed_branches = allowed_branches or self.env['res.branch']
        coach = coach or self.env['hr.employee']
        start = fields.Date.to_date(start_date) or fields.Date.context_today(self)

        if not partner.is_gym_member:
            partner.is_gym_member = True

        membership = Membership.create({
            'partner_id': partner.id,
            'product_id': product.id,
            'start_date': start,
            'branch_id': branch.id or False,
            'allowed_branch_ids': [(6, 0, allowed_branches.ids)],
            'coach_id': coach.id or False,
            'pt_slot_hour': slot_hour or 0.0,
            'amount_paid': amount_paid,
            'sale_line_id': sale_line.id if sale_line else False,
            'pos_order_line_id': pos_line_id or False,
            'invoice_id': invoice.id if invoice else False,
        })

        tmpl = product.product_tmpl_id
        if tmpl.membership_type in ('pt', 'class') and coach and tmpl.pt_total_sessions:
            self._generate_pt_sessions(membership, tmpl.pt_total_sessions)

        partner_vals = {}
        current = partner.current_membership_id
        if tmpl.membership_type == 'gym' or not current or current.state not in ('active', 'frozen'):
            partner_vals['current_membership_id'] = membership.id
        if allowed_branches:
            partner_vals['allowed_branch_ids'] = [(6, 0, allowed_branches.ids)]
        if partner_vals:
            partner.write(partner_vals)

        if tmpl.membership_type == 'gym' or partner.current_membership_id == membership:
            membership._gym_gate_push()
        return membership

    @api.model
    def _generate_pt_sessions(self, membership, total_sessions):
        Session = self.env['gym.pt.session']
        coach, branch, hour = membership.coach_id, membership.branch_id, membership.pt_slot_hour
        dates = self._plan_session_dates(coach, branch, membership.start_date, total_sessions, hour,
                                         membership.end_date)
        vals_list = [{
            'partner_id': membership.partner_id.id,
            'coach_id': coach.id,
            'branch_id': branch.id or False,
            'membership_id': membership.id,
            'session_date': day,
            'start_hour': hour,
            'end_hour': hour + 1,
            'session_number': idx,
        } for idx, day in enumerate(dates, start=1)]
        try:
            with self.env.cr.savepoint():
                Session.create(vals_list)
        except ValidationError as err:
            _logger.warning("PT session generation conflict for %s: %s", membership.name, err)
            membership.message_post(body=self.env._(
                "PT sessions could not be generated automatically (slot conflict): %s", err))
            membership.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=self.env._("Reschedule PT sessions (coach slot conflict)"))
        if len(dates) < total_sessions:
            membership.message_post(body=self.env._(
                "Only %(n)s of %(total)s PT sessions fit in the coach schedule before the end date.",
                n=len(dates), total=total_sessions))
