"""
Import chores to Grocy from a TSV file

e.g. exported from Excel/Sheets

"""
import csv
from os import environ
import sys

# pylint: disable=import-error
from grocy import Grocy
from grocy.grocy_api_client import DEFAULT_PORT_NUMBER
from grocy.data_models.chore import AssignmentType
from grocy.data_models.chore import PeriodType
from grocy.data_models.generic import EntityType
# pylint: enable=import-error


API_HOST = environ['GROCY_API_HOST']
API_PORT = environ.get('GROCY_API_PORT', DEFAULT_PORT_NUMBER)
API_KEY = environ['GROCY_API_KEY']
GROCY = Grocy(API_HOST, API_KEY, port=API_PORT)

CHORES_EPILOG = """
Expected Line Format:
Where	What	When	Who	Notes	Grocy Name

Columns:

- Where: Room/location prefix; e.g. "Kitchen", "Bathroom", etc.
- What: Title/summary; e.g. "Mop floor", "Tidy Up", etc.
- When: Frequency; i.e. "Daily", "Weekly", "Fortnightly", "Monthly",
        "Seasonally", "Biennially", "Anually", "Arbitrarily"
- Who: Grocy Username; e.g. "mom", "dad", "kid1", "kid2", etc.
- Notes: Description of chore
"""
CHORE_PERIOD_TYPE = {
    # UNUSED
    # 'ADAPTIVE': None,
    # 'DYNAMIC_REGULAR': None,
    # 'HOURLY': None,

    # USED
    'Daily': {
        'period_type': PeriodType.DAILY.value,
        'period_config': None, #
        'period_days': 1,
        'period_interval': 1,
    },
    'Monthly': {
        'period_type': PeriodType.MONTHLY.value,
        'period_config': 1, # day number of month
        'period_days': 1,
        'period_interval': 1,
    },
    'Weekly': {
        'period_type': PeriodType.WEEKLY.value,
        'period_config': 'sunday', # day name of week
        'period_days': 1,
        'period_interval': 1,
    },

    # RENAMED
    'Anually': {
        'period_type': PeriodType.YEARLY.value,
        'period_config': None, # 'sunday'
        'period_days': 1,
        'period_interval': 1,
    },
    'Arbitrarily': {
        'period_type': PeriodType.MANUALLY.value,
        'period_config': None, # 'sunday'
        'period_days': None,
        'period_interval': None,
    },

    # COMPOSITE
    'Fortnightly': {
        'period_type': PeriodType.WEEKLY.value,
        'period_config': 'sunday', # day name of week
        'period_days': 1,
        'period_interval': 2,
    },
    'Seasonally': {
        'period_type': PeriodType.MONTHLY.value,
        'period_config': 1, # day number of month
        'period_days': 1,
        'period_interval': 3,
    },
    'Biennially': {
        'period_type': PeriodType.MONTHLY.value,
        'period_config': 1, # day number of month
        'period_days': 1,
        'period_interval': 6,
    },
}


def _get_tsv_lines(input_path, users, has_header=True):
    """
    Get columns/rows from lines of a tab-separated-value list

    TODO: Handle escaped newlines and tabs
    """
    csv.register_dialect(
        'TabSeparatedValues',
        delimiter='\t',
        doublequote=False,
        # quotechar='"',
        quoting=csv.QUOTE_NONE,
        escapechar=None,
        # lineterminator='\r\n',
        skipinitialspace=True,
        strict=True,
    )
    users_non_admin = {
        username: user
        for username, user in users.items()
        if username != 'admin'
    }
    with open(input_path, encoding='utf-8') as input_file:
        reader = csv.reader(input_file, dialect='TabSeparatedValues')
        header = None
        for row in reader:
            if has_header and header is None:
                header = row
                continue
            where, what, when, who, how, name = row
            who = who.lower()
            if who == 'all':
                for username in users_non_admin:
                    _what = '; '.join((what, username))
                    _who = username.upper()
                    yield (where, _what, when, _who, how, name)
            else:
                yield row
    csv.unregister_dialect('TabSeparatedValues')


def _get_chore_data(name, description, user, when):
    chore_data = {
        'active': 1,
        'name': name,
        'description': description,            # _?

        'track_date_only': None,               # '0'
        'start_date': None,                    # '2026-07-14 16:58:49'

        'rollover': None,                      # '0'

        'consume_product_on_execution': None,  # '0'
        'product_id': None,                    # ''
    }
    if user:
        chore_data.update({
            'assignment_type': AssignmentType.IN_ALPHABETICAL_ORDER.value,
            'assignment_config': str(user.id),
        })
    else:
        # user_name in ('any', None):
        chore_data.update({
            'assignment_type': AssignmentType.NO_ASSIGNMENT.value,
            'assignment_config': None,
        })
    if when in CHORE_PERIOD_TYPE:
        chore_data.update(CHORE_PERIOD_TYPE[when])
    else:
        print("Skipping invalid frequency", name, when, file=sys.stderr)
        return None
    chore_data = {
        key: value
        for key, value in chore_data.items()
        if value is not None
    }
    return chore_data


def _write_chore(chore, chore_data):
    if chore is not None:
        response = GROCY.generic.update(EntityType.CHORES, object_id=chore.id, data=chore_data)
        print('Updated chore; object_id =', chore.id, file=sys.stderr)
    else:
        response = GROCY.generic.create(EntityType.CHORES, chore_data)
        object_id = int(response.get('created_object_id', '0'))
        print('Created chore; object_id =', object_id, file=sys.stderr)


def main():
    """
    Import chores to Grocy from a TSV file

    TODO: Build name (C1+C2) or read it (C6)
    """
    users = {
        user.username: user
        for user in GROCY.users.list()
    }
    chores = {
        chore.name: chore
        for chore in GROCY.chores.list(get_details=True)
    }
    for row in _get_tsv_lines('var/chores.tsv', users):
        where, what, when, who, how, _name = row
        if not (where and what):
            print("Skipping empty task", row, file=sys.stderr)
            continue
        chore_name = ': '.join((where, what))
        user_name = who.lower()
        user = users.get(user_name)
        chore_data = _get_chore_data(name=chore_name, description=how, user=user, when=when)
        if chore_data is None:
            continue
        chore = chores.get(chore_name)
        _write_chore(chore, chore_data)
    GROCY.chores.calculate_next_assignments()


if __name__ == '__main__':
    main()
