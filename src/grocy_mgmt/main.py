"""
Import chores to Grocy from a TSV file

e.g. exported from Excel/Sheets

"""
import argparse
import csv
import json
import os
import sys

# pylint: disable=import-error
from grocy import Grocy
from grocy.grocy_api_client import DEFAULT_PORT_NUMBER
from grocy.data_models.chore import AssignmentType
from grocy.data_models.chore import PeriodType
from grocy.data_models.generic import EntityType
# pylint: enable=import-error


APP_NAME = 'grocy-mgmt'
USER_HOME = os.environ.get('HOME') or os.path.expanduser('~')
CACHE_HOME_XDG = os.environ.get('XDG_CACHE_HOME') or os.path.join(USER_HOME, '.cache')
CACHE_HOME_APP = os.path.join(CACHE_HOME_XDG, APP_NAME)
CACHE_PATH_LOG = os.path.join(CACHE_HOME_APP, 'app.log')
CONFIG_HOME_XDG = os.environ.get('XDG_CONFIG_HOME') or os.path.join(USER_HOME, '.config')
CONFIG_HOME_APP = os.path.join(CONFIG_HOME_XDG, APP_NAME)
CONFIG_PATH_JSON = os.path.join(CONFIG_HOME_APP, 'config.json')
CONFIG_ENV_PREFIX = 'GROCY_MGMT_'  # Changing this value is a breaking change!

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
            if who == 'all':
                for username in users_non_admin:
                    _what = '; '.join((what, username))
                    yield (where, _what, when, username, how, name)
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


def _write_chore(noop, api, chore, chore_data):
    """
    Create or update a chore
    """
    if chore is not None:
        if not noop:
            response = api.generic.update(EntityType.CHORES, object_id=chore.id, data=chore_data)
        print('Updated chore; object_id =', chore.id, file=sys.stderr)
    else:
        if not noop:
            response = api.generic.create(EntityType.CHORES, chore_data)
            object_id = int(response.get('created_object_id', '0'))
        else:
            object_id = -1
        print('Created chore; object_id =', object_id, file=sys.stderr)


def _ensure_app_directories_exist():  # type: () -> None
    """
    Create necessary application directories
    """
    for _dir in (CONFIG_HOME_APP, CACHE_HOME_APP):
        if not os.path.isdir(_dir):
            try:
                os.makedirs(_dir)
            except FileExistsError:
                pass


def parse_args():  # type: () -> Dict[str, Any]
    """
    Parse and process configuration arguments

    CLI > ENV > JSON > DEFAULTS
    """
    # pylint: disable=too-many-locals
    script_name = os.path.split(sys.argv[0])[-1]
    description = __doc__
    parser = argparse.ArgumentParser(
        prog=script_name,
        description=description,
    )
    parser.add_argument(
        '-c',
        '--config',
        help='Path to JSON config file',
    )
    parser.add_argument(
        '-n',
        '--noop',
        action='store_true',
        default=None,
    )
    parser.add_argument(
        '-N',
        '--no-noop',
        action='store_false',
        default=None,
        dest='noop',
    )
    subparsers = parser.add_subparsers(dest='subcommand')
    parser_import_chores = subparsers.add_parser(
        'import_chores_tsv',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CHORES_EPILOG,
    )
    parser_import_chores.add_argument(
        '-a',
        '--host-address',
    )
    parser_import_chores.add_argument(
        '-p',
        '--host-port',
    )
    parser_import_chores.add_argument(
        '-P',
        '--host-path',
    )
    parser_import_chores.add_argument(
        '-k',
        '--api-key',
    )
    parser_import_chores.add_argument(
        '-i',
        '--input-file-tsv',
    )
    args = parser.parse_args()
    cli_settings = vars(args)
    env_settings = {
        key.lower()[len(CONFIG_ENV_PREFIX):]: value
        for key, value in os.environ.items()
        if key.startswith(CONFIG_ENV_PREFIX)
    }
    default_settings = {
        'config': CONFIG_PATH_JSON,
        'host_address': 'http://127.0.0.1',
        'host_port': DEFAULT_PORT_NUMBER,
        'host_path': '',
        'noop': True,
        'subcommand': 'import_chores_tsv',
        'input_file_tsv': None,
        'api_key': None,
    }
    config_path = str(
        cli_settings['config']
        or env_settings.get('config')
        or default_settings['config']
    )
    with open(config_path, 'r', encoding='utf-8') as config_file:
        json_settings = json.load(config_file)
    join_settings = {
        key: value if value is not None else (
            env_settings.get(
                key,
                json_settings.get(
                    key,
                    default_settings.get(key)
                )
            )
        )
        for key, value in cli_settings.items()
    }
    return join_settings


def main():
    """
    Import chores to Grocy from a TSV file

    TODO: Build name (C1+C2) or read it (C6)
    """
    _ensure_app_directories_exist()
    args = parse_args()
    api = Grocy(args['host_address'], args['api_key'], port=args['host_port'])
    users = {
        user.username: user
        for user in api.users.list()
    }
    chores = {
        chore.name: chore
        for chore in api.chores.list(get_details=True)
    }
    for row in _get_tsv_lines(args['input_file_tsv'], users):
        where, what, when, who, how, _name = row
        if not (where and what):
            print("Skipping empty task", row, file=sys.stderr)
            continue
        chore_name = ': '.join((where, what))
        user = users.get(who)
        chore_data = _get_chore_data(name=chore_name, description=how, user=user, when=when)
        if chore_data is None:
            continue
        chore = chores.get(chore_name)
        _write_chore(args['noop'], api, chore, chore_data)
    if not args['noop']:
        api.chores.calculate_next_assignments()


if __name__ == '__main__':
    main()
