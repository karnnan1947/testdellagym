{
    'name': 'Dallah Gym Core - Membership & Operations',
    'version': '20.0.1.0.0',
    'category': 'Services/Gym Management',
    'summary': 'Gym membership contracts, unified Sales & POS service engine, coach split shifts, '
               'PT bookings, freeze wizard, expiry reminders, pro-rata refunds and turnstile check-ins.',
    'description': """
Core Gym Membership Contracts, Unified Sales & POS Service Engine, Trainer Split-Shift Schedules,
PT Session Bookings, Vacation Freeze Wizard, Tiered Expiry Reminders, Pro-Rata Refunds,
Turnstile Check-in Model & Dual PT Dashboards (DES00143).
    """,
    'author': 'AGM Global Services',
    'website': 'https://www.agmglobal.co/',
    'license': 'OPL-1',
    'depends': [
        'base', 'contacts', 'sale_management', 'account', 'account_accountant',
        'hr', 'mail', 'resource', 'restricted_cost_access',
    ],
    'data': [
        'security/gym_security.xml',
        'security/ir.access.csv',
        'data/gym_sequence_data.xml',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
        'views/res_branch_views.xml',
        'views/product_template_views.xml',
        'views/hr_employee_views.xml',
        'views/gym_membership_views.xml',
        'views/gym_member_checkin_views.xml',
        'views/gym_pt_session_views.xml',
        'views/gym_pt_dashboard_action.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'wizard/gym_freeze_wizard_views.xml',
        'wizard/gym_refund_wizard_views.xml',
        'views/gym_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dallah_gym_core/static/src/scss/pt_dashboard.scss',
            'dallah_gym_core/static/src/xml/pt_dashboard_templates.xml',
            'dallah_gym_core/static/src/js/pt_dashboard.js',
        ],
    },
    'installable': True,
    'application': True,
}
