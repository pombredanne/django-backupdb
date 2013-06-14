import os
import shlex

from .exceptions import RestoreError
from .processes import pipe_commands, pipe_commands_to_file


def require_backup_exists(func):
    """
    Requires that the file referred to by `backup_file` exists in the file
    system before running the decorated function.
    """
    def new_func(*args, **kwargs):
        backup_file = kwargs['backup_file']
        if not os.path.exists(backup_file):
            raise RestoreError("Could not find file '{0}'".format(backup_file))
        return func(*args, **kwargs)
    return new_func


def get_mysql_args(db_config):
    user = db_config['USER']
    password = db_config.get('PASSWORD')
    host = db_config.get('HOST')
    port = db_config.get('PORT')
    db = db_config['NAME']

    args = ['--user={0}'.format(user)]
    if password:
        args += ['--password={0}'.format(password)]
    if host:
        args += ['--host={0}'.format(host)]
    if port:
        args += ['--port={0}'.format(port)]
    args += [db]

    return args


def get_postgresql_args(db_config, extra_args=None):
    user = db_config['USER']
    host = db_config.get('HOST')
    port = db_config.get('PORT')
    db = db_config['NAME']

    args = ['--username={0}'.format(user)]
    if host:
        args += ['--host={0}'.format(host)]
    if port:
        args += ['--port={0}'.format(port)]
    if extra_args:
        args += shlex.split(extra_args)
    args += [db]

    return args


def do_mysql_backup(backup_file, db_config, show_output=False):
    args = get_mysql_args(db_config)
    cmd = ['mysqldump'] + args
    pipe_commands_to_file([cmd, ['gzip']], path=backup_file, show_stderr=show_output)


def do_postgresql_backup(backup_file, db_config, pg_dump_options=None, show_output=False):
    password = db_config.get('PASSWORD')
    env = {'PGPASSWORD': password} if password else None

    args = get_postgresql_args(db_config, pg_dump_options)
    cmd = ['pg_dump', '--clean'] + args
    pipe_commands_to_file([cmd, ['gzip']], path=backup_file, extra_env=env, show_stderr=show_output)


def do_sqlite_backup(backup_file, db_config, show_output=False):
    db_file = db_config['NAME']

    cmd = ['cat', db_file]
    pipe_commands_to_file([cmd, ['gzip']], path=backup_file, show_stderr=show_output)


@require_backup_exists
def do_mysql_restore(backup_file, db_config, drop_tables=False, show_output=False):
    kwargs = {'show_stderr': show_output, 'show_last_stdout': show_output}

    args = get_mysql_args(db_config)
    mysql_cmd = ['mysql'] + args

    if drop_tables:
        dump_cmd = ['mysqldump'] + args + ['--no-data']
        pipe_commands([dump_cmd, ['grep', '^DROP'], mysql_cmd], **kwargs)

    pipe_commands([['cat', backup_file], ['gunzip'], mysql_cmd], **kwargs)


@require_backup_exists
def do_postgresql_restore(backup_file, db_config, drop_tables=False, show_output=False):
    password = db_config.get('PASSWORD')
    env = {'PGPASSWORD': password} if password else None
    kwargs = {'extra_env': env, 'show_stderr': show_output, 'show_last_stdout': show_output}

    args = get_postgresql_args(db_config)
    psql_cmd = ['psql'] + args

    if drop_tables:
        drop_sql = "SELECT 'DROP TABLE IF EXISTS \"' || tablename || '\" CASCADE;' FROM pg_tables WHERE schemaname = 'public';"
        gen_drop_sql_cmd = psql_cmd + ['-t', '-c', drop_sql]
        pipe_commands([gen_drop_sql_cmd, psql_cmd], **kwargs)

    pipe_commands([['cat', backup_file], ['gunzip'], psql_cmd], **kwargs)


@require_backup_exists
def do_sqlite_restore(backup_file, db_config, drop_tables=False, show_output=False):
    db_file = db_config['NAME']

    cmd = ['cat', backup_file]
    pipe_commands_to_file([cmd, ['gunzip']], path=db_file, show_stderr=show_output)
