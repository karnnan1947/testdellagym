from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

MORNING_HOURS = [9.0, 10.0, 11.0, 12.0]
EVENING_HOURS = [16.0, 17.0, 18.0, 19.0]


def format_hour(hour):
    h = int(hour)
    m = int(round((hour - h) * 60))
    suffix = 'AM' if h < 12 else 'PM'
    h12 = h % 12 or 12
    return f"{h12:02d}:{m:02d} {suffix}"


class GymPtSession(models.Model):
    _name = 'gym.pt.session'
    _description = 'Personal Training Session'
    _inherit = ['mail.thread']
    _order = 'session_date, start_hour, coach_id'

    name = fields.Char(compute='_compute_name', store=True)
    partner_id = fields.Many2one('res.partner', string='Member', required=True, index=True, tracking=True)
    coach_id = fields.Many2one(
        'hr.employee', string='Coach', required=True, index=True, tracking=True,
        domain=[('is_coach', '=', True)])
    branch_id = fields.Many2one('res.branch', string='Branch', index=True, tracking=True)
    membership_id = fields.Many2one('gym.membership', string='Membership', ondelete='cascade', index=True)
    session_date = fields.Date(string='Date', required=True, index=True, tracking=True)
    start_hour = fields.Float(string='Start Hour', required=True, tracking=True)
    end_hour = fields.Float(string='End Hour', required=True)
    session_number = fields.Integer(string='Session #')
    state = fields.Selection(
        [('scheduled', 'Scheduled'), ('ongoing', 'Ongoing'), ('done', 'Done'),
         ('no_show', 'No Show'), ('cancelled', 'Cancelled')],
        string='Status', default='scheduled', required=True, tracking=True, index=True)
    # Datetime pair used by the native calendar view (drag & drop rescheduling)
    start_datetime = fields.Datetime(
        string='Start', compute='_compute_datetimes', inverse='_inverse_datetimes', store=True)
    stop_datetime = fields.Datetime(
        string='End', compute='_compute_datetimes', inverse='_inverse_datetimes', store=True)

    @api.depends('partner_id', 'coach_id', 'session_number')
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.partner_id.name or ''} / {rec.coach_id.name or ''}" + (
                f" #{rec.session_number}" if rec.session_number else '')

    def _tz(self):
        return pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'Asia/Qatar')

    @api.depends('session_date', 'start_hour', 'end_hour')
    def _compute_datetimes(self):
        tz = self._tz()
        for rec in self:
            if not rec.session_date:
                rec.start_datetime = rec.stop_datetime = False
                continue
            rec.start_datetime = self._to_utc(tz, rec.session_date, rec.start_hour)
            rec.stop_datetime = self._to_utc(tz, rec.session_date, rec.end_hour or rec.start_hour + 1)

    @staticmethod
    def _to_utc(tz, day, hour):
        h = int(hour)
        m = int(round((hour - h) * 60))
        local = tz.localize(datetime.combine(day, time(min(h, 23), m)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _inverse_datetimes(self):
        tz = self._tz()
        for rec in self:
            if not rec.start_datetime:
                continue
            start = pytz.utc.localize(rec.start_datetime).astimezone(tz)
            duration = 1.0
            if rec.stop_datetime:
                duration = max((rec.stop_datetime - rec.start_datetime).total_seconds() / 3600.0, 0.5)
            rec.session_date = start.date()
            rec.start_hour = start.hour + start.minute / 60.0
            rec.end_hour = rec.start_hour + duration

    @api.onchange('start_hour')
    def _onchange_start_hour(self):
        if self.start_hour and (not self.end_hour or self.end_hour <= self.start_hour):
            self.end_hour = self.start_hour + 1

    @api.constrains('coach_id', 'session_date', 'start_hour', 'end_hour', 'state')
    def _check_coach_double_booking(self):
        for rec in self:
            if rec.state == 'cancelled':
                continue
            # sudo: a coach's bookings in other branches must count even if hidden by branch rules
            conflict = self.sudo().search_count([
                ('id', '!=', rec.id),
                ('coach_id', '=', rec.coach_id.id),
                ('session_date', '=', rec.session_date),
                ('state', '!=', 'cancelled'),
                ('start_hour', '<', rec.end_hour),
                ('end_hour', '>', rec.start_hour),
            ], limit=1)
            if conflict:
                raise ValidationError(self.env._(
                    "Coach %(coach)s is already booked on %(date)s at %(hour)s.",
                    coach=rec.coach_id.name, date=rec.session_date, hour=format_hour(rec.start_hour)))

    # ------------------------------------------------------------------
    # PT Reception Floor Board (OWL client action)
    # ------------------------------------------------------------------
    @api.model
    def get_reception_board_data(self, branch_id=False, date_str=False, search_query=False):
        day = fields.Date.to_date(date_str) if date_str else fields.Date.context_today(self)
        branches = self.env['res.branch'].search([])
        branch = self.env['res.branch'].browse(branch_id) if branch_id else branches[:1]
        coach_domain = [('is_coach', '=', True)]
        if branch:
            coach_domain.append(('allowed_branch_ids', 'in', branch.ids))
        coaches = self.env['hr.employee'].search(coach_domain)
        session_domain = [('session_date', '=', day), ('state', '!=', 'cancelled')]
        if branch:
            session_domain.append(('branch_id', '=', branch.id))
        sessions = self.search(session_domain)

        query = (search_query or '').strip().lower()
        hours = {'morning': MORNING_HOURS, 'evening': EVENING_HOURS}
        grid = {}
        weekday = str(day.weekday())
        for coach in coaches:
            shifts = coach.coach_shift_ids.filtered(
                lambda s: s.day_of_week == weekday and (not branch or s.branch_id == branch))
            for shift_key, shift_hours in hours.items():
                cells = []
                for hour in shift_hours:
                    session = sessions.filtered(
                        lambda s: s.coach_id == coach and s.start_hour <= hour < s.end_hour)[:1]
                    on_shift = not coach.coach_shift_ids or any(
                        s.start_hour <= hour < s.end_hour for s in shifts)
                    match = bool(query and session and (
                        query in (session.partner_id.name or '').lower()
                        or query in (session.partner_id.member_id_code or '').lower()))
                    cells.append({
                        'hour': hour,
                        'label': format_hour(hour),
                        'session_id': session.id or False,
                        'member': session.partner_id.name or '',
                        'member_code': session.partner_id.member_id_code or '',
                        'state': session.state or '',
                        'available': on_shift and not session,
                        'off_shift': not on_shift,
                        'highlight': match,
                    })
                grid.setdefault(shift_key, []).append({
                    'coach_id': coach.id, 'coach_name': coach.name, 'cells': cells})

        return {
            'date': fields.Date.to_string(day),
            'branch_id': branch.id or False,
            'branches': [{'id': b.id, 'name': b.display_name} for b in branches],
            'hours': {k: [{'hour': h, 'label': format_hour(h)} for h in v] for k, v in hours.items()},
            'grid': grid,
            'kpi': {
                'total_today': len(sessions),
                'free_slots': sum(1 for rows in grid.values() for r in rows for c in r['cells'] if c['available']),
                'ongoing': len(sessions.filtered(lambda s: s.state == 'ongoing')),
            },
        }

    @api.model
    def quick_book(self, partner_id, coach_id, branch_id, date_str, hour):
        session = self.create({
            'partner_id': partner_id,
            'coach_id': coach_id,
            'branch_id': branch_id or False,
            'session_date': date_str,
            'start_hour': hour,
            'end_hour': hour + 1,
        })
        return session.id

    def action_start(self):
        self.write({'state': 'ongoing'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_no_show(self):
        self.write({'state': 'no_show'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'scheduled'})
