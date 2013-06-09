from optparse import make_option
from subprocess import CalledProcessError
import os

from django.core.management.base import BaseCommand, CommandError

from backupdb_utils.commands import get_latest_timestamped_file, BACKUP_CONFIG
from backupdb_utils.exceptions import RestoreError
from backupdb_utils.settings import BACKUP_DIR
from backupdb_utils.streamtools import err, set_verbosity, section, SectionError


class Command(BaseCommand):
    help = 'Restores each database in settings.DATABASES from latest db backup.'
    can_import_settings = True

    option_list = BaseCommand.option_list + (
        make_option(
            '--backup-name',
            help=(
                'Name of backup to restore from.  Example: '
                '`--backup-name=mybackup` will restore any backups that look '
                'like "default-mybackup.pgsql.gz".  Defaults to latest '
                'timestamped backup name.'
            ),
        ),
        make_option(
            '--drop-tables',
            action='store_true',
            default=False,
            help=(
                '** EXPERIMENTAL, USE WITH CAUTION ** Drop all tables in '
                'databases before restoring them.  The SQL dumps which are '
                'created by backupdb have drop statements so, usually, this '
                'option is not necessary.'
            ),
        ),
        make_option(
            '--show-output',
            action='store_true',
            default=False,
            help=(
                'Display the output of stderr and stdout (apart from data which '
                'is piped from one process to another) for processes that are '
                'run while restoring databases.  These are command-line '
                'programs such as `psql` or `mysql`.  This can be useful for '
                'understanding how restoration is failing in the case that it '
                'is.'
            ),
        ),
    )

    def handle(self, *args, **options):
        from django.conf import settings

        # Ensure backup dir present
        if not os.path.exists(BACKUP_DIR):
            raise CommandError('Backup dir \'{0}\' does not exist!'.format(BACKUP_DIR))

        backup_name = options['backup_name']
        drop_tables = options['drop_tables']
        show_output = options['show_output']

        set_verbosity(int(options['verbosity']))

        # Loop through databases
        for db_name, db_config in settings.DATABASES.items():
            with section("Restoring '{0}'...".format(db_name)):
                # Get backup config for this engine type
                engine = db_config['ENGINE']
                backup_config = BACKUP_CONFIG.get(engine)
                if not backup_config:
                    raise SectionError("! Restore for '{0}' engine not implemented".format(engine))

                # Get backup file name
                backup_extension = backup_config['backup_extension']
                if backup_name:
                    backup_file = '{dir}/{db_name}-{backup_name}.{ext}.gz'.format(
                        dir=BACKUP_DIR,
                        db_name=db_name,
                        backup_name=backup_name,
                        ext=backup_extension,
                    )
                else:
                    try:
                        backup_file = get_latest_timestamped_file(backup_extension)
                    except RestoreError as e:
                        raise SectionError('! ' + e.message)

                # Find restore command and get kwargs
                restore_func = backup_config['restore_func']
                restore_kwargs = {
                    'backup_file': backup_file,
                    'db_config': db_config,
                    'drop_tables': drop_tables,
                    'show_output': show_output,
                }

                # Run restore command
                try:
                    restore_func(**restore_kwargs)
                    err("* Restored '{db}' from '{backup_file}'".format(
                        db=db_name,
                        backup_file=backup_file))
                except (RestoreError, CalledProcessError) as e:
                    raise SectionError('! ' + e.message)
