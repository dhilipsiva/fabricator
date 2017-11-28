from os import environ

from fabric.colors import green
from fabric.contrib.files import exists
from fabric.context_managers import settings, lcd
from fabric.api import run, env, task, cd, puts, abort, local, sudo, hide

from fabtools.mysql import query
from fabtools import deb, require

branch = 'stable'
env.user = 'phacility'
hostname = environ["FABRICATOR_HOST"]
env.hosts = [environ['FABRICATOR_IP'], ]
apache_mods = ["rewrite", "ssl", "php7.0"]
db_root_pass = environ['FABRICATOR_DB_ROOT_PASS']
db_user_pass = environ['FABRICATOR_DB_USER_PASS']
repo_names = ["phabricator", "libphutil", "arcanist"]
repos = ["git@github.com:phacility/%s" % repo_name for repo_name in repo_names]

home_dir = "/home/%s" % env.user
apps_dir = "%s/apps" % home_dir
logs_dir = "%s/logs" % home_dir

docroot = "%s/phabricator/webroot" % apps_dir

CONFIG_TPL = '''
<VirtualHost *:%(port)s>
    ServerName %(hostname)s
    DocumentRoot %(docroot)s
    RewriteEngine on
    RewriteRule ^(.*)$          /index.php?__path__=$1  [B,L,QSA]
    <Directory "%(docroot)s">
        Require all granted
    </Directory>
</VirtualHost>
'''


# NOTE: most-git related code is borrowed from `gitric` pypi package
def git_init(repo_path):
    """
    create a git repository if necessary [remote]
    """

    if exists('%s/.git' % repo_path):
        return

    puts(green('Creating new git repository ') + repo_path)
    run('mkdir -p %s' % repo_path, quiet=True)
    with cd(repo_path), settings(warn_only=True):
        if run('git init').failed:
            run('git init-db')
        run('git config receive.denyCurrentBranch ignore')


def git_push(git_src, repo_path):
    """
    seed a git repository (and create if necessary) [remote]
    """
    git_init(repo_path)
    with settings(warn_only=True):
        with lcd(git_src):
            commit = local('git rev-parse HEAD', capture=True)
            puts(green('Pushing commit ') + commit)
            push = local(
                'git push git+ssh://%s@%s:%s%s %s:refs/heads/master' % (
                    env.user, env.host, env.port, repo_path, commit))

    if push.failed:
        abort(
            '%s is a non-fast-forward\n'
            'push. The seed will abort so you don\'t lose information. '
            'If you are doing this\nintentionally import '
            'gitric.api.force_push and add it to your call.' % commit)

    puts(green('Resetting to commit ') + commit)
    with cd(repo_path):
        run('git reset --hard %s' % commit)


def local_clone_repos():
    for repo in repos:
        local("git clone -b %s %s" % (branch, repo))


def local_pull_repos():
    for repo_name in repo_names:
        with lcd(repo_name):
            local("git checkout %s" % branch)
            local("git pull origin %s:%s" % (branch, branch))


def push_repos():
    for repo_name in repo_names:
        git_push(repo_name, "%s/%s" % (apps_dir, repo_name))


def grant_all(name, host='localhost', **kwargs):
    """
    GRANT ALL
    """
    with settings(
            hide('running', 'stdout', 'stderr', 'warnings'), warn_only=True):
        res = query("""
            use mysql;
            GRANT ALL PRIVILEGES ON * . * TO '%(name)s'@'%(host)s';
            """ % {'name': name, 'host': host}, **kwargs)
    return res.succeeded


@task
def setup():
    local_clone_repos()
    require.files.directories([apps_dir, logs_dir])
    require.files.directories(["/var/repo/"], use_sudo=True)
    require.deb.package("software-properties-common")
    sudo("add-apt-repository ppa:ondrej/php")
    sudo("add-apt-repository ppa:ondrej/apache2")
    sudo("add-apt-repository ppa:certbot/certbot")
    deb.update_index()
    deb.upgrade()
    require.git.command()
    require.deb.packages([
        "mysql-server", "dpkg-dev", "php7.1", "php7.1-mysql", "php7.1-gd",
        "php7.1-dev", "php7.1-curl", "php7.1-cli", "php7.1-json", "php-apcu",
        "libpcre3-dev", "php-pear", "libapache2-mod-php7.1", "sendmail",
        "php7.1-mbstring", "python-pip", "python-certbot-apache"])
    sudo("yes '' | pecl install apc")
    sudo("pip install pygments")
    require.apache.server()
    for apache_mod in apache_mods:
        require.apache.module_enabled(apache_mod)
    push_repos()
    require.apache.site(
        hostname,
        template_contents=CONFIG_TPL,
        port=80,
        hostname=hostname,
        docroot=docroot,
    )
    require.apache.site_enabled(hostname)
    require.apache.site_disabled('default')
    print("Please make sure %s is pointing to %s before certbot install" % (
        hostname, env.hosts))
    sudo("certbot --apache")
    require.mysql.server(password=db_root_pass)
    with settings(mysql_user='root', mysql_password=db_root_pass):
        require.mysql.user(env.user, db_user_pass)
        grant_all(env.user)
    require.file(
        "/etc/mysql/conf.d/mysql.cnf",
        "[mysqld]\nsql_mode=STRICT_ALL_TABLES", use_sudo=True)
    sudo("service mysql restart")
    require.nodejs.installed_from_source(version='8.9.1')
    with cd("%s/phabricator" % apps_dir):
        run("./bin/config set mysql.host localhost")
        run("./bin/config set mysql.user %s" % env.user)
        run("./bin/config set mysql.pass %s" % db_user_pass)
        run("./bin/config set phabricator.base-uri 'https://%s'" % hostname)
        run("./bin/storage upgrade --force")
        run("./bin/phd start")
        run("./bin/aphlict start")


@task
def quick():
    with cd("%s/phabricator" % apps_dir):
        run("./bin/phd start")
        run("./bin/aphlict start")
