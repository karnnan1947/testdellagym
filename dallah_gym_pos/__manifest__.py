{
    'name': 'Dallah Gym POS - Checkout Extensions & Dot-Matrix Print',
    'version': '20.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'POS counter branch defaults, single pre-payment checkout modal (dates, turnstiles, '
               'coach 1-hour slots) and Epson LQ-350 continuous 3-ply receipt.',
    'description': """
Optimized Front-Desk POS Counter Extensions featuring pos.config Auto-Branch Defaults, Low-Load Single
Pre-Payment OWL Checkout Modal (Dates, Gate Turnstiles & Coach 1-Hr Slots), and Continuous 3-Ply
Epson LQ-350 Dot-Matrix Receipt Printing (DES00144).
    """,
    'author': 'AGM Global Services',
    'website': 'https://www.agmglobal.co/',
    'license': 'OPL-1',
    'depends': ['point_of_sale', 'pos_hr', 'dallah_gym_core', 'restricted_cost_access'],
    'data': [
        'security/ir.access.csv',
        'views/pos_config_views.xml',
        'views/pos_order_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'dallah_gym_pos/static/src/js/models.js',
            'dallah_gym_pos/static/src/js/GymCheckoutModal.js',
            'dallah_gym_pos/static/src/js/PaymentScreenHook.js',
            'dallah_gym_pos/static/src/js/PaymentValidationHook.js',
            'dallah_gym_pos/static/src/xml/GymCheckoutModal.xml',
            'dallah_gym_pos/static/src/xml/EpsonLQ350Receipt.xml',
            'dallah_gym_pos/static/src/scss/pos_custom.scss',
        ],
    },
    'installable': True,
    'application': False,
}
